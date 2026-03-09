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

# Default hard time limit (seconds) for a Celery task.  The worker sends
# SIGKILL if the task exceeds this.  Individual tools can override via
# ``ToolDef["max_duration"]``.
DEFAULT_MAX_DURATION: int = int(os.environ.get("DEFAULT_MAX_DURATION", "3600"))

# Path to the shared volume mounted in both web and worker containers.
# Used for large result offloading and trained model storage.
SHARED_VOLUME_PATH: str = os.environ.get("SHARED_VOLUME_PATH", "/data")

# Maximum result size (bytes) stored inline in Redis.  Results larger
# than this are written to the shared volume and a reference is stored
# in Redis instead.
MAX_RESULT_BYTES: int = int(os.environ.get("MAX_RESULT_BYTES", str(512 * 1024)))
