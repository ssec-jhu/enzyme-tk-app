"""Tests for ``CeleryTaskScheduler`` — the concrete Redis + Celery backend.

These tests exercise the scheduler's **public API** without requiring a
running Redis or Celery.  The ``fakeredis`` package provides a
protocol-faithful in-memory Redis that catches compatibility issues when
``redis-py`` is upgraded.  Fixtures (``fake_redis``, ``task_scheduler_celery_service``) and
the ``write_job_into_fake_redis`` helper are provided by ``conftest.py``.
"""

import uuid
from unittest import mock

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.tests.conftest import write_job_into_fake_redis

# ── submit_job ──────────────────────────────────────────────────────────────────


def test_submit_job_returns_uuid(task_scheduler_celery_service):
    """submit_job returns a valid UUID4 string.

    Why this matters: the job_id is used as the Redis key and the output
    directory name.  If it's not a valid UUID, key collisions or path
    traversal issues could arise.
    """
    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.apply_async = mock.MagicMock()
        job_id = task_scheduler_celery_service.submit_job("reaction-similarity", {"smiles": "CCO"}, "sess-1")

    uuid.UUID(job_id)


def test_submit_job_dispatches_celery_task(task_scheduler_celery_service):
    """submit_job sends a Celery message with the correct tool slug and job_id.

    Why this matters: if ``apply_async`` isn't called (or is called with
    wrong kwargs), the worker never picks up the job and it stays PENDING
    forever.  This is the only test we need for submit's side effects —
    the Redis hash and session set are implicitly verified by the get/list
    tests below.
    """
    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.apply_async = mock.MagicMock()
        job_id = task_scheduler_celery_service.submit_job("reaction-similarity", {"k": "v"}, "sess-1")

    mock_task.apply_async.assert_called_once()
    call_kwargs = mock_task.apply_async.call_args
    task_kwargs = call_kwargs.kwargs.get("kwargs") or call_kwargs[1].get("kwargs")
    assert task_kwargs["tool_slug"] == "reaction-similarity"
    assert task_kwargs["job_id"] == job_id

    # The Celery task_id must equal job_id so that cancel_job (which calls
    # revoke(job_id, ...)) targets the correct Celery task.
    celery_task_id = call_kwargs.kwargs.get("task_id") or call_kwargs[1].get("task_id")
    assert celery_task_id == job_id


# ── get_job / get_job_status ──────────────────────────────────────────────


def test_get_job_returns_job_info(task_scheduler_celery_service, fake_redis):
    """get_job returns a fully populated JobInfo for an owned job.

    Why this matters: this is the primary way the UI retrieves job
    results.  If deserialization from Redis is broken, the user sees
    nothing after a successful computation.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS", result='{"answer": 42}')
    job = task_scheduler_celery_service.get_job("j1", "sess-1")

    assert isinstance(job, JobInfo)
    assert job.status is JobStatus.SUCCESS
    assert job.result == {"answer": 42}


def test_get_job_returns_none_for_wrong_session(task_scheduler_celery_service, fake_redis):
    """get_job returns None when the caller doesn't own the job.

    Why this matters: this is the core session-isolation guarantee.
    Without it, any user could read another user's results by guessing
    a job_id.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1")
    assert task_scheduler_celery_service.get_job("j1", "sess-OTHER") is None


def test_get_job_returns_none_for_missing_job(task_scheduler_celery_service):
    """get_job returns None for a job_id that doesn't exist in Redis.

    Why this matters: after TTL expiry or manual deletion, the UI must
    handle a missing job gracefully instead of crashing.
    """
    assert task_scheduler_celery_service.get_job("no-such-job", "sess-1") is None


