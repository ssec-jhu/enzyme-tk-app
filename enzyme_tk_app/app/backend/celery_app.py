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

# Tell Celery to scan the ``enzyme_tk_app.app.backend`` package for a
# ``tasks.py`` module and register any functions decorated with ``@celery_app.task``
# (in our case, ``run_tool_task``).  Without this call, the worker would not
# know about our task and ``apply_async`` calls from the web process would fail
# with a "Received unregistered task" error.
celery_app.autodiscover_tasks(["enzyme_tk_app.app.backend"])
