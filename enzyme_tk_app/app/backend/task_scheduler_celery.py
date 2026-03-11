"""Celery + Redis implementation of ``TaskScheduler``.

This module is the concrete backend that actually stores job data and
communicates with Celery workers.  The Dash UI never talks to Redis or
Celery directly — it only calls methods on this class via the abstract
``TaskScheduler`` interface.

**How Redis is used:**

*   Each job's metadata (status, timestamps, parameters, result) is stored
    in a Redis *hash* keyed by ``job:<job_id>``.
*   Each user session keeps a Redis *set* of its job IDs, keyed by
    ``session:<session_id>:jobs``.  This lets us quickly list "my jobs"
    without scanning every key in Redis.
*   All keys have a TTL (time-to-live), so old jobs are automatically
    cleaned up after 24 hours.

**How Celery is used:**

*   ``submit_job`` calls ``run_tool_task.apply_async(...)`` to send work
    to a Celery worker process (which may be running in a separate
    container or machine).
*   ``cancel_job`` uses ``celery.control.revoke(...)`` to send a SIGKILL
    signal to the worker running the task.

Redis key schema::

    job:{job_id}              → Hash   (all JobInfo fields)
    session:{session_id}:jobs → Set    (set of job_id strings)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone

import redis as redis_lib

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.backend.task_scheduler import TaskScheduler
from enzyme_tk_app.app.backend.tasks import run_tool_task

logger = logging.getLogger(__name__)

# Terminal statuses — once a job reaches one of these states it is
# considered "done" and will not change again.  Only terminal jobs can
# be deleted by the user (you can't delete a job that is still running).
_TERMINAL_STATUSES = frozenset(
    {
        JobStatus.SUCCESS,
        JobStatus.FAILURE,
        JobStatus.REVOKED,
        JobStatus.TIMEOUT,
    }
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    We always use UTC so that timestamps are comparable regardless of
    which timezone the server or the user is in.
    """
    return datetime.now(tz=timezone.utc).isoformat()


