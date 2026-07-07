"""Tests for ``run_tool_task`` and the result-offloading helpers in ``tasks.py``.

These tests mock the ``importlib`` import machinery and inject the
``fakeredis`` stub (from conftest) via ``_get_redis`` so they run
without a broker, worker, or live Redis instance.
"""

import json
from unittest import mock

import pytest

from enzyme_tk_app.app.backend.models import JobStatus
from enzyme_tk_app.app.backend.tasks import _make_preview, _store_result, celery_beat_sweep_orphaned_outputs

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_compute(fake_redis, tmp_path):
    """Patch Redis, importlib, and config for ``run_tool_task`` tests.

    Yields a ``MagicMock`` representing the tool's ``compute`` module.
    Configure ``mock_compute.run.return_value`` or ``.side_effect`` in
    each test to control what the tool "computes".

    Uses the ``fake_redis`` fixture from conftest so that the tests
    exercise the real Redis command API (hset, expire, hgetall) instead
    of a hand-rolled stub that could silently pass if the production
    code changes Redis commands.
    """
    compute = mock.MagicMock()
    with (
        mock.patch("enzyme_tk_app.app.backend.tasks._get_redis", return_value=fake_redis),
        mock.patch("enzyme_tk_app.app.backend.tasks.importlib") as mock_importlib,
        mock.patch("enzyme_tk_app.app.backend.tasks.config") as cfg,
        mock.patch(
            "enzyme_tk_app.app.backend.tasks.DEFAULT_MAX_DURATION",
            3600,
        ),
        mock.patch(
            "enzyme_tk_app.app.backend.tasks.HARD_TIMEOUT_GRACE_SECONDS",
            60,
        ),
        mock.patch(
            "enzyme_tk_app.app.backend.tasks.effective_ttl",
            side_effect=lambda max_duration=3600, grace=60: max_duration + grace + 86400,
        ),
    ):
        cfg.JOB_TTL_SECONDS = 86400
        cfg.JOB_OUTPUTS_PATH = str(tmp_path / "job_outputs")
        mock_importlib.import_module.return_value = compute
        yield compute


# ── _make_preview ─────────────────────────────────────────────────────────
# _make_preview builds a lightweight summary of a result dict so the
# jobs-list page can show a useful snippet without loading megabytes of
# data from Redis.  Each test below exercises one distinct summarisation
# rule to verify they work in isolation.


def test_make_preview_small_dict():
    """Preview of a small dict returns it unchanged.

    Why this matters: when all values are small scalars and there are few
    keys, the preview should be an exact copy — no information loss.
    """
    result = {"a": 1, "b": 2}
    preview = _make_preview(result)
    assert preview == {"a": 1, "b": 2}


def test_make_preview_truncates_large_list():
    """Preview summarises list values with more than 3 items.

    Why this matters: tool results often contain large arrays (e.g. 10 000
    similarity scores).  The preview replaces them with a count string so
    the JSON stored in Redis stays small.
    """
    result = {"rows": list(range(100))}
    preview = _make_preview(result)
    assert preview["rows"] == "[100 items]"


def test_make_preview_truncates_large_nested_dict():
    """Preview summarises dict values with more than 3 keys.

    Why this matters: deeply nested dicts can be arbitrarily large.
    Replacing them with "{N keys}" keeps the preview bounded regardless
    of depth.
    """
    result = {"meta": {"a": 1, "b": 2, "c": 3, "d": 4}}
    preview = _make_preview(result)
    assert preview["meta"] == "{4 keys}"


def test_make_preview_limits_top_level_keys():
    """Preview includes at most max_items (default 5) top-level keys.

    Why this matters: even if every individual value is tiny, a result
    with hundreds of keys would produce an unwieldy preview.  Capping at
    max_items keeps the preview small regardless of the result shape.
    """
    result = {f"key{i}": i for i in range(20)}
    preview = _make_preview(result, max_items=5)
    assert len(preview) == 5


# ── _store_result ─────────────────────────────────────────────────────────
# _store_result now ALWAYS offloads the full result to the shared Docker
# volume and returns only a pointer dict (ref + size + preview).  There is
# no longer a size threshold or an inline path — small and large results
# behave identically, so one parametrized test covers both.


