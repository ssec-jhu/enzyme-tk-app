"""Data models for the backend job scheduling system.

Defines the canonical job lifecycle states (``JobStatus``) and the data
transfer object (``JobInfo``) shared between the UI and backend layers.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class JobStatus(enum.Enum):
    """Lifecycle states a job can occupy.

    State transitions::

        PENDING  ──▶  STARTED  ──▶  SUCCESS
                                 ──▶  FAILURE
                                 ──▶  TIMEOUT
                 ──▶  REVOKED  (cancel before or during execution)
    """

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"
    TIMEOUT = "TIMEOUT"


@dataclass
class JobInfo:
    """Immutable snapshot of a job's metadata and result.

    Attributes:
        job_id: Unique identifier (UUID4 string).
        tool_slug: URL-safe slug of the tool that owns this job.
        status: Current lifecycle state.
        session_id: Anonymous session that submitted the job.
        submitted_at: ISO-8601 timestamp when the job was submitted.
        started_at: ISO-8601 timestamp when the worker began execution,
            or ``None`` if not yet started.
        completed_at: ISO-8601 timestamp when the job reached a terminal
            state, or ``None`` if still running.
        params: Input parameters as submitted by the user.
        result: Output dict from ``compute.run()``, or ``None``.
        error: Traceback string on failure, or ``None``.
        output_log: Captured stdout/stderr from the worker process.
    """

    job_id: str
    tool_slug: str
    status: JobStatus
    session_id: str
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    output_log: str = ""


# Terminal statuses — once a job reaches one of these states it is
# considered "done" and will not change again.  Only terminal jobs can
# be deleted by the user (you can't delete a job that is still running).
# This constant is the single source of truth; CeleryTaskScheduler
# imports it from here.
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCESS,
        JobStatus.FAILURE,
        JobStatus.REVOKED,
        JobStatus.TIMEOUT,
    }
)
