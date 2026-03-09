"""Backend job scheduling package for the EnzymeTK Tool Suite.

Public API
----------
- ``get_job_scheduling_service()`` — returns the singleton
  ``JobSchedulingService`` implementation (currently Celery + Redis).
- ``JobSchedulingService`` — the ABC that all UI code programs against.
- ``JobInfo`` / ``JobStatus`` — data transfer objects.

Usage in Dash callbacks::

    from flask import g
    from enzyme_tk_app.app.backend import get_job_scheduling_service

    service = get_job_scheduling_service()
    job_id = service.submit_job("reaction-similarity", params, g.session_id)
"""

from __future__ import annotations

from enzyme_tk_app.app.backend.api import JobSchedulingService
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus

__all__ = [
    "JobInfo",
    "JobSchedulingService",
    "JobStatus",
    "get_job_scheduling_service",
]

# Singleton instance — lazily initialised to avoid Redis connections at
# import time (important for test environments that don't run Redis).
_service: JobSchedulingService | None = None


def get_job_scheduling_service() -> JobSchedulingService:
    """Return the singleton ``JobSchedulingService`` implementation.

    The instance is created on first call to avoid opening a Redis
    connection during module import (which would break tests and CLI
    scripts that don't need the backend).

    Returns:
        The application-wide ``CeleryJobSchedulingService`` instance.
    """
    global _service  # noqa: PLW0603
    if _service is None:
        from enzyme_tk_app.app.backend.celery_service import CeleryJobSchedulingService  # noqa: PLC0415

        _service = CeleryJobSchedulingService()
    return _service
