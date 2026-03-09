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
    serialized = json.dumps(result)

    if len(serialized.encode()) <= config.MAX_RESULT_BYTES:
        return result

    # Too large — write to shared volume.
    output_dir = os.path.join(config.SHARED_VOLUME_PATH, "job_outputs", job_id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "result.json")
    with open(output_path, "w") as fh:
        fh.write(serialized)

    return {
        "_result_ref": output_path,
        "_result_size_bytes": len(serialized.encode()),
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

    Args:
        tool_slug: Identifies which tool to run (e.g. ``"reaction-similarity"``).
        params: JSON-serialisable parameters forwarded to ``compute.run()``.
        session_id: The anonymous session that submitted the job.
        job_id: Pre-generated UUID for this job.
    """
    r = _get_redis()
    job_key = f"job:{job_id}"

    # Mark STARTED.
    r.hset(job_key, mapping={"status": JobStatus.STARTED.value, "started_at": _now_iso()})
    r.expire(job_key, config.JOB_TTL_SECONDS)

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        # Dynamic import: slug ``reaction-similarity`` → folder ``reaction_similarity``.
        folder = tool_slug.replace("-", "_")
        module_path = f"enzyme_tk_app.app.tools.{folder}.compute"
        compute_module = importlib.import_module(module_path)

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            result = compute_module.run(params)

        stored = _store_result(job_id, result)

        r.hset(
            job_key,
            mapping={
                "status": JobStatus.SUCCESS.value,
                "completed_at": _now_iso(),
                "result": json.dumps(stored),
                "output_log": stdout_buf.getvalue() + stderr_buf.getvalue(),
            },
        )

    except Exception:
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
        r.expire(job_key, config.JOB_TTL_SECONDS)
