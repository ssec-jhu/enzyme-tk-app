"""Multi-tool, multi-session integration test.

One end-to-end test that walks through the full lifecycle:
    1. Two sessions each submit a different tool ("fast-tool" / "slow-tool").
    2. Each session retrieves its own job and gets the correct result.
    3. Sessions cannot see, cancel, or delete each other's jobs.
    4. Bulk operations (list_jobs, clear_jobs) respect session scope.
    5. Mixed statuses (SUCCESS, STARTED, FAILURE) behave correctly.
"""

import json
from unittest import mock

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.tests.conftest import write_job_into_fake_redis

# Canonical result dicts — one per mock tool.
FAST_RESULT = {"tool": "fast", "duration": 2, "input": "A"}
SLOW_RESULT = {"tool": "slow", "duration": 5, "input": "B"}
FAST_RESULT_JSON = json.dumps(FAST_RESULT)
SLOW_RESULT_JSON = json.dumps(SLOW_RESULT)


def test_multitool_multisession_lifecycle(task_scheduler_celery_service, fake_redis):
    """Full integration test: two tools, two sessions, complete lifecycle.

    Why this matters: real-world usage has multiple users concurrently
    running different tools.  This single test walks through every
    scheduler interaction to verify result routing, session isolation,
    status queries, cancel / delete ownership, and bulk cleanup —
    all in one cohesive scenario.
    """
    svc = task_scheduler_celery_service

    # ── Step 1: Seed jobs ────────────────────────────────────────────
    # Session A submits fast-tool (SUCCESS) and slow-tool (STARTED).
    # Session B submits fast-tool (FAILURE).
    write_job_into_fake_redis(
        fake_redis,
        "j-a1",
        "sess-A",
        status="SUCCESS",
        tool_slug="fast-tool",
        result=FAST_RESULT_JSON,
        params='{"input": "A"}',
    )
    write_job_into_fake_redis(
        fake_redis,
        "j-a2",
        "sess-A",
        status="STARTED",
        tool_slug="slow-tool",
    )
    write_job_into_fake_redis(
        fake_redis,
        "j-b1",
        "sess-B",
        status="FAILURE",
        tool_slug="fast-tool",
        error="Something went wrong",
    )

    # ── Step 2: Retrieve results — correct tool data per session ────
    job_a1 = svc.get_job("j-a1", "sess-A")
    assert isinstance(job_a1, JobInfo)
    assert job_a1.tool_slug == "fast-tool"
    assert job_a1.result == FAST_RESULT
    assert job_a1.params == {"input": "A"}

    job_b1 = svc.get_job("j-b1", "sess-B")
    assert isinstance(job_b1, JobInfo)
    assert job_b1.tool_slug == "fast-tool"
    assert job_b1.status is JobStatus.FAILURE
    assert job_b1.error == "Something went wrong"

    # ── Step 3: get_job_status returns correct enum ──────────────────
    assert svc.get_job_status("j-a1", "sess-A") is JobStatus.SUCCESS
    assert svc.get_job_status("j-a2", "sess-A") is JobStatus.STARTED
    assert svc.get_job_status("j-b1", "sess-B") is JobStatus.FAILURE

    # ── Step 4: Session isolation — cross-session access blocked ─────
    # Session B cannot see session A's jobs (and vice versa).
    assert svc.get_job("j-a1", "sess-B") is None
    assert svc.get_job_status("j-a1", "sess-B") is None
    assert svc.get_job("j-b1", "sess-A") is None

    # ── Step 5: list_jobs scoped per session; list_all sees everything ─
    jobs_a = svc.list_jobs("sess-A")
    jobs_b = svc.list_jobs("sess-B")
    all_jobs = svc.admin_list_all_jobs()

    assert len(jobs_a) == 2
    assert {j.job_id for j in jobs_a} == {"j-a1", "j-a2"}
    assert len(jobs_b) == 1
    assert jobs_b[0].job_id == "j-b1"
    assert len(all_jobs) == 3

    # ── Step 6: Cross-session delete / cancel blocked ────────────────
    # Session A cannot delete session B's failed job.
    assert svc.delete_job("j-b1", "sess-A") is False
    assert fake_redis.hgetall("job:j-b1") != {}

    # Session B cannot cancel session A's running job.
    assert svc.cancel_job("j-a2", "sess-B") is False
    assert fake_redis.hgetall("job:j-a2")["status"] == "STARTED"

    # ── Step 7: Owner can cancel their own running job ───────────────
    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.app = mock.MagicMock()
        assert svc.cancel_job("j-a2", "sess-A") is True
    assert fake_redis.hgetall("job:j-a2")["status"] == "REVOKED"

    # ── Step 8: clear_jobs removes only own terminal jobs ────────────
    # Session A now has: j-a1 (SUCCESS) + j-a2 (REVOKED) — both terminal.
    cleared = svc.clear_jobs("sess-A")
    assert cleared == 2
    assert fake_redis.hgetall("job:j-a1") == {}
    assert fake_redis.hgetall("job:j-a2") == {}

    # Session B's FAILURE job must be completely untouched.
    assert fake_redis.hgetall("job:j-b1") != {}
    remaining_b = svc.list_jobs("sess-B")
    assert len(remaining_b) == 1
    assert remaining_b[0].status is JobStatus.FAILURE

    # ── Step 9: Owner can delete their own terminal job ──────────────
    assert svc.delete_job("j-b1", "sess-B") is True
    assert fake_redis.hgetall("job:j-b1") == {}
    assert svc.list_jobs("sess-B") == []