class CeleryTaskScheduler(TaskScheduler):
    """Concrete ``TaskScheduler`` backed by Celery and Redis.

    This is the only class the Dash UI interacts with for job management.
    It stores job metadata in Redis and dispatches computation to Celery
    workers.  You should never instantiate this class directly — use
    ``get_task_scheduler()`` from ``enzyme_tk_app.app.backend`` instead,
    which creates a single shared instance (singleton).

    Args:
        redis_url: Redis connection string.  Defaults to ``config.REDIS_URL``.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        # Create a Redis client.  ``decode_responses=True`` tells the
        # client to return Python strings instead of raw bytes, which
        # makes all downstream code simpler.
        self._redis = redis_lib.Redis.from_url(
            redis_url or config.REDIS_URL,
            decode_responses=True,
        )

    # ── helpers ───────────────────────────────────────────────────────

    def _job_key(self, job_id: str) -> str:  # noqa: PLR6301
        """Return the Redis hash key for *job_id*.

        Every job is stored as a Redis hash at ``job:<uuid>``.  This
        helper keeps the key format in one place so we never mistype it.
        """
        return f"job:{job_id}"

    def _session_key(self, session_id: str) -> str:  # noqa: PLR6301
        """Build the Redis set key that tracks which jobs belong to a session.

        Each anonymous browser session has a UUID (set via a cookie in
        ``session.py``).  We maintain a Redis *set* at
        ``session:<uuid>:jobs`` containing the IDs of every job that
        session has submitted.  This lets ``list_jobs`` quickly return
        only *your* jobs without scanning the entire keyspace.
        """
        return f"session:{session_id}:jobs"

    def _read_job(self, job_id: str) -> JobInfo | None:
        """Read a job hash from Redis and convert it into a ``JobInfo`` object.

        Redis stores everything as strings, so this method parses JSON
        fields (``params``, ``result``) back into Python dicts and wraps
        the status string in the ``JobStatus`` enum.

        Does **not** check session ownership — callers must verify that
        separately (via ``_owns_job``) before returning data to the UI.

        Returns:
            ``JobInfo`` if the key exists in Redis, ``None`` otherwise.
        """
        # ``hgetall`` returns all fields of the Redis hash as a dict.
        # If the key doesn't exist (expired or deleted), it returns {}.
        data = self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None

        # Convert the flat string dict back into a typed JobInfo dataclass.
        # ``params`` and ``result`` are stored as JSON strings in Redis
        # because Redis hashes only support string values.
        return JobInfo(
            job_id=data.get("job_id", job_id),
            tool_slug=data.get("tool_slug", ""),
            status=JobStatus(data.get("status", JobStatus.PENDING.value)),
            session_id=data.get("session_id", ""),
            submitted_at=data.get("submitted_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            params=json.loads(data["params"]) if data.get("params") else {},
            result=json.loads(data["result"]) if data.get("result") else None,
            error=data.get("error"),
            output_log=data.get("output_log", ""),
        )

    def _owns_job(self, job_id: str, session_id: str) -> bool:
        """Return ``True`` if *session_id* owns *job_id*.

        Ownership is enforced so that one user cannot view, cancel, or
        delete another user's jobs.  We check membership of ``job_id``
        in the session's Redis set (``session:<session_id>:jobs``).
        """
        return bool(self._redis.sismember(self._session_key(session_id), job_id))

    # ── Submit & control ─────────────────────────────────────────────

    def submit_job(self, tool_slug: str, params: dict, session_id: str) -> str:
        """Submit a job for asynchronous execution.

        Args:
            tool_slug: URL-safe tool identifier.
            params: JSON-serialisable parameters.
            session_id: Anonymous session UUID.

        Returns:
            A unique ``job_id`` (UUID4 string).
        """
        # 1. Generate a unique ID for this job.
        job_id = str(uuid.uuid4())
        job_key = self._job_key(job_id)
        session_key = self._session_key(session_id)

        # 2. Look up per-tool time limits.
        #    Each tool can declare ``max_duration`` (hard kill after N seconds)
        #    and ``soft_time_limit`` (raise SoftTimeLimitExceeded after N seconds
        #    so the task can clean up gracefully).
        #    We import TOOLS lazily here to avoid a circular import — this
        #    module is imported at app startup, before tools are registered.
        max_duration = config.DEFAULT_MAX_DURATION
        soft_limit: int | None = None
        try:
            from enzyme_tk_app.app.tools import TOOLS  # noqa: PLC0415

            for tool in TOOLS:
                if tool["slug"] == tool_slug:
                    max_duration = tool.get("max_duration", config.DEFAULT_MAX_DURATION)
                    soft_limit = tool.get("soft_time_limit")
                    break
        except Exception:  # noqa: BLE001
            logger.debug("Could not resolve ToolDef for %s — using defaults", tool_slug)

        # Default soft limit = 5 minutes before hard limit, but at least 60s.
        if soft_limit is None:
            soft_limit = max(max_duration - 300, 60)

        submitted_at = _now_iso()

        # 3. Write initial job metadata to Redis as a hash.
        #    At this point the job is PENDING — it hasn't been picked up
        #    by a worker yet.  The worker will update the status to
        #    STARTED and eventually to SUCCESS / FAILURE.
        self._redis.hset(
            job_key,
            mapping={
                "job_id": job_id,
                "tool_slug": tool_slug,
                "status": JobStatus.PENDING.value,
                "session_id": session_id,
                "submitted_at": submitted_at,
                "params": json.dumps(params),
                "output_log": "",
            },
        )
        # Auto-expire the key after 24 hours so old jobs don't pile up.
        self._redis.expire(job_key, config.JOB_TTL_SECONDS)

        # 4. Add this job_id to the session's set so we can later list
        #    "all jobs for this user" efficiently.
        self._redis.sadd(session_key, job_id)
        self._redis.expire(session_key, config.JOB_TTL_SECONDS)

        # 5. Send the task to Celery.  ``apply_async`` puts a message on
        #    the Redis broker queue.  A worker picks it up and calls
        #    ``run_tool_task(**kwargs)`` in a separate process.
        #    We set ``task_id=job_id`` so that the Celery task ID matches
        #    our own job ID.  This is required for ``cancel_job`` to work,
        #    because ``revoke(job_id, ...)`` must target the real Celery
        #    task ID.
        run_tool_task.apply_async(
            kwargs={
                "tool_slug": tool_slug,
                "params": params,
                "session_id": session_id,
                "job_id": job_id,
            },
            task_id=job_id,
            time_limit=max_duration,
            soft_time_limit=soft_limit,
        )

        return job_id

    def cancel_job(self, job_id: str, session_id: str | None = None) -> bool:
        """Cancel / revoke a pending or running job.

        Args:
            job_id: The job to cancel.
            session_id: When provided, ownership is verified (user mode).
                When ``None``, the ownership check is skipped (admin mode).

        Returns:
            ``True`` if successfully revoked.
        """
        # When session_id is given, enforce ownership so regular users
        # can only cancel their own jobs.
        if session_id is not None and not self._owns_job(job_id, session_id):
            return False

        job = self._read_job(job_id)
        if job is None:
            return False

        # A job that has already finished cannot be cancelled.
        if job.status in _TERMINAL_STATUSES:
            return False

        # Tell Celery to kill the worker process running this task.
        # SIGKILL is used (instead of SIGTERM) to guarantee the process
        # stops, even if the task code doesn't handle interrupts.
        run_tool_task.app.control.revoke(job_id, terminate=True, signal="SIGKILL")

        # Immediately mark the job as REVOKED in Redis so the UI shows
        # the updated status without waiting for the worker to report back.
        self._redis.hset(
            self._job_key(job_id),
            mapping={
                "status": JobStatus.REVOKED.value,
                "completed_at": _now_iso(),
            },
        )
        return True

    # ── Query ────────────────────────────────────────────────────────

    def get_job(self, job_id: str, session_id: str) -> JobInfo | None:
        """Retrieve full job details, including the computation result.

        When a tool produces a very large result (> 512 KB), the worker
        saves the full JSON to a file on the shared volume and stores a
        small ``{"_result_ref": "/data/job_outputs/..."}`` pointer in
        Redis instead.  This method detects that pointer and loads the
        full result from disk transparently, so callers always get the
        complete data.

        Returns:
            ``JobInfo`` if found and owned by *session_id*, else ``None``.
        """
        if not self._owns_job(job_id, session_id):
            return None

        job = self._read_job(job_id)
        if job is None:
            return None

        # If the result was too large for Redis, load it from the shared
        # volume (a Docker volume mounted at /data on both web and worker).
        if job.result and "_result_ref" in job.result:
            ref_path = job.result["_result_ref"]
            try:
                with open(ref_path) as fh:
                    job.result = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError):
                logger.warning("Failed to load result from %s for job %s", ref_path, job_id)

        return job

    def get_job_status(self, job_id: str, session_id: str) -> JobStatus | None:
        """Lightweight status check — reads only the status field.

        This is much cheaper than ``get_job`` because it fetches a single
        field from the Redis hash instead of deserialising the entire job
        (which may include large params or output logs).  Use this when
        the UI only needs to update a status badge or progress indicator.

        Returns:
            ``JobStatus`` if found and owned, else ``None``.
        """
        if not self._owns_job(job_id, session_id):
            return None

        # ``hget`` fetches a single field from the hash — O(1) in Redis.
        status_str = self._redis.hget(self._job_key(job_id), "status")
        if status_str is None:
            return None

        return JobStatus(status_str)

    def list_jobs(self, session_id: str) -> list[JobInfo]:
        """List all jobs belonging to *session_id*.

        Reads the session's Redis set to get job IDs, then fetches each
        job's metadata.  Jobs that have expired (TTL reached) are
        silently skipped — the set may contain stale IDs if the hash
        key expired before the set key.
        """
        # ``smembers`` returns all members of the set (the job IDs).
        job_ids = self._redis.smembers(self._session_key(session_id))
        jobs: list[JobInfo] = []
        for jid in job_ids:
            job = self._read_job(jid)
            if job is not None:
                jobs.append(job)
        return jobs

    def list_all_jobs(self) -> list[JobInfo]:
        """List every job across all sessions (admin only).

        Uses ``scan_iter`` to iterate over all ``job:*`` keys without
        blocking Redis (unlike ``KEYS *`` which is O(N) and blocks).
        This is safe for production but should still be used sparingly
        — it's intended for admin dashboards, not regular user queries.
        """
        jobs: list[JobInfo] = []
        for key in self._redis.scan_iter("job:*"):
            # Extract the UUID portion after "job:".
            job_id = key.split(":", 1)[1]
            job = self._read_job(job_id)
            if job is not None:
                jobs.append(job)
        return jobs

    # ── Cleanup ──────────────────────────────────────────────────────

    def delete_job(self, job_id: str, session_id: str) -> bool:
        """Remove a single completed/failed job from Redis.

        Only jobs in a terminal state (SUCCESS, FAILURE, REVOKED, TIMEOUT)
        can be deleted.  PENDING and STARTED jobs must be cancelled first.
        This prevents users from accidentally losing track of running work.

        Returns:
            ``True`` if the job was deleted.
        """
        if not self._owns_job(job_id, session_id):
            return False

        job = self._read_job(job_id)
        if job is None or job.status not in _TERMINAL_STATUSES:
            return False

        # Remove the job hash and its reference from the session set.
        self._redis.delete(self._job_key(job_id))
        self._redis.srem(self._session_key(session_id), job_id)
        return True

    def clear_jobs(self, session_id: str) -> int:
        """Clear all finished jobs for *session_id*.

        This is a bulk "clean up" action — it removes every job that
        has reached a terminal state while leaving running or pending
        jobs untouched.

        Returns:
            Count of jobs removed.
        """
        job_ids = self._redis.smembers(self._session_key(session_id))
        count = 0
        for jid in job_ids:
            job = self._read_job(jid)
            if job is not None and job.status in _TERMINAL_STATUSES:
                self._redis.delete(self._job_key(jid))
                self._redis.srem(self._session_key(session_id), jid)
                count += 1
        return count

    def clear_all_jobs(self) -> int:
        """Clear all finished jobs across every session (admin only).

        Similar to ``clear_jobs`` but operates globally.  Each deleted
        job is also removed from its owning session's set to keep the
        data consistent.

        Returns:
            Count of jobs removed.
        """
        count = 0
        for key in self._redis.scan_iter("job:*"):
            job_id = key.split(":", 1)[1]
            job = self._read_job(job_id)
            if job is not None and job.status in _TERMINAL_STATUSES:
                # Remove from the owning session's set so it doesn't
                # contain stale references to deleted job hashes.
                session_key = self._session_key(job.session_id)
                self._redis.srem(session_key, job_id)
                self._redis.delete(self._job_key(job_id))
                count += 1
        return count

    # ── Admin: deep cleanup ──────────────────────────────────────────

    def purge_all(self) -> dict:
        """Nuclear option: delete ALL jobs, results, and shared-volume files.

        This is intended for admin maintenance (e.g., during deployment
        or when resetting a dev environment).  It:

        1. Kills any still-running Celery tasks.
        2. Deletes every ``job:*`` hash from Redis.
        3. Deletes every ``session:*:jobs`` set from Redis.
        4. Removes all result files from the shared Docker volume.

        Returns:
            Summary dict with counts of deleted resources.
        """
        jobs_deleted = 0
        sessions_cleared = 0
        tasks_revoked = 0

        # Step 1 & 2: iterate over every job, revoke if still active,
        # then delete the Redis hash regardless.
        for key in self._redis.scan_iter("job:*"):
            job_id = key.split(":", 1)[1]
            status_str = self._redis.hget(key, "status")
            if status_str in {JobStatus.PENDING.value, JobStatus.STARTED.value}:
                try:
                    run_tool_task.app.control.revoke(job_id, terminate=True, signal="SIGKILL")
                    tasks_revoked += 1
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to revoke task %s", job_id)

            self._redis.delete(key)
            jobs_deleted += 1

        # Step 3: delete every session-tracking set.
        for key in self._redis.scan_iter("session:*:jobs"):
            self._redis.delete(key)
            sessions_cleared += 1

        # Step 4: remove large result files from the shared Docker volume
        # (``/data/job_outputs/``).  These are the files created by
        # ``tasks._store_result()`` when a result exceeds 512 KB.
        volume_bytes_freed = 0
        volume_files_deleted = 0
        outputs_dir = os.path.join(config.SHARED_VOLUME_PATH, "job_outputs")
        if os.path.isdir(outputs_dir):
            for dirpath, _dirnames, filenames in os.walk(outputs_dir):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    try:
                        volume_bytes_freed += os.path.getsize(fpath)
                        volume_files_deleted += 1
                    except OSError:
                        pass
            shutil.rmtree(outputs_dir, ignore_errors=True)

        return {
            "jobs_deleted": jobs_deleted,
            "sessions_cleared": sessions_cleared,
            "tasks_revoked": tasks_revoked,
            "volume_bytes_freed": volume_bytes_freed,
            "volume_files_deleted": volume_files_deleted,
        }
