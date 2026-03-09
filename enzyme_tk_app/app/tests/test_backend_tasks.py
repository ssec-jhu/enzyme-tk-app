"""Tests for ``run_tool_task`` and the result-offloading helpers in ``tasks.py``.

These tests mock the ``importlib`` import machinery and inject the
``fakeredis`` stub (from conftest) via ``_get_redis`` so they run
without a broker, worker, or live Redis instance.
"""

import json
from unittest import mock

import pytest

from enzyme_tk_app.app.backend.models import JobStatus
from enzyme_tk_app.app.backend.tasks import _make_preview, _store_result

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
    ):
        cfg.JOB_TTL_SECONDS = 86400
        cfg.MAX_RESULT_BYTES = 512 * 1024
        cfg.SHARED_VOLUME_PATH = str(tmp_path)
        mock_importlib.import_module.return_value = compute
        yield compute


# ── 1. _make_preview ─────────────────────────────────────────────────────────
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


# ── 2. _store_result ─────────────────────────────────────────────────────────
# _store_result decides whether to keep a result inline in Redis or
# offload it to the shared Docker volume.  The threshold is set by
# config.MAX_RESULT_BYTES (default 512 KB).
# Only two code paths exist (inline vs offload) — one test each.


def test_store_result_inline_small(tmp_path):
    """Small results are returned inline without writing to disk.

    Why this matters: most tool results are a few KB.  Keeping them in
    Redis avoids extra disk I/O and simplifies retrieval.  This test
    verifies the "no-op" path where the result stays in Redis as-is.
    """
    result = {"answer": 42}
    with mock.patch("enzyme_tk_app.app.backend.tasks.config") as cfg:
        cfg.MAX_RESULT_BYTES = 512 * 1024
        cfg.SHARED_VOLUME_PATH = str(tmp_path)
        stored = _store_result("job-small", result)

    # The result dict should pass through unchanged.
    assert stored == result
    # No file should have been created on the shared volume.
    assert not (tmp_path / "job_outputs" / "job-small").exists()


def test_store_result_offloads_large(tmp_path):
    """Large results are written to the shared volume with a reference.

    Why this matters: if a tool returns megabytes of data, keeping it in
    Redis wastes memory and risks OOM.  The offload writes the full JSON
    to the shared volume and returns a small reference dict + preview.
    We use an intentionally low threshold (100 bytes) so the test triggers
    offloading without needing megabytes of test data.
    """
    result = {"data": "x" * 200}
    with mock.patch("enzyme_tk_app.app.backend.tasks.config") as cfg:
        cfg.MAX_RESULT_BYTES = 100
        cfg.SHARED_VOLUME_PATH = str(tmp_path)
        stored = _store_result("job-big", result)

    # The reference dict must contain all three expected keys.
    assert "_result_ref" in stored
    assert "_result_size_bytes" in stored
    assert "preview" in stored

    # The file on the shared volume must contain the original result,
    # proving that no data was lost during offloading.
    ref_path = stored["_result_ref"]
    with open(ref_path) as fh:
        loaded = json.load(fh)
    assert loaded == result


# ── 3. run_tool_task (mocked execution) ──────────────────────────────────────
# run_tool_task is the Celery task entry-point.  It dynamically imports a
# tool's compute module, runs it, and writes the outcome to Redis.
# These tests call the function directly (bypassing the Celery broker)
# with Redis, importlib, and config patched via the ``mock_compute``
# fixture.  Each test covers a distinct outcome: success, failure,
# and stdout capture.


def test_run_tool_task_success(fake_redis, mock_compute):
    """A successful compute.run() stores SUCCESS status and result in Redis.

    Why this matters: the happy path must write both "status" and "result"
    fields so the UI can show the outcome.  This confirms the full
    pipeline — import → run → serialise → store — works end-to-end.
    """
    mock_compute.run.return_value = {"similarity": 0.95}

    from enzyme_tk_app.app.backend.tasks import run_tool_task

    run_tool_task("test-tool", {"query": "CCO"}, "sess-1", "job-123")

    job_data = fake_redis.hgetall("job:job-123")
    assert job_data["status"] == JobStatus.SUCCESS.value
    assert json.loads(job_data["result"]) == {"similarity": 0.95}


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
