"""Backend configuration loaded from environment variables.

All backend settings are read from environment variables with sensible
defaults for local development.  In production, these are injected via
Docker Compose or the orchestrator's secret/config mechanism.
"""

import os

# Redis connection URL used as both Celery broker and result backend.
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Time-to-live (seconds) for job metadata in Redis.  After this period,
# Redis automatically evicts the key.  Default: 24 hours.
JOB_TTL_SECONDS: int = int(os.environ.get("JOB_TTL_SECONDS", "86400"))

# Default timeout (seconds) for a Celery task.  When this limit is
# reached the worker raises ``SoftTimeLimitExceeded``, which the task
# handler catches and records as ``TIMEOUT``.  A hard-kill buffer of
# ``HARD_TIMEOUT_GRACE_SECONDS`` is added automatically so cleanup code
# has time to run.  Individual tools can override via
# ``ToolDef["max_duration"]``.
DEFAULT_MAX_DURATION: int = int(os.environ.get("DEFAULT_MAX_DURATION", "3600"))

# Extra seconds added beyond ``max_duration`` for the hard SIGKILL.
# This gives the ``SoftTimeLimitExceeded`` handler time to write the
# TIMEOUT status to Redis before the process is forcibly killed.
HARD_TIMEOUT_GRACE_SECONDS: int = int(os.environ.get("HARD_TIMEOUT_GRACE_SECONDS", "60"))


# Directory for temporary job result files.  When a tool result exceeds
# ``MAX_RESULT_BYTES`` the worker writes it here as JSON.  The web
# container reads from the same path to serve results.  Cleaned up
# when a job is deleted or ``admin_purge_all()`` is called.
JOB_OUTPUTS_PATH: str = os.environ.get(
    "JOB_OUTPUTS_PATH",
    os.path.join(os.environ.get("SHARED_VOLUME_PATH", "/data"), "job_outputs"),
)

# Maximum result size (bytes) stored inline in Redis.  Results larger
# than this are written to the shared volume and a reference is stored
# in Redis instead.
MAX_RESULT_BYTES: int = int(os.environ.get("MAX_RESULT_BYTES", str(512 * 1024)))
