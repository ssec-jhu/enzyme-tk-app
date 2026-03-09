"""Backend task scheduling package for the EnzymeTK Tool Suite.

Public API
----------
- ``get_task_scheduler()`` — returns the singleton
  ``TaskScheduler`` implementation (currently Celery + Redis).
- ``TaskScheduler`` — the ABC that all UI code programs against.
- ``JobInfo`` / ``JobStatus`` — data transfer objects.

Usage in Dash callbacks::

    from flask import g
    from enzyme_tk_app.app.backend import get_task_scheduler

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job("reaction-similarity", params, g.session_id)
"""

from __future__ import annotations

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.backend.task_scheduler import TaskScheduler

__all__ = [
    "JobInfo",
    "JobStatus",
    "TaskScheduler",
    "get_task_scheduler",
]

# Singleton instance — lazily initialised to avoid Redis connections at
# import time (important for test environments that don't run Redis).
_scheduler: TaskScheduler | None = None


def get_task_scheduler() -> TaskScheduler:
    """Return the singleton ``TaskScheduler`` implementation.

    The instance is created on first call to avoid opening a Redis
    connection during module import (which would break tests and CLI
    scripts that don't need the backend).

    Returns:
        The application-wide ``CeleryTaskScheduler`` instance.
    """
    global _scheduler  # noqa: PLW0603
    if _scheduler is None:
        from enzyme_tk_app.app.backend.task_scheduler_celery import CeleryTaskScheduler  # noqa: PLC0415

        _scheduler = CeleryTaskScheduler()
    return _scheduler
