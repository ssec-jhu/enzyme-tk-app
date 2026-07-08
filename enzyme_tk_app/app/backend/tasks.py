"""Generic Celery task that executes any tool's ``compute.run()`` function.

The single ``run_tool_task`` task:

1. Updates the Redis job hash to ``STARTED`` with a timestamp.
2. Captures stdout/stderr via ``contextlib.redirect_stdout``.
3. Dynamically imports ``enzyme_tk_app.app.tools.<folder>.compute``.
4. Calls ``compute.run(params)`` and stores the result.
5. On failure, stores the traceback and any partial captured output.

Every result is written to the shared volume as JSON and the captured log to
a sibling text file; Redis keeps only a pointer (``_result_ref``) to the result.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import logging
import os
import shutil
import traceback
from datetime import datetime, timezone

import redis
from celery.exceptions import SoftTimeLimitExceeded

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.backend.celery_app import (
    DEFAULT_MAX_DURATION,
    HARD_TIMEOUT_GRACE_SECONDS,
    celery_app,
    effective_ttl,
)
from enzyme_tk_app.app.backend.models import JobStatus

logger = logging.getLogger(__name__)

# Lazily initialised Redis client (one per worker process).
_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Return a module-level Redis client, creating it on first call."""
    global _redis  # noqa: PLW0603
    if _redis is None:
        _redis = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _redis


def _store_result(job_id: str, result: dict) -> dict:
    """Offload *result* to the shared volume, returning a pointer dict.

    Every result is written to ``JOB_OUTPUTS_PATH/<job_id>/result.json`` on
    the shared volume.  Redis keeps only the returned pointer dict
    (``_result_ref`` + size), never the full result inline.

    A filesystem error here (e.g. disk full / volume unmounted) raises
    ``OSError``, which the ``run_tool_task`` handler catches and records as
    a FAILURE — the write failed, so the job failed.

    Args:
        job_id: Used to build the output directory path.
        result: The dict returned by ``compute.run()``.

    Returns:
        A reference dict pointing to the volume file.
    """
    serialized = json.dumps(result, ensure_ascii=False)
    output_dir = config.job_output_dir(job_id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, config.JOB_RESULT_FILENAME)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    return {
        "_result_ref": output_path,
        "_result_size_bytes": len(serialized.encode("utf-8")),
    }


def _store_log(job_id: str, log_text: str) -> None:
    """Write the captured job log to ``JOB_OUTPUTS_PATH/<job_id>/output_log.txt``.

    Best-effort: logs are non-critical, so a filesystem error is logged and
    swallowed rather than failing an otherwise-finished job.  ``get_job`` reads
    this file back so the Redis hash keeps no log body.
    """
    try:
        output_dir = config.job_output_dir(job_id)
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, config.JOB_LOG_FILENAME), "w", encoding="utf-8") as fh:
            fh.write(log_text)
    except OSError:
        logger.warning("Failed to write output log for job %s", job_id, exc_info=True)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


