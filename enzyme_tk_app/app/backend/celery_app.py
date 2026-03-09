"""Celery application instance for the EnzymeTK backend.

Configured from environment variables via ``backend.config``.  Both the
web containers (for ``apply_async``) and the worker containers import this
module to share the same Celery app object.
"""

from celery import Celery

from enzyme_tk_app.app.backend import config

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

# Auto-discover the tasks module so Celery registers run_tool_task.
celery_app.autodiscover_tasks(["enzyme_tk_app.app.backend"])
