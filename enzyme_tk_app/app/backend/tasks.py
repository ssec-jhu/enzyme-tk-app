"""Generic Celery task that executes any tool's ``compute.run()`` function.

The single ``run_tool_task`` task:

1. Updates the Redis job hash to ``STARTED`` with a timestamp.
2. Captures stdout/stderr via ``contextlib.redirect_stdout``.
3. Dynamically imports ``enzyme_tk_app.app.tools.<folder>.compute``.
4. Calls ``compute.run(params)`` and stores the result.
5. On failure, stores the traceback and any partial captured output.

Large results (> ``MAX_RESULT_BYTES``) are automatically offloaded to the
shared volume and replaced with a reference dict in Redis.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import logging
import os
import traceback
from datetime import datetime, timezone

import redis
from celery.exceptions import SoftTimeLimitExceeded

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.backend.celery_app import celery_app
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
    """Decide whether to store *result* inline or offload to volume.

    Args:
        job_id: Used to build the output directory path.
        result: The dict returned by ``compute.run()``.

    Returns:
        The dict to persist in Redis — either the original *result*
        (if small enough) or a reference dict pointing to the volume file.
    """
    serialized = json.dumps(result, ensure_ascii=False)

    if len(serialized.encode("utf-8")) <= config.MAX_RESULT_BYTES:
        return result

    # Too large — write to shared volume.
    output_dir = os.path.join(config.JOB_OUTPUTS_PATH, job_id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "result.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)

    return {
        "_result_ref": output_path,
        "_result_size_bytes": len(serialized.encode("utf-8")),
        "preview": _make_preview(result),
    }


def _make_preview(result: dict, max_items: int = 5) -> dict:
    """Create a lightweight preview of *result* for the jobs list page.

    Args:
        result: Full result dict.
        max_items: Maximum number of top-level keys to include.

    Returns:
        A trimmed copy containing at most *max_items* keys.
    """
    preview: dict = {}
    for i, (key, value) in enumerate(result.items()):
        if i >= max_items:
            break
        # Truncate large nested values to a summary string.
        if isinstance(value, list) and len(value) > 3:
            preview[key] = f"[{len(value)} items]"
        elif isinstance(value, dict) and len(value) > 3:
            preview[key] = f"{{{len(value)} keys}}"
        else:
            preview[key] = value
    return preview


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
        4. Store the result back in Redis (or offload to disk if too big).
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

    # Step 1: Tell Redis (and therefore the UI) that we've started work.
    # The web server polls this status field to update the user's dashboard.
    r.hset(job_key, mapping={"status": JobStatus.STARTED.value, "started_at": _now_iso()})
    # Reset the TTL so the key doesn't expire while the job is running.
    # Also refresh the session set TTL to keep it in sync with the job hash.
    r.expire(job_key, config.JOB_TTL_SECONDS)
    r.expire(f"session:{session_id}:jobs", config.JOB_TTL_SECONDS)

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
        # _store_result checks the size — if the result dict serialises to
        # more than 512 KB of JSON, it writes the full data to a file on
        # the shared Docker volume and returns a small pointer dict instead.
        # This prevents Redis from running out of memory on large outputs.
        stored = _store_result(job_id, result)

        # Write the final SUCCESS state + result + captured output to Redis.
        r.hset(
            job_key,
            mapping={
                "status": JobStatus.SUCCESS.value,
                "completed_at": _now_iso(),
                "result": json.dumps(stored),
                "output_log": stdout_buf.getvalue() + stderr_buf.getvalue(),
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
                "output_log": stdout_buf.getvalue() + stderr_buf.getvalue(),
            },
        )

    except Exception:
        # Step 5b: If the algorithm (or import) raised an exception, store
        # the full Python traceback so the user can diagnose the failure.
        # Any partial stdout/stderr captured before the crash is also saved.
        r.hset(
            job_key,
            mapping={
                "status": JobStatus.FAILURE.value,
                "completed_at": _now_iso(),
                "error": traceback.format_exc(),
                "output_log": stdout_buf.getvalue() + stderr_buf.getvalue(),
            },
        )

    finally:
        # Always refresh the TTL so the job metadata stays available for
        # the configured period (default 24 hours) regardless of outcome.
        r.expire(job_key, config.JOB_TTL_SECONDS)
        # Keep the session set alive at least as long as its newest job.
        # Without this, the set can expire before the job hash, breaking
        # ownership checks and job listing even though the job still exists.
        session_key = f"session:{session_id}:jobs"
        r.expire(session_key, config.JOB_TTL_SECONDS)
