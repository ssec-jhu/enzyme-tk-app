"""Backend configuration loaded from environment variables.

All backend settings are read from environment variables with sensible
defaults for local development.  In production, these are injected via
Docker Compose or the orchestrator's secret/config mechanism.
"""

import os

# Redis connection URL used as both Celery broker and result backend.
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Post-completion retention period (seconds) for job metadata in Redis.
# Celery-specific code uses ``celery_app.effective_ttl()`` to add this
# on top of the execution window so keys never expire mid-run.
# Default: 24 hours.
JOB_TTL_SECONDS: int = int(os.environ.get("JOB_TTL_SECONDS", "86400"))


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
