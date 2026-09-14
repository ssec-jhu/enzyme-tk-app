"""Integration tests for ``CeleryTaskScheduler`` against a real Redis server.

These tests verify that the scheduler works with an actual Redis instance,
catching issues that ``fakeredis`` cannot reproduce — for example, network
serialization changes, Lua script behaviour, or server-version-specific
command flags.

Requirements:
    A running Redis instance.  By default, tests connect to
    ``redis://localhost:6380/15`` (port 6380 matches docker-compose's
    published port; database 15 avoids collisions with development data).

    Override with the ``REDIS_TEST_URL`` environment variable::

        REDIS_TEST_URL=redis://my-host:6379/15 tox run -e test-integration

Run:
    These tests are marked ``@pytest.mark.integration`` and are **skipped**
    by default.  Use the dedicated tox environment::

        tox run -e test-integration

    Or run directly with pytest::

        pytest -m integration
"""

import os
import uuid
from unittest import mock

import pytest
import redis

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.backend.task_scheduler_celery import CeleryTaskScheduler

# ── Configuration ────────────────────────────────────────────────────────────
# Database 15 is used to avoid interfering with dev data on db 0.
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380/15")

# All integration tests share this marker, so they can be selected/excluded.
pytestmark = pytest.mark.integration


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def real_redis():
    """Connect to a real Redis and flush the test database before each test.

    If Redis is not reachable, the test is skipped with a clear message
    instead of failing with a connection error.
    """
    client = redis.Redis.from_url(REDIS_TEST_URL, decode_responses=True)
    try:
        client.ping()
    except redis.ConnectionError:
        pytest.skip(f"Redis not reachable at {REDIS_TEST_URL}")

    # Start each test with a clean database.
    client.flushdb()
    yield client
    # Clean up after the test as well.
    client.flushdb()


@pytest.fixture()
def real_service(real_redis):
    """CeleryTaskScheduler wired to the real Redis instance.

    Uses ``__new__`` to skip ``__init__`` (which would call
    ``redis.Redis.from_url`` again).  We inject the already-connected
    client directly.
    """
    svc = CeleryTaskScheduler.__new__(CeleryTaskScheduler)
    svc._redis = real_redis
    return svc


def write_job_into_real_redis_for_testing(real_redis, job_id, session_id, status="PENDING", **extra):
    """Insert a job directly into Redis for test setup."""
    mapping = {
        "job_id": job_id,
        "tool_slug": "test-tool",
        "status": status,
        "session_id": session_id,
        "submitted_at": "2025-01-01T00:00:00+00:00",
        "params": "{}",
        **extra,
    }
    real_redis.hset(f"job:{job_id}", mapping=mapping)
    real_redis.sadd(f"session:{session_id}:jobs", job_id)


# ── Round-trip: submit → get → delete ────────────────────────────────────────


def test_submit_and_retrieve_job(real_service, real_redis):
    """A submitted job can be retrieved with all fields intact.

    Why this matters: this is the core round-trip — submit writes to Redis,
    get_job reads it back.  This verifies hash serialization, set membership,
    and deserialization through real Redis, not an in-memory fake.
    """
    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.apply_async = mock.MagicMock()
        job_id = real_service.submit_job("reaction-similarity", {"smiles": "CCO"}, "sess-int-1")

    # Verify it's a valid UUID.
    uuid.UUID(job_id)

    # Retrieve and verify fields.
    job = real_service.get_job(job_id, "sess-int-1")
    assert isinstance(job, JobInfo)
    assert job.status is JobStatus.PENDING
    assert job.tool_slug == "reaction-similarity"
    assert job.job_id == job_id


def test_delete_removes_from_redis(real_service, real_redis):
    """delete_job removes both the hash key and the session-set entry.

    Why this matters: verifies that Redis DEL and SREM work correctly
    against the real server.  A mismatch between the two would orphan
    references.
    """
    write_job_into_real_redis_for_testing(real_redis, "del-1", "sess-1", status="SUCCESS")

    assert real_service.delete_job("del-1", "sess-1") is True
    # Hash must be gone.
    assert real_redis.hgetall("job:del-1") == {}
    # Session set must not reference it.
    assert not real_redis.sismember("session:sess-1:jobs", "del-1")


# ── Session isolation ────────────────────────────────────────────────────────


