"""Tests for backend data models — ``JobStatus`` enum and ``JobInfo`` dataclass."""

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus

# ── JobStatus enum ────────────────────────────────────────────────────────


def test_job_status_members():
    """JobStatus has exactly the six expected lifecycle states.

    Why this matters: the Celery worker and Redis both store status as a
    string.  If someone accidentally adds or removes a member, existing
    jobs in Redis would fail to deserialise.  This test catches that.
    """
    expected = {"PENDING", "STARTED", "SUCCESS", "FAILURE", "REVOKED", "TIMEOUT"}
    actual = {s.name for s in JobStatus}
    assert actual == expected


def test_job_status_values_match_names():
    """Each member's .value equals its .name (e.g. JobStatus.PENDING.value == "PENDING").

    Why this matters: throughout the backend we reconstruct the enum from
    a Redis string via ``JobStatus(string_value)``.  This only works if
    .value == .name.  If someone changed a value to e.g. "pending"
    (lowercase), every Redis lookup would break with a ValueError.
    """
    for member in JobStatus:
        assert member.value == member.name


# ── JobInfo dataclass ─────────────────────────────────────────────────────


def test_job_info_minimal_construction():
    """JobInfo can be built with only the required fields; optional fields get safe defaults.

    Why this matters: ``_read_job()`` in the scheduler builds JobInfo from
    a Redis hash that may be missing optional fields (e.g. a PENDING job
    has no ``started_at``).  This test ensures the defaults are sensible
    (None for timestamps, empty dict for params, empty string for logs)
    so the UI never crashes on a partially-filled job.
    """
    job = JobInfo(
        job_id="abc-123",
        tool_slug="reaction-similarity",
        status=JobStatus.PENDING,
        session_id="sess-1",
        submitted_at="2025-01-01T00:00:00+00:00",
    )
    assert job.job_id == "abc-123"
    assert job.status is JobStatus.PENDING
    # All optional fields should have safe defaults:
    assert job.started_at is None
    assert job.completed_at is None
    assert job.params == {}
    assert job.result is None
    assert job.error is None
    assert job.output_log == ""


def test_job_info_full_construction():
    """JobInfo accepts and stores all optional fields correctly.

    Why this matters: a completed SUCCESS job will have every field
    populated — timestamps, result dict, captured output.  This test
    confirms the dataclass wiring doesn't silently drop any field,
    which would cause the results page to show blank data.
    """
    job = JobInfo(
        job_id="xyz-789",
        tool_slug="substrate-product-similarity",
        status=JobStatus.SUCCESS,
        session_id="sess-2",
        submitted_at="2025-01-01T00:00:00+00:00",
        started_at="2025-01-01T00:00:01+00:00",
        completed_at="2025-01-01T00:00:05+00:00",
        params={"smiles": "CCO"},
        result={"matches": [1, 2, 3]},
        error=None,
        output_log="Processing...\nDone.",
    )
    assert job.result == {"matches": [1, 2, 3]}
    assert job.output_log == "Processing...\nDone."