@celery_app.task(name="run_tool_task")
def run_tool_task(tool_slug: str, params: dict, session_id: str, job_id: str) -> None:
    """Execute a tool's ``compute.run()`` inside the Celery worker.

    This function runs in a **separate process** (the Celery worker),
    NOT in the web server.  It is the bridge between the job scheduling
    system and every tool's algorithm code.

    The flow:
        1. Mark the job as STARTED in Redis so the UI can show progress.
        2. Convert the tool slug to a Python module path and import it.
        3. Run the tool's ``compute.run(params)`` while capturing any
           ``print()`` output the algorithm produces.
        4. Offload the result to the shared volume and store a pointer in Redis.
        5. If anything crashes, store the full traceback so the user can
           see what went wrong.

    Args:
        tool_slug: Identifies which tool to run (e.g. ``"reaction-similarity"``).
            This gets converted to an underscore folder name for import.
        params: JSON-serialisable parameters forwarded to ``compute.run()``.
            These come directly from the user's form inputs in the modal.
        session_id: The anonymous session that submitted the job.
            Used to refresh the session-set TTL so it stays in sync
            with the job hash TTL.
        job_id: Pre-generated UUID for this job.  Used as the Redis hash
            key (``job:<job_id>``) and the output directory name.
    """
    # Get the Redis client (lazily created once per worker process).
    r = _get_redis()
    job_key = f"job:{job_id}"

    # Read the per-tool timeout thresholds stored at submit time so we
    # can compute a TTL that covers the full execution window + the
    # post-completion retention period.  This prevents Redis keys from
    # expiring mid-execution when max_duration is large.
    _max_dur, _grace = r.hmget(job_key, "max_duration", "hard_timeout_grace")
    job_ttl = effective_ttl(
        int(_max_dur or DEFAULT_MAX_DURATION),
        int(_grace or HARD_TIMEOUT_GRACE_SECONDS),
    )

    # Step 1: Tell Redis (and therefore the UI) that we've started work.
    # The web server polls this status field to update the user's dashboard.
    r.hset(job_key, mapping={"status": JobStatus.STARTED.value, "started_at": _now_iso()})
    # Reset the TTL so the key doesn't expire while the job is running.
    # Also refresh the session set TTL to keep it in sync with the job hash.
    r.expire(job_key, job_ttl)
    r.expire(f"session:{session_id}:jobs", job_ttl)

    # Prepare buffers to capture anything the tool prints to stdout/stderr.
    # Many scientific algorithms use print() for progress logging — we
    # save this output so the user can review it later.
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        # Step 2: Convert URL slug to Python module path.
        # Example: "reaction-similarity" → "reaction_similarity"
        #        → "enzyme_tk_app.app.tools.reaction_similarity.compute"
        folder = tool_slug.replace("-", "_")
        module_path = f"enzyme_tk_app.app.tools.{folder}.compute"
        compute_module = importlib.import_module(module_path)

        # Step 3: Run the tool's algorithm.
        # redirect_stdout/stderr captures any print() calls the algorithm
        # makes during execution (e.g., progress updates, debug info).
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            result = compute_module.run(params)

        # Step 4: Persist the result.
        # _store_result always writes the full result to a file on the shared
        # Docker volume and returns a small pointer dict (ref + size).
        # This keeps Redis lean regardless of result size.
        stored = _store_result(job_id, result)

        # Write the final SUCCESS state + result pointer to Redis.
        r.hset(
            job_key,
            mapping={
                "status": JobStatus.SUCCESS.value,
                "completed_at": _now_iso(),
                "result": json.dumps(stored),
            },
        )

    except SoftTimeLimitExceeded:
        # Step 5a: The tool exceeded its ``max_duration`` timeout.
        # Celery raises ``SoftTimeLimitExceeded`` (which does NOT inherit
        # from ``Exception``, so the generic handler below won't catch it).
        # We record TIMEOUT explicitly so the UI shows the right status.
        r.hset(
            job_key,
            mapping={
                "status": JobStatus.TIMEOUT.value,
                "completed_at": _now_iso(),
                "error": "Job exceeded the maximum allowed duration and was stopped.",
            },
        )

    except Exception:
        # Step 5b: If the algorithm (or import) raised an exception, store
        # the full Python traceback so the user can diagnose the failure.
        r.hset(
            job_key,
            mapping={
                "status": JobStatus.FAILURE.value,
                "completed_at": _now_iso(),
                "error": traceback.format_exc(),
            },
        )

    finally:
        # Offload the captured log to the volume on every outcome (success,
        # timeout, or crash) — the args are identical in all branches, so a
        # single write here covers them and keeps no log body in Redis. Any
        # partial stdout/stderr captured before a crash is preserved.
        _store_log(job_id, stdout_buf.getvalue() + stderr_buf.getvalue())
        # Always refresh the TTL so the job metadata stays available for
        # the full lifecycle window regardless of outcome.
        r.expire(job_key, job_ttl)
        # Keep the session set alive at least as long as its newest job.
        # Without this, the set can expire before the job hash, breaking
        # ownership checks and job listing even though the job still exists.
        session_key = f"session:{session_id}:jobs"
        r.expire(session_key, job_ttl)


@celery_app.task(name="celery_beat_sweep_orphaned_outputs")
def celery_beat_sweep_orphaned_outputs() -> int:
    """Delete job_outputs dirs whose Redis ``job:<id>`` key has expired.

    Runs periodically via Celery beat.  Reclaims disk for results whose
    Redis metadata has aged out (TTL reached) but whose ``result.json``
    file still lingers on the shared volume.

    Returns:
        The number of orphaned directories removed.
    """
    outputs_dir = config.JOB_OUTPUTS_PATH
    if not os.path.isdir(outputs_dir):
        return 0

    r = _get_redis()
    removed = 0
    # ponytail: one EXISTS per dir, fine for a once-a-day background sweep.
    # If dir counts get huge and sweep latency matters, pipeline the EXISTS.
    with os.scandir(outputs_dir) as entries:
        for entry in entries:
            if entry.is_dir() and not r.exists(f"job:{entry.name}"):
                shutil.rmtree(entry.path, ignore_errors=True)
                removed += 1

    logger.info("Orphan sweep: removed %d orphaned outputs", removed)
    return removed