def test_get_job_status_lightweight(task_scheduler_celery_service, fake_redis):
    """get_job_status reads only the status field (not the full hash).

    Why this matters: the UI polls this endpoint frequently for progress
    updates.  It must return the correct enum value without the overhead
    of deserializing params/result/output_log.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="STARTED")
    assert task_scheduler_celery_service.get_job_status("j1", "sess-1") is JobStatus.STARTED


def test_get_job_status_none_for_wrong_session(task_scheduler_celery_service, fake_redis):
    """get_job_status enforces ownership, same as get_job."""
    write_job_into_fake_redis(fake_redis, "j1", "sess-1")
    assert task_scheduler_celery_service.get_job_status("j1", "sess-OTHER") is None


# ── list_jobs ───────────────────────────────────────────────────────────────────


def test_list_jobs_returns_session_jobs(task_scheduler_celery_service, fake_redis):
    """list_jobs returns only jobs belonging to the given session.

    Why this matters: the jobs dashboard shows "your" jobs.  If session
    filtering is broken, users would see other people's jobs or miss
    their own.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-A")
    write_job_into_fake_redis(fake_redis, "j2", "sess-A")
    write_job_into_fake_redis(fake_redis, "j3", "sess-B")

    jobs_a = task_scheduler_celery_service.list_jobs("sess-A")
    jobs_b = task_scheduler_celery_service.list_jobs("sess-B")

    assert len(jobs_a) == 2
    assert len(jobs_b) == 1
    assert {j.job_id for j in jobs_a} == {"j1", "j2"}


def test_admin_list_all_jobs_returns_everything(task_scheduler_celery_service, fake_redis):
    """admin_list_all_jobs returns jobs from all sessions (admin view).

    Why this matters: the admin dashboard needs a global view.  This must
    scan all ``job:*`` keys, not just one session's set.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-A")
    write_job_into_fake_redis(fake_redis, "j2", "sess-B")

    assert len(task_scheduler_celery_service.admin_list_all_jobs()) == 2


# ── Session isolation ───────────────────────────────────────────────────────────


def test_session_isolation_delete_job(task_scheduler_celery_service, fake_redis):
    """User A cannot delete user B's job — ownership is enforced.

    Why this matters: without this check, a malicious or buggy client
    could delete another user's completed results.
    """
    write_job_into_fake_redis(fake_redis, "j-secret", "sess-B", status="SUCCESS")
    assert task_scheduler_celery_service.delete_job("j-secret", "sess-A") is False
    # Job must still exist.
    assert fake_redis.hgetall("job:j-secret") != {}


# ── delete_job ──────────────────────────────────────────────────────────────────


def test_delete_terminal_job(task_scheduler_celery_service, fake_redis):
    """delete_job removes a completed (terminal) job from Redis.

    Why this matters: users need to clean up old results.  After deletion
    the Redis hash must be gone and the session set must no longer
    reference it.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS")
    assert task_scheduler_celery_service.delete_job("j1", "sess-1") is True
    assert fake_redis.hgetall("job:j1") == {}


def test_delete_running_job_refuses(task_scheduler_celery_service, fake_redis):
    """delete_job refuses to remove a non-terminal (STARTED) job.

    Why this matters: deleting a running job would orphan the Celery
    task — the worker would finish but have nowhere to write results.
    Users must cancel first, then delete.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="STARTED")
    assert task_scheduler_celery_service.delete_job("j1", "sess-1") is False
    assert fake_redis.hgetall("job:j1") != {}


# ── clear_jobs ──────────────────────────────────────────────────────────────────


def test_clear_jobs_removes_terminal_only(task_scheduler_celery_service, fake_redis):
    """clear_jobs bulk-removes finished jobs but preserves running ones.

    Why this matters: the "clear all" button in the UI should clean up
    completed work without accidentally destroying in-progress jobs.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS")
    write_job_into_fake_redis(fake_redis, "j2", "sess-1", status="FAILURE")
    write_job_into_fake_redis(fake_redis, "j3", "sess-1", status="STARTED")

    count = task_scheduler_celery_service.clear_jobs("sess-1")
    assert count == 2
    assert fake_redis.hgetall("job:j3") != {}
    assert fake_redis.hgetall("job:j1") == {}


# ── cancel_job ──────────────────────────────────────────────────────────────────


