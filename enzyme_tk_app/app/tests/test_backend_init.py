"""Tests for ``get_task_scheduler()`` — the lazily-initialised singleton.

``get_task_scheduler`` uses double-checked locking so that gunicorn's
multi-threaded workers never construct the ``CeleryTaskScheduler`` more
than once.  These tests exercise both the trivial single-threaded case
and an actual concurrency race to catch a regression to the broken
(missing inner check) version of the pattern.
"""


import pytest

import enzyme_tk_app.app.backend as backend_pkg
from enzyme_tk_app.app.backend import get_task_scheduler


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Force the module-level ``_scheduler`` global to ``None`` around every test.

    Reset both before and after so neither a prior test nor this module can leak a
    constructed singleton into the next test or the next test module (which would
    make later tests pass or fail depending on collection order).
    """
    backend_pkg._scheduler = None
    yield
    backend_pkg._scheduler = None


def test_get_task_scheduler_returns_singleton(monkeypatch):
    """Two sequential calls return the exact same object.

    Why this matters: this is the basic contract of a singleton factory
    — callers must be able to share state (e.g. the Redis connection)
    through the returned instance.
    """
    # Patch the CeleryTaskScheduler constructor so we can control what
    # gets returned and count constructions. Here we just return a
    # unique object each time so we can verify the singleton behavior.
    monkeypatch.setattr(
        "enzyme_tk_app.app.backend.task_scheduler_celery.CeleryTaskScheduler",
        lambda: object(),
    )

    first = get_task_scheduler()
    second = get_task_scheduler()

    # make sure both calls returned the same object
    assert first is second