def test_session_isolation_real_redis(real_service, real_redis):
    """Jobs are invisible to sessions that don't own them.

    Why this matters: session isolation is a security boundary.  Testing
    it against real Redis ensures SISMEMBER returns the correct boolean
    value through the wire protocol.
    """
    write_job_into_real_redis_for_testing(real_redis, "secret-job", "sess-owner")

    # Owner can see it.
    assert real_service.get_job("secret-job", "sess-owner") is not None
    # Stranger cannot.
    assert real_service.get_job("secret-job", "sess-stranger") is None


# ── list_jobs with real scan ──────────────────────────────────────────────────


def test_list_jobs_real_scan(real_service, real_redis):
    """list_jobs correctly filters by session using real SMEMBERS + HGETALL.

    Why this matters: SMEMBERS returns a Python set from the wire protocol.
    This test verifies that the scheduler correctly iterates over it and
    hydrates each job.
    """
    write_job_into_real_redis_for_testing(real_redis, "j1", "sess-A", status="SUCCESS")
    write_job_into_real_redis_for_testing(real_redis, "j2", "sess-A", status="FAILURE")
    write_job_into_real_redis_for_testing(real_redis, "j3", "sess-B", status="PENDING")

    jobs_a = real_service.list_jobs("sess-A")
    assert len(jobs_a) == 2
    assert {j.job_id for j in jobs_a} == {"j1", "j2"}


def test_admin_list_all_jobs_real_scan(real_service, real_redis):
    """admin_list_all_jobs uses SCAN to find all ``job:*`` keys.

    Why this matters: SCAN iteration is cursor-based on real Redis.
    This catches any issues with the scan_iter pattern matching.
    """
    write_job_into_real_redis_for_testing(real_redis, "x1", "sess-1")
    write_job_into_real_redis_for_testing(real_redis, "x2", "sess-2")

    all_jobs = real_service.admin_list_all_jobs()
    assert len(all_jobs) == 2


# ── clear_jobs ────────────────────────────────────────────────────────────────


def test_clear_jobs_real_redis(real_service, real_redis):
    """clear_jobs removes terminal jobs and preserves running ones.

    Why this matters: bulk deletion involves multiple DEL + SREM calls
    in sequence.  This test verifies atomicity isn't needed (each
    deletion is independent) and that the running job survives.
    """
    write_job_into_real_redis_for_testing(real_redis, "done1", "sess-1", status="SUCCESS")
    write_job_into_real_redis_for_testing(real_redis, "done2", "sess-1", status="FAILURE")
    write_job_into_real_redis_for_testing(real_redis, "running", "sess-1", status="STARTED")

    count = real_service.clear_jobs("sess-1")
    assert count == 2
    # Running job must still exist.
    assert real_redis.hgetall("job:running") != {}
    # Cleared jobs must be gone.
    assert real_redis.hgetall("job:done1") == {}


# ── TTL / expiry ─────────────────────────────────────────────────────────────


def test_submit_sets_ttl(real_service, real_redis):
    """Submitted jobs get a Redis TTL (real EXPIRE command).

    Why this matters: TTL expiry is the automatic cleanup mechanism.
    This verifies that ``expire()`` was actually called and the key
    has a positive TTL — something fakeredis cannot truly validate
    since it doesn't run an eviction loop.

    Also asserts the session set gets a real TTL from this first-ever
    ``expire()`` call in ``submit_job`` (which deliberately does NOT use
    ``gt=True`` — see the comment above that call). fakeredis does not
    reproduce the real-Redis edge case where ``gt=True`` on a persistent
    (no-TTL) key silently no-ops, so a regression here (someone adding
    ``gt=True`` to that specific call) would only be caught against a
    real Redis server, not fakeredis.
    """
    with mock.patch("enzyme_tk_app.app.backend.task_scheduler_celery.run_tool_task") as mock_task:
        mock_task.apply_async = mock.MagicMock()
        job_id = real_service.submit_job("test-tool", {}, "sess-ttl")

    # Redis TTL returns -1 if no expiry, -2 if key doesn't exist,
    # or a positive integer for the remaining seconds.
    ttl = real_redis.ttl(f"job:{job_id}")
    assert ttl > 0, f"Expected positive TTL, got {ttl}"

    session_ttl = real_redis.ttl("session:sess-ttl:jobs")
    assert session_ttl > 0, f"Expected positive session-set TTL, got {session_ttl}"