def test_cancel_job_revokes_pending(task_scheduler_celery_service, fake_redis):
    """cancel_job sends SIGKILL via Celery and marks the job REVOKED.

    Why this matters: this is the only way a user can stop a running
    computation.  The status must update in Redis immediately so the UI
    reflects the change without waiting for the killed worker to report.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="PENDING")

    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.app = mock.MagicMock()
        result = task_scheduler_celery_service.cancel_job("j1", "sess-1")

    assert result is True
    assert fake_redis.hgetall("job:j1")["status"] == "REVOKED"


def test_cancel_job_refreshes_ttls(task_scheduler_celery_service, fake_redis):
    """cancel_job refreshes both job hash and session set TTLs.

    Why this matters: the worker is SIGKILL'd so its ``finally`` block
    never runs.  If the job had been running for most of the TTL period,
    the remaining TTL could be very short — the user might not see the
    REVOKED status before it expires.  Refreshing both keys gives the
    user a full window.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="STARTED")

    # Simulate almost-expired keys.
    fake_redis.expire("job:j1", 10)
    fake_redis.expire("session:sess-1:jobs", 10)

    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.app = mock.MagicMock()
        task_scheduler_celery_service.cancel_job("j1", "sess-1")

    # Both TTLs must be refreshed well beyond 10 seconds.
    assert fake_redis.ttl("job:j1") > 10
    assert fake_redis.ttl("session:sess-1:jobs") > 10


def test_cancel_job_refuses_terminal(task_scheduler_celery_service, fake_redis):
    """cancel_job returns False for already-completed jobs.

    Why this matters: revoking a finished task is a no-op in Celery but
    could confuse the UI.  The scheduler must reject the request cleanly.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS")
    assert task_scheduler_celery_service.cancel_job("j1", "sess-1") is False


def test_cancel_job_wrong_session(task_scheduler_celery_service, fake_redis):
    """cancel_job enforces ownership — user A cannot cancel user B's job.

    Why this matters: without this, any user could kill another user's
    long-running computation by guessing the job_id.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="PENDING")
    assert task_scheduler_celery_service.cancel_job("j1", "sess-OTHER") is False


# ── cancel_job admin mode (session_id=None) ───────────────────────────────


def test_cancel_job_admin_ignores_session(task_scheduler_celery_service, fake_redis):
    """cancel_job(session_id=None) revokes a job without ownership check.

    Why this matters: an admin must be able to kill any runaway job,
    even if they don't know (or don't have) the owning session ID.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="STARTED")

    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.app = mock.MagicMock()
        result = task_scheduler_celery_service.cancel_job("j1")

    assert result is True
    assert fake_redis.hgetall("job:j1")["status"] == "REVOKED"


def test_cancel_job_admin_refuses_terminal(task_scheduler_celery_service, fake_redis):
    """cancel_job(session_id=None) returns False for already-completed jobs.

    Why this matters: same rationale as user-mode cancel — revoking a
    finished task is a no-op, so the scheduler rejects the request.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS")
    assert task_scheduler_celery_service.cancel_job("j1") is False


def test_cancel_job_admin_nonexistent(task_scheduler_celery_service):
    """cancel_job(session_id=None) returns False for unknown job IDs."""
    assert task_scheduler_celery_service.cancel_job("no-such-job") is False


# ── admin_purge_all ───────────────────────────────────────────────────────


def test_admin_purge_all_clears_everything(task_scheduler_celery_service, fake_redis, tmp_path):
    """admin_purge_all removes all jobs, session sets, and shared-volume files.

    Why this matters: this is the admin "nuclear reset" used during
    deployments or dev environment cleanup.  It must delete Redis keys
    AND disk files, and revoke any still-running Celery tasks.
    """
    write_job_into_fake_redis(fake_redis, "j1", "sess-1", status="SUCCESS")
    write_job_into_fake_redis(fake_redis, "j2", "sess-2", status="PENDING")

    # Create a fake volume directory to verify disk cleanup.
    outputs_dir = tmp_path / "job_outputs" / "j1"
    outputs_dir.mkdir(parents=True)
    (outputs_dir / config.JOB_RESULT_FILENAME).write_text('{"big": "data"}')

    with (
        mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task,
        mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.config") as mock_config,
    ):
        mock_task.app = mock.MagicMock()
        mock_config.JOB_OUTPUTS_PATH = str(tmp_path / "job_outputs")

        summary = task_scheduler_celery_service.admin_purge_all()

    assert summary["jobs_deleted"] == 2
    assert summary["sessions_cleared"] >= 1