@pytest.mark.parametrize(
    ("job_id", "result"),
    [
        ("job-small", {"answer": 42}),
        ("job-large", {"data": "x" * 200}),
    ],
    ids=["small-result", "large-result"],
)
def test_store_result_always_offloads(tmp_path, job_id, result):
    """Every result — small or large — is offloaded to the shared volume.

    Why this matters: keeping full results out of Redis avoids memory
    bloat and OOM risk regardless of size.  Redis only ever sees the
    pointer dict, while the complete result must round-trip losslessly
    from ``<JOB_OUTPUTS_PATH>/<job_id>/result.json`` on the shared volume.
    """
    with mock.patch("enzyme_tk_app.app.backend.tasks.config") as cfg:
        cfg.JOB_OUTPUTS_PATH = str(tmp_path / "job_outputs")
        stored = _store_result(job_id, result)

    # Redis only ever gets the pointer dict — never the full result inline.
    assert set(stored) == {"_result_ref", "_result_size_bytes", "preview"}

    # The full result must round-trip from the file on the shared volume,
    # proving no data was lost during offloading.
    result_file = tmp_path / "job_outputs" / job_id / "result.json"
    assert result_file.exists()
    with open(result_file) as fh:
        assert json.load(fh) == result

    # The returned reference must point at the file we just verified.
    assert stored["_result_ref"] == str(result_file)


# ── run_tool_task (mocked execution) ──────────────────────────────────────
# run_tool_task is the Celery task entry-point.  It dynamically imports a
# tool's compute module, runs it, and writes the outcome to Redis.
# These tests call the function directly (bypassing the Celery broker)
# with Redis, importlib, and config patched via the ``mock_compute``
# fixture.  Each test covers a distinct outcome: success, failure,
# and stdout capture.


def test_run_tool_task_success(fake_redis, mock_compute):
    """A successful compute.run() stores SUCCESS status and a result pointer.

    Why this matters: the happy path must write both "status" and "result"
    fields so the UI can show the outcome.  Since results are always
    offloaded, Redis stores the pointer dict (ref + preview), and the full
    result must round-trip from the file on the shared volume.
    """
    mock_compute.run.return_value = {"similarity": 0.95}

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    run_tool_task("test-tool", {"query": "CCO"}, "sess-1", "job-123")

    job_data = fake_redis.hgetall("job:job-123")
    assert job_data["status"] == JobStatus.SUCCESS.value

    # Redis holds only the pointer dict, whose preview mirrors the result.
    stored = json.loads(job_data["result"])
    assert stored["preview"] == {"similarity": 0.95}

    # The full result must round-trip from the offloaded file.
    with open(stored["_result_ref"]) as fh:
        assert json.load(fh) == {"similarity": 0.95}


def test_run_tool_task_failure(fake_redis, mock_compute):
    """A failing compute.run() stores FAILURE status and traceback.

    Why this matters: when a tool crashes (e.g. invalid user input), the
    task must NOT propagate the exception to Celery.  Instead it records
    the traceback in Redis so the UI can display a user-friendly error.
    If this behaviour breaks, user-facing errors would be silent.
    """
    mock_compute.run.side_effect = ValueError("Invalid SMILES")

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    run_tool_task("test-tool", {"query": "BAD"}, "sess-1", "job-fail")

    job_data = fake_redis.hgetall("job:job-fail")
    assert job_data["status"] == JobStatus.FAILURE.value
    assert "Invalid SMILES" in job_data["error"]


def test_run_tool_task_captures_stdout(fake_redis, mock_compute):
    """stdout from compute.run() is captured in the output_log.

    Why this matters: scientific tools commonly use print() for progress
    logging.  The task wraps execution with redirect_stdout so users can
    review algorithm output after the job completes.  Without this,
    print() output would be lost inside the Celery worker.
    """

    def run_with_output(params):
        print("Processing query...")  # noqa: T201
        print("Done!")  # noqa: T201
        return {"result": "ok"}

    mock_compute.run.side_effect = run_with_output

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    run_tool_task("test-tool", {}, "sess-1", "job-stdout")

    job_data = fake_redis.hgetall("job:job-stdout")
    assert "Processing query..." in job_data["output_log"]
    assert "Done!" in job_data["output_log"]


