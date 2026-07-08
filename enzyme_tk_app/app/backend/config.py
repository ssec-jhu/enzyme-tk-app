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

# How often the Celery beat orphan-sweep runs (seconds).  The sweep removes
# job_outputs dirs whose Redis job:<id> key has expired.  Default: 24 hours.
# Clamped to >= 1s: a 0/negative value fed to Celery beat makes it fire
# continuously (or crash at startup), so we floor it to a sane minimum.
CELERY_SWEEP_INTERVAL_SECONDS: int = max(1, int(os.environ.get("CELERY_SWEEP_INTERVAL_SECONDS", "86400")))


# Directory for temporary job result files.  Every tool result is written
# here as JSON; Redis keeps only a pointer + preview.  The web container
# reads from the same path to serve results.  Cleaned up when a job is
# deleted, by the orphan sweep, or when ``admin_purge_all()`` is called.
JOB_OUTPUTS_PATH: str = os.environ.get(
    "JOB_OUTPUTS_PATH",
    os.path.join(os.environ.get("SHARED_VOLUME_PATH", "/data"), "job_outputs"),
)


# Shared secret that unlocks the hidden ``/admin`` dashboard.  Supplied
# only at deploy time via the environment — it is NEVER committed to the
# repository.  An empty value (the default) means the admin page is
# DISABLED entirely: the login can never succeed (fail-closed).  This is
# the safe default for a public codebase where anyone can read the source
# but only the deployer knows the token.
ADMIN_TOKEN: str = os.environ.get("ETK_ADMIN_TOKEN", "")

# Secret key used by Flask to cryptographically sign the session cookie
# that records a successful admin login.  Must be a long, random,
# deployer-provided value in production so the ``is_admin`` flag cannot be
# forged.  When unset, the app falls back to a random per-process key
# (see ``app.py``) — usable for local dev but logs admins out on restart.
SECRET_KEY: str = os.environ.get("ETK_SECRET_KEY", "")

# Idle timeout (seconds) for an unlocked admin session.  The admin cookie
# is a browser-session cookie (cleared on browser close), but browsers
# that restore sessions can keep it alive indefinitely.  To bound this,
# the server slides an expiry forward on every authenticated admin request
# (the dashboard polls every 10 s while open).  Once the tab closes the
# polling stops and the session expires after this window.  Default: 5 min.
ADMIN_SESSION_TTL_SECONDS: int = int(os.environ.get("ETK_ADMIN_SESSION_TTL_SECONDS", "300"))


def admin_enabled() -> bool:
    """Return True only when both ADMIN_TOKEN and SECRET_KEY are configured."""
    return bool(ADMIN_TOKEN and SECRET_KEY)