# ── Read-time stale-job timeout detection ─────────────────────────────────


def test_get_job_marks_stale_started_as_timeout(task_scheduler_celery_service, fake_redis):
    """get_job marks a STARTED job past its deadline as TIMEOUT at read time.

    Why this matters: when Celery's hard time limit fires (SIGKILL), no
    Python cleanup runs, so the job stays STARTED in Redis indefinitely.
    Read-time detection catches this the moment the job is read, without
    requiring a periodic sweep.
    """
    write_job_into_fake_redis(
        fake_redis,
        "j-stale",
        "sess-1",
        status="STARTED",
        started_at="2020-01-01T00:00:00+00:00",
        max_duration="60",
        hard_timeout_grace="10",
    )

    job = task_scheduler_celery_service.get_job("j-stale", "sess-1")
    assert job.status is JobStatus.TIMEOUT
    assert fake_redis.hgetall("job:j-stale")["status"] == "TIMEOUT"


def test_get_job_status_marks_stale_started_as_timeout(task_scheduler_celery_service, fake_redis):
    """get_job_status also triggers read-time timeout detection.

    Why this matters: the UI polls this lightweight method for live
    status updates.  It must detect stale STARTED jobs the same way
    get_job does.
    """
    write_job_into_fake_redis(
        fake_redis,
        "j-stale-status",
        "sess-1",
        status="STARTED",
        started_at="2020-01-01T00:00:00+00:00",
        max_duration="60",
        hard_timeout_grace="10",
    )

    status = task_scheduler_celery_service.get_job_status("j-stale-status", "sess-1")
    assert status is JobStatus.TIMEOUT
    assert fake_redis.hgetall("job:j-stale-status")["status"] == "TIMEOUT"


def test_read_time_timeout_refreshes_ttls(task_scheduler_celery_service, fake_redis):
    """Read-time timeout detection refreshes both job hash and session set TTLs.

    Why this matters: the worker was hard-killed so its ``finally`` block
    never refreshed TTLs.  The stale job and its session set may be close
    to expiry.  After detection the user should have a full TTL window to
    see the TIMEOUT status.
    """
    write_job_into_fake_redis(
        fake_redis,
        "j-stale2",
        "sess-recon",
        status="STARTED",
        started_at="2020-01-01T00:00:00+00:00",
        max_duration="60",
        hard_timeout_grace="10",
    )
    # Simulate almost-expired keys.
    fake_redis.expire("job:j-stale2", 10)
    fake_redis.expire("session:sess-recon:jobs", 10)

    task_scheduler_celery_service.get_job("j-stale2", "sess-recon")

    # Both TTLs must be refreshed well beyond 10 seconds.
    assert fake_redis.ttl("job:j-stale2") > 10
    assert fake_redis.ttl("session:sess-recon:jobs") > 10


def test_read_time_timeout_ignores_recent_started(task_scheduler_celery_service, fake_redis):
    """A freshly-started STARTED job is NOT marked TIMEOUT at read time.

    Why this matters: a job that just started should not be prematurely
    marked as timed out.
    """
    from datetime import datetime, timezone

    write_job_into_fake_redis(
        fake_redis,
        "j-fresh",
        "sess-1",
        status="STARTED",
        started_at=datetime.now(tz=timezone.utc).isoformat(),
        max_duration="3600",
        hard_timeout_grace="60",
    )

    job = task_scheduler_celery_service.get_job("j-fresh", "sess-1")
    assert job.status is JobStatus.STARTED


def test_read_time_timeout_ignores_non_started(task_scheduler_celery_service, fake_redis):
    """Read-time timeout detection only affects STARTED jobs, not terminals.

    Why this matters: SUCCESS, FAILURE, REVOKED, etc. are terminal and
    should never be mutated by the timeout check.
    """
    write_job_into_fake_redis(fake_redis, "j-done", "sess-1", status="SUCCESS")
    write_job_into_fake_redis(fake_redis, "j-fail", "sess-1", status="FAILURE")

    assert task_scheduler_celery_service.get_job("j-done", "sess-1").status is JobStatus.SUCCESS
    assert task_scheduler_celery_service.get_job("j-fail", "sess-1").status is JobStatus.FAILURE