def test_run_tool_task_timeout(fake_redis, mock_compute):
    """SoftTimeLimitExceeded from compute.run() stores TIMEOUT status.

    Why this matters: when a tool exceeds its ``max_duration`` timeout,
    Celery raises ``SoftTimeLimitExceeded``.  The task must catch it and
    record TIMEOUT (not FAILURE) so the UI shows the correct status and
    message.  Without this, the exception would propagate uncaught
    because ``SoftTimeLimitExceeded`` does not inherit from ``Exception``.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    mock_compute.run.side_effect = SoftTimeLimitExceeded()

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    run_tool_task("test-tool", {"query": "slow"}, "sess-1", "job-timeout")

    job_data = fake_redis.hgetall("job:job-timeout")
    assert job_data["status"] == JobStatus.TIMEOUT.value
    assert "exceeded" in job_data["error"].lower()


# ── Session set TTL refresh ───────────────────────────────────────────────────
# The session-set key (session:<id>:jobs) must have its TTL refreshed
# every time the job hash TTL is refreshed, otherwise the set can expire
# before the job hash and break ownership checks / job listing.


def test_run_tool_task_refreshes_session_set_ttl(fake_redis, mock_compute):
    """run_tool_task must refresh the session-set TTL alongside the job hash TTL.

    Why this matters: the session set (``session:<id>:jobs``) is only given
    a TTL at submission time.  If the worker refreshes the job hash TTL
    (at STARTED and in the ``finally`` block) without also refreshing the
    session set, the set can expire before the job — breaking ownership
    checks and ``list_jobs`` even though the job data still exists in Redis.
    """
    mock_compute.run.return_value = {"ok": True}

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    session_key = "session:sess-ttl:jobs"

    # Pre-set the session set with a short TTL to simulate an almost-expired set.
    fake_redis.sadd(session_key, "old-job")
    fake_redis.expire(session_key, 10)  # about to expire

    run_tool_task("test-tool", {}, "sess-ttl", "job-ttl-check")

    # After the task completes, the session set TTL must have been refreshed
    # to the full JOB_TTL_SECONDS (86 400 in the mock_compute fixture).
    ttl = fake_redis.ttl(session_key)
    assert ttl > 10, f"session set TTL must be refreshed (got {ttl}s, expected ~86400)"


# ── celery_beat_sweep_orphaned_outputs ──────────────────────────────────────
# celery_beat_sweep_orphaned_outputs reclaims disk by deleting result
# directories whose Redis ``job:<id>`` key has already expired.


@pytest.fixture()
def sweep_env(fake_redis, tmp_path):
    """Patch Redis and config for the orphan-sweep tests.

    Yields the ``job_outputs`` directory path (a ``Path``) so each test can
    build result directories inside it.
    """
    outputs_dir = tmp_path / "job_outputs"
    with (
        mock.patch("enzyme_tk_app.app.backend.tasks._get_redis", return_value=fake_redis),
        mock.patch("enzyme_tk_app.app.backend.tasks.config") as cfg,
    ):
        cfg.JOB_OUTPUTS_PATH = str(outputs_dir)
        yield outputs_dir


def _make_output_dir(outputs_dir, job_id):
    """Create ``<outputs_dir>/<job_id>/result.json`` for the sweep tests."""
    job_dir = outputs_dir / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "result.json").write_text("{}")
    return job_dir


def test_sweep_removes_orphan(sweep_env):
    """A result dir with no live Redis key is deleted.

    Why this matters: this is the whole point of the sweep — when a job's
    Redis metadata has aged out (TTL reached) the leftover ``result.json``
    on the shared volume is dead weight and must be reclaimed.
    """
    job_dir = _make_output_dir(sweep_env, "orphan-1")
    # No ``job:orphan-1`` key exists in fakeredis, simulating an expired job.

    removed = celery_beat_sweep_orphaned_outputs()

    assert removed == 1
    assert not job_dir.exists()


def test_sweep_keeps_dir_with_live_redis_key(sweep_env, fake_redis):
    """A result dir whose ``job:<id>`` key still exists survives.

    Why this matters: a live Redis key means the job is still within its
    retention window and the user can still open its results.  Deleting the
    file would break the results page even though the metadata is present.
    """
    job_dir = _make_output_dir(sweep_env, "live-1")
    fake_redis.hset("job:live-1", mapping={"status": JobStatus.SUCCESS.value})

    removed = celery_beat_sweep_orphaned_outputs()

    assert removed == 0
    assert job_dir.exists()


def test_sweep_returns_zero_when_outputs_dir_missing(sweep_env):
    """A missing ``JOB_OUTPUTS_PATH`` returns 0 without raising.

    Why this matters: on a fresh deployment no job has ever run, so the
    outputs directory may not exist yet.  The periodic sweep must handle
    that gracefully rather than crashing the Celery beat schedule.
    """
    # ``sweep_env`` points JOB_OUTPUTS_PATH at a directory we never create.
    assert not sweep_env.exists()

    assert celery_beat_sweep_orphaned_outputs() == 0
