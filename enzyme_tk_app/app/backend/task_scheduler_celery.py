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
*   All keys have a TTL computed by ``celery_app.effective_ttl()`` —
    ``max_duration + grace + JOB_TTL_SECONDS`` — so keys never expire
    mid-execution and are cleaned up after the retention period.

**How Celery is used:**

*   ``submit_job`` calls ``run_tool_task.apply_async(...)`` to send work
    to a Celery worker process (which may be running in a separate
    container or machine).  Each tool has a single ``max_duration``
    timeout.  Celery's *soft* time limit is set to ``max_duration``
    (raises ``SoftTimeLimitExceeded``, caught by the task to record
    ``TIMEOUT``) and the *hard* limit is ``max_duration + grace`` as
    a safety net.
*   ``cancel_job`` uses ``celery.control.revoke(...)`` to send a SIGKILL
    signal to the worker running the task.

**Read-time stale-job detection:**

When Celery's hard time limit fires it sends SIGKILL, killing the worker
instantly — no Python cleanup runs, so the job stays ``STARTED`` in Redis.
Rather than requiring a periodic sweep, this module detects stale jobs
*at read time*: every call to ``_read_job`` or ``get_job_status`` checks
whether a ``STARTED`` job has exceeded its deadline and, if so, transitions
it to ``TIMEOUT`` on the spot.  The deadline is computed from
``max_duration`` and ``hard_timeout_grace`` fields stored in the Redis hash
at submit time, making the check independent of the application lifecycle
or the TOOLS registry.

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
from enzyme_tk_app.app.backend.celery_app import (
    DEFAULT_MAX_DURATION,
    HARD_TIMEOUT_GRACE_SECONDS,
    effective_ttl,
)
from enzyme_tk_app.app.backend.models import TERMINAL_STATUSES, JobInfo, JobStatus
from enzyme_tk_app.app.backend.task_scheduler import TaskScheduler
from enzyme_tk_app.app.backend.tasks import run_tool_task

logger = logging.getLogger(__name__)

