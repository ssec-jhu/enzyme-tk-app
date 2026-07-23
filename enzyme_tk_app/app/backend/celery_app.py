"""Celery application instance for the EnzymeTK backend.

Configured from environment variables via ``backend.config``.  Both the
web containers (for ``apply_async``) and the worker containers import this
module to share the same Celery app object.
"""

import os

from celery import Celery

from enzyme_tk_app.app.backend import config

# ── Task timeout defaults ────────────────────────────────────────────
# These are internal to the Celery execution layer.  Tool authors set
# ``max_duration`` in ``ToolDef`` and the system handles the rest.

# Default timeout (seconds) for a Celery task.  Individual tools can
# override via ``ToolDef["max_duration"]``.  When this limit is
# reached the worker raises ``SoftTimeLimitExceeded``, which the task
# handler catches and records as ``TIMEOUT``.
DEFAULT_MAX_DURATION: int = int(os.environ.get("DEFAULT_MAX_DURATION", "3600"))

# Extra seconds added beyond ``max_duration`` for the hard SIGKILL.
# This gives the ``SoftTimeLimitExceeded`` handler time to write the
# TIMEOUT status to Redis before the process is forcibly killed.
HARD_TIMEOUT_GRACE_SECONDS: int = int(os.environ.get("HARD_TIMEOUT_GRACE_SECONDS", "60"))


def effective_ttl(
    max_duration: int = DEFAULT_MAX_DURATION,
    grace: int = HARD_TIMEOUT_GRACE_SECONDS,
) -> int:
    """Compute the Redis TTL that covers a job's full lifecycle.

    Returns ``max_duration + grace + JOB_TTL_SECONDS`` so that Redis
    keys survive the entire execution window *plus* the post-completion
    retention period.  This is called automatically — tool authors and
    app developers never need to use it directly.
    """
    return max_duration + grace + config.JOB_TTL_SECONDS


# ── Celery app ───────────────────────────────────────────────────────

celery_app = Celery("enzyme_tk_app")

celery_app.conf.update(
    broker_url=config.REDIS_URL,
    result_backend=config.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_hijack_root_logger=False,
)

# Tell Celery to scan the ``enzyme_tk_app.app.backend`` package for a
# ``tasks.py`` module and register any functions decorated with ``@celery_app.task``
# (in our case, ``run_tool_task``).  Without this call, the worker would not
# know about our task and ``apply_async`` calls from the web process would fail
# with a "Received unregistered task" error.
celery_app.autodiscover_tasks(["enzyme_tk_app.app.backend"])

# ── Beat schedule ────────────────────────────────────────────────────
# Periodically reclaim disk from result dirs whose Redis job:<id> key has
# expired.  Fired by a single ``celery beat`` process (see docker-compose).
celery_app.conf.beat_schedule = {
    "celery_beat_sweep_orphaned_outputs": {
        "task": "celery_beat_sweep_orphaned_outputs",
        "schedule": config.CELERY_SWEEP_INTERVAL_SECONDS,
    },
}
