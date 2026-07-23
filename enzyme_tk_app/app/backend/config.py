"""Backend configuration loaded from environment variables.

All backend settings are read from environment variables with sensible
defaults for local development.  In production, these are injected via
Docker Compose or the orchestrator's secret/config mechanism.
"""

import os
from typing import NamedTuple

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


# Directory for offloaded job files.  Every tool result and its captured log
# are written here; Redis keeps only a pointer to the result.  The web
# container reads from the same path to serve results.  Cleaned up when a job
# is deleted, by the orphan sweep, or when ``admin_purge_all()`` is called.
JOB_OUTPUTS_PATH: str = os.environ.get("JOB_OUTPUTS_PATH", "/job-outputs")

# Filenames written under ``JOB_OUTPUTS_PATH/<job_id>/`` by the worker and read
# back by the web container.  These literal values live ONLY here — the single
# source of truth.  All other code (and docstrings) references the constants so
# the writer (``tasks.py``) and reader (``task_scheduler_celery.py``) can never
# drift out of sync.
JOB_RESULT_FILENAME: str = "result.json"
JOB_LOG_FILENAME: str = "output_log.txt"


class JobPaths(NamedTuple):
    """The on-disk paths for one job's offloaded output, all under ``directory``.

    ``directory`` is ``JOB_OUTPUTS_PATH/<job_id>``;
    ``result`` and ``log`` are the ``JOB_RESULT_FILENAME`` / ``JOB_LOG_FILENAME`` files inside it.
    """

    directory: str
    result: str
    log: str


def job_output_paths(job_id: str) -> JobPaths:
    """Return the validated on-disk paths for *job_id*'s offloaded output.

    Single choke point for turning a ``job_id`` into filesystem paths, so the
    containment check here protects every consumer — including the destructive
    ``shutil.rmtree`` in ``_delete_job_outputs`` — against a ``job_id`` that
    tries to escape ``JOB_OUTPUTS_PATH`` (e.g. ``".."`` or an absolute path).

    Raises:
        ValueError: if *job_id* does not resolve to a direct child of
            ``JOB_OUTPUTS_PATH``.
    """
    output_dir = os.path.join(JOB_OUTPUTS_PATH, job_id)
    base = os.path.realpath(JOB_OUTPUTS_PATH)
    # realpath resolves ".." *and* symlinks;
    # require a direct child of the base.
    if os.path.dirname(os.path.realpath(output_dir)) != base:
        raise ValueError(f"job_id {job_id!r} escapes JOB_OUTPUTS_PATH")
    return JobPaths(
        directory=output_dir,
        result=os.path.join(output_dir, JOB_RESULT_FILENAME),
        log=os.path.join(output_dir, JOB_LOG_FILENAME),
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