# Buffer (seconds) added on top of the hard-kill deadline when detecting
# stale STARTED jobs at read time.  Accounts for minor clock drift
# between the web and worker containers.  Kept small because read-time
# detection does not suffer from periodic-scheduling delays.
_STALE_JOB_BUFFER_SECONDS = 30


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

    @staticmethod
    def _delete_job_outputs(job_id: str) -> None:
        """Remove a job's offloaded result + log files from the shared volume.

        The worker writes a job's ``result.json`` and ``output_log.txt`` under
        ``JOB_OUTPUTS_PATH/<job_id>/``.  This helper deletes that directory tree
        so disk space is reclaimed when a job is deleted.
        """
        output_dir = config.job_output_dir(job_id)
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)

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

        # Read-time stale-job detection: if the job is STARTED past its
        # deadline, transition it to TIMEOUT before returning.
        if self._is_timed_out(data):
            data = self._mark_timed_out(self._job_key(job_id), data)

        # Convert the flat string dict back into a typed JobInfo dataclass.
        # ``params`` and ``result`` are stored as JSON strings in Redis
        # because Redis hashes only support string values.
        raw_status = data.get("status", JobStatus.PENDING.value)
        try:
            status = JobStatus(raw_status)
        except ValueError:
            logger.warning("Unknown job status %r for job %s — defaulting to FAILURE", raw_status, job_id)
            status = JobStatus.FAILURE
        return JobInfo(
            job_id=data.get("job_id", job_id),
            tool_slug=data.get("tool_slug", ""),
            status=status,
            session_id=data.get("session_id", ""),
            submitted_at=data.get("submitted_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            params=json.loads(data["params"]) if data.get("params") else {},
            result=json.loads(data["result"]) if data.get("result") else None,
            error=data.get("error"),
            ip_address=data.get("ip_address", ""),
        )

    def _owns_job(self, job_id: str, session_id: str) -> bool:
        """Return ``True`` if *session_id* owns *job_id*.

        Ownership is enforced so that one user cannot view, cancel, or
        delete another user's jobs.  We check membership of ``job_id``
        in the session's Redis set (``session:<session_id>:jobs``).
        """
        return bool(self._redis.sismember(self._session_key(session_id), job_id))

    @staticmethod
    def _is_timed_out(data: dict) -> bool:
        """Return ``True`` if a STARTED job has exceeded its deadline.

        Pure decision function — reads only the values in *data* and
        has no side effects.  Callers are responsible for writing the
        TIMEOUT status back to Redis when this returns ``True``.
        """
        if data.get("status") != JobStatus.STARTED.value or not data.get("started_at"):
            return False

        max_dur = int(data.get("max_duration") or DEFAULT_MAX_DURATION)
        grace = int(data.get("hard_timeout_grace") or HARD_TIMEOUT_GRACE_SECONDS)
        elapsed = (datetime.now(tz=timezone.utc) - datetime.fromisoformat(data["started_at"])).total_seconds()
        return elapsed > max_dur + grace + _STALE_JOB_BUFFER_SECONDS

    def _mark_timed_out(self, job_key: str, data: dict) -> dict:
        """Write TIMEOUT status to Redis and return the updated *data* dict.

        Call only after ``_is_timed_out(data)`` returns ``True``.
        """
        update = {
            "status": JobStatus.TIMEOUT.value,
            "completed_at": _now_iso(),
            "error": "Job exceeded the maximum allowed duration and was terminated by the system.",
        }
        self._redis.hset(job_key, mapping=update)
        ttl = effective_ttl(
            int(data.get("max_duration") or DEFAULT_MAX_DURATION),
            int(data.get("hard_timeout_grace") or HARD_TIMEOUT_GRACE_SECONDS),
        )
        self._redis.expire(job_key, ttl)
        if data.get("session_id"):
            self._redis.expire(self._session_key(data["session_id"]), ttl)

        logger.info("Read-time timeout: job %s → TIMEOUT", data.get("job_id", "?"))
        data.update(update)
        return data

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

        # Extract IP and Browser from Flask request context if available
        ip_address = ""
        try:
            from flask import has_request_context, request

            # attempt to extract the IP address from the Flask request context
            if has_request_context():
                ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
                if ip_address:
                    ip_address = ip_address.split(",")[0].strip()
        except Exception as e:
            logger.debug("Could not extract request metadata: %s", e)

        # 2. Look up per-tool timeout.
        #    Each tool can declare ``max_duration`` — the number of seconds
        #    the computation is allowed to run.  Celery's *soft* time limit
        #    is set to ``max_duration`` (raises ``SoftTimeLimitExceeded``)
        #    and the *hard* time limit is ``max_duration + grace`` so the
        #    handler has time to write TIMEOUT to Redis before SIGKILL.
        #    We import TOOLS lazily here to avoid a circular import — this
        #    module is imported at app startup, before tools are registered.
        max_duration = DEFAULT_MAX_DURATION
        try:
            from enzyme_tk_app.app.tools import TOOLS  # noqa: PLC0415

            for tool in TOOLS:
                if tool["slug"] == tool_slug:
                    max_duration = tool.get("max_duration", DEFAULT_MAX_DURATION)
                    break
        except Exception:  # noqa: BLE001
            logger.debug("Could not resolve ToolDef for %s — using defaults", tool_slug)

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
                "ip_address": ip_address,
                # Persist timeout thresholds so read-time stale-job
                # detection can compute the deadline without consulting
                # the TOOLS registry or application lifecycle.
                "max_duration": str(max_duration),
                "hard_timeout_grace": str(HARD_TIMEOUT_GRACE_SECONDS),
            },
        )
        # Expire the key after the full execution window + retention
        # period so the hash never vanishes while the job is running.
        job_ttl = effective_ttl(max_duration)
        self._redis.expire(job_key, job_ttl)

        # 4. Add this job_id to the session's set so we can later list
        #    "all jobs for this user" efficiently.
        self._redis.sadd(session_key, job_id)
        self._redis.expire(session_key, job_ttl)

        # 5. Send the task to Celery.  ``apply_async`` puts a message on
        #    the Redis broker queue.  A worker picks it up and calls
        #    ``run_tool_task(**kwargs)`` in a separate process.
        #    We set ``task_id=job_id`` so that the Celery task ID matches
        #    our own job ID.  This is required for ``cancel_job`` to work,
        #    because ``revoke(job_id, ...)`` must target the real Celery
        #    task ID.
        #    ``soft_time_limit`` = user-visible timeout (raises exception).
        #    ``time_limit``      = hard kill = timeout + grace buffer.
        hard_limit = max_duration + HARD_TIMEOUT_GRACE_SECONDS
        run_tool_task.apply_async(
            kwargs={
                "tool_slug": tool_slug,
                "params": params,
                "session_id": session_id,
                "job_id": job_id,
            },
            task_id=job_id,
            time_limit=hard_limit,
            soft_time_limit=max_duration,
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
        if job.status in TERMINAL_STATUSES:
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

        # Refresh TTLs so the user has a full window to see the REVOKED
        # status.  The worker was SIGKILL'd, so its ``finally`` block
        # never ran — the previous TTL may be almost exhausted.
        job_key = self._job_key(job_id)
        max_dur_str = self._redis.hget(job_key, "max_duration")
        ttl = effective_ttl(int(max_dur_str or DEFAULT_MAX_DURATION))
        self._redis.expire(job_key, ttl)
        if session_id is not None:
            self._redis.expire(self._session_key(session_id), ttl)
        else:
            # Admin mode — look up the session from the job hash.
            self._redis.expire(self._session_key(job.session_id), ttl)
        return True

    # ── Query ────────────────────────────────────────────────────────

    def get_job(self, job_id: str, session_id: str) -> JobInfo | None:
        """Retrieve full job details, including the computation result and log.

        Returns:
            ``JobInfo`` if found and owned by *session_id*, else ``None``.
        """
        if not self._owns_job(job_id, session_id):
            return None

        job = self._read_job(job_id)
        if job is None:
            return None

        # Both the result and log files live under this job's directory on the
        # shared volume (a Docker volume mounted at /data on both web + worker).
        job_dir = config.job_output_dir(job_id)

        # Load the result from the shared volume if the Redis hash
        # contains a ``_result_ref``.
        if job.result and "_result_ref" in job.result:
            ref_path = job.result["_result_ref"]

            # Validate the path resolves inside the expected output
            # directory for this job.  This prevents an arbitrary file
            # read if the Redis hash is ever corrupted or tampered with.
            # We use realpath (not abspath) because it also resolves
            # symlinks — abspath only normalises ".." segments, so a
            # symlink inside JOB_OUTPUTS_PATH could still escape.
            expected_dir = os.path.realpath(job_dir)
            real_ref = os.path.realpath(ref_path)
            if (
                not real_ref.startswith(expected_dir + os.sep)
                or os.path.basename(real_ref) != config.JOB_RESULT_FILENAME
            ):
                logger.warning(
                    "Suspicious _result_ref for job %s: %s (expected under %s/%s)",
                    job_id,
                    ref_path,
                    expected_dir,
                    config.JOB_RESULT_FILENAME,
                )
            else:
                try:
                    with open(real_ref, encoding="utf-8") as fh:
                        job.result = json.load(fh)
                except (FileNotFoundError, json.JSONDecodeError):
                    logger.warning("Failed to load result from %s for job %s", ref_path, job_id)

        # Load the captured log from the volume.  The path is built from the
        # server-generated UUID job_id (never from Redis), so no traversal
        # validation is needed.
        log_path = os.path.join(job_dir, config.JOB_LOG_FILENAME)
        try:
            with open(log_path, encoding="utf-8") as fh:
                job.output_log = fh.read()
        except OSError:
            # No log file yet (job unfinished) or the best-effort write failed.
            # Leave job.output_log at its "" default rather than raise.
            pass

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

        # Read-time stale-job detection: when the status is STARTED we
        # fetch the deadline fields and check whether the job has
        # exceeded its timeout.  Only costs one extra ``hmget`` and only
        # when the job is still running.
        if status_str == JobStatus.STARTED.value:
            job_key = self._job_key(job_id)
            extra = self._redis.hmget(
                job_key,
                "started_at",
                "max_duration",
                "hard_timeout_grace",
                "session_id",
                "job_id",
            )
            data = {
                "status": status_str,
                "started_at": extra[0],
                "max_duration": extra[1],
                "hard_timeout_grace": extra[2],
                "session_id": extra[3],
                "job_id": extra[4],
            }
            if self._is_timed_out(data):
                data = self._mark_timed_out(job_key, data)
            status_str = data["status"]

        try:
            return JobStatus(status_str)
        except ValueError:
            # Mirrors the guard in ``_read_job()`` — if Redis contains an
            # unexpected value (schema change, manual corruption) we log a
            # warning and fall back to FAILURE instead of crashing the
            # status-polling callback.
            logger.warning("Unknown job status %r for job %s — defaulting to FAILURE", status_str, job_id)
            return JobStatus.FAILURE

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

    def admin_list_all_jobs(self) -> list[JobInfo]:
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
        if job is None or job.status not in TERMINAL_STATUSES:
            return False

        # Remove the job hash and its reference from the session set.
        self._redis.delete(self._job_key(job_id))
        self._redis.srem(self._session_key(session_id), job_id)

        # Clean up any offloaded result files on the shared volume.
        self._delete_job_outputs(job_id)
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
            if job is not None and job.status in TERMINAL_STATUSES:
                self._redis.delete(self._job_key(jid))
                self._redis.srem(self._session_key(session_id), jid)
                self._delete_job_outputs(jid)
                count += 1
        return count

    def admin_clear_all_jobs(self) -> int:
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
            if job is not None and job.status in TERMINAL_STATUSES:
                # Remove from the owning session's set so it doesn't
                # contain stale references to deleted job hashes.
                session_key = self._session_key(job.session_id)
                self._redis.srem(session_key, job_id)
                self._redis.delete(self._job_key(job_id))
                self._delete_job_outputs(job_id)
                count += 1
        return count

    # ── Admin: deep cleanup ──────────────────────────────────────────

    def admin_purge_all(self) -> dict:
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

        # Step 4: remove all result/log files from the job outputs directory.
        # These are the files created by ``tasks._store_result()`` and
        # ``tasks._store_log()`` for every job.
        volume_bytes_freed = 0
        volume_files_deleted = 0
        outputs_dir = config.JOB_OUTPUTS_PATH
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
