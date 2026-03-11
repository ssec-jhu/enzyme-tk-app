"""Abstract contract for task scheduling backends.

The ``TaskScheduler`` ABC is the **sole interface** between the Dash
UI layer and any task-scheduling infrastructure.  All Dash callbacks and
future pages import ONLY this ABC plus ``JobInfo`` / ``JobStatus``.

Never import Celery, Redis, or any backend-specific module in UI code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus


class TaskScheduler(ABC):
    """Contract between the Dash UI layer and any task-scheduling backend.

    Implementations must provide concrete versions of every abstract method.
    The ABC ships one concrete helper (``_verify_ownership``) that all
    implementations inherit.

    **Job lifecycle methods at a glance:**

    +-----------------+--------------------+-----------------------------+-------+
    | Method          | Scope              | Affected statuses           | Role  |
    +=================+====================+=============================+=======+
    | ``cancel_job``  | One job            | PENDING, STARTED → REVOKED | Both  |
    +-----------------+--------------------+-----------------------------+-------+
    | ``delete_job``  | One job            | Terminal only *             | User  |
    +-----------------+--------------------+-----------------------------+-------+
    | ``clear_jobs``  | All jobs / session | Terminal only *             | User  |
    +-----------------+--------------------+-----------------------------+-------+
    | ``clear_all_jobs`` | All jobs / all  | Terminal only *             | Admin |
    +-----------------+--------------------+-----------------------------+-------+
    | ``purge_all``   | Everything         | ALL (+ volume files)        | Admin |
    +-----------------+--------------------+-----------------------------+-------+

    (*) Terminal statuses: SUCCESS, FAILURE, REVOKED, TIMEOUT.

    - **cancel** stops a live job (PENDING/STARTED) and moves it to REVOKED.
      It does NOT remove the job record — the user can still see it.
      Pass ``session_id`` for user-scoped ownership checks, or ``None``
      to skip the check (admin mode).
    - **delete** removes a single job record, but only if it has already
      reached a terminal state.  A running job must be cancelled first.
    - **clear** is a bulk delete of all terminal jobs for one session
      (``clear_jobs``) or across every session (``clear_all_jobs``).
      Running/pending jobs are never touched.
    - **purge** is the dangerous zone option: it revokes every active task,
      deletes ALL job records regardless of status, wipes session sets,
      and removes result files from the shared Docker volume.
    """

    # ── Submit & control ─────────────────────────────────────────────

    @abstractmethod
    def submit_job(self, tool_slug: str, params: dict, session_id: str) -> str:
        """Submit a job for asynchronous execution.

        Args:
            tool_slug: URL-safe tool identifier (e.g. ``"reaction-similarity"``).
            params: Arbitrary JSON-serialisable parameters from the modal form.
            session_id: Anonymous session UUID that owns this job.

        Returns:
            A unique ``job_id`` string (UUID4).
        """

    @abstractmethod
    def cancel_job(self, job_id: str, session_id: str | None = None) -> bool:
        """Cancel / revoke a pending or running job.

        Args:
            job_id: The job to cancel.
            session_id: When provided, ownership is verified (user mode).
                When ``None``, the ownership check is skipped (admin mode).

        Returns:
            ``True`` if successfully revoked, ``False`` otherwise.
        """

    # ── Query ────────────────────────────────────────────────────────

    @abstractmethod
    def get_job(self, job_id: str, session_id: str) -> JobInfo | None:
        """Retrieve full job details (status, result, logs).

        Returns ``None`` if not found **or** not owned by *session_id*.
        """

    @abstractmethod
    def get_job_status(self, job_id: str, session_id: str) -> JobStatus | None:
        """Lightweight status check — reads only the status field.

        More efficient than ``get_job()`` for UI polling intervals.
        Returns ``None`` if not found or not owned by *session_id*.
        """

    @abstractmethod
    def list_jobs(self, session_id: str) -> list[JobInfo]:
        """List all jobs belonging to *session_id*."""

    @abstractmethod
    def list_all_jobs(self) -> list[JobInfo]:
        """List every job across all sessions (admin use only)."""

    # ── Cleanup ──────────────────────────────────────────────────────

    @abstractmethod
    def delete_job(self, job_id: str, session_id: str) -> bool:
        """Remove a single completed/failed job from the user's list.

        Returns ``True`` if deleted, ``False`` if not found, not owned,
        or still running (PENDING / STARTED jobs are **not** deleted).
        """

    @abstractmethod
    def clear_jobs(self, session_id: str) -> int:
        """Clear all finished jobs for a session.

        Removes jobs with terminal status (SUCCESS, FAILURE, REVOKED,
        TIMEOUT).  PENDING and STARTED jobs are left untouched.

        Returns:
            Count of jobs removed.
        """

    @abstractmethod
    def clear_all_jobs(self) -> int:
        """Clear all finished jobs across every session (admin only).

        Same rules as ``clear_jobs()`` applied globally.

        Returns:
            Count of jobs removed.
        """

    # ── Admin: deep cleanup ──────────────────────────────────────────

    @abstractmethod
    def purge_all(self) -> dict:
        """Complete deep cleanup of ALL jobs, results, and volume data.

        Removes:
        - ALL ``job:{job_id}`` hashes from Redis (regardless of status)
        - ALL ``session:{session_id}:jobs`` sets from Redis
        - ALL files under ``JOB_OUTPUTS_PATH``
        - Revokes any currently running or pending Celery tasks

        Returns:
            Summary dict, e.g.::

                {"jobs_deleted": 42, "sessions_cleared": 15,
                 "tasks_revoked": 3, "volume_bytes_freed": 1073741824,
                 "volume_files_deleted": 200}
        """

    # ── Shared (concrete) ────────────────────────────────────────────

    def _verify_ownership(self, job_id: str, session_id: str) -> bool:
        """Check whether *session_id* owns *job_id*.

        Concrete method inherited by all implementations.

        Args:
            job_id: Job to check.
            session_id: Expected owner.

        Returns:
            ``True`` if the job exists and belongs to the session.
        """
        job = self.get_job(job_id, session_id)
        return job is not None and job.session_id == session_id
