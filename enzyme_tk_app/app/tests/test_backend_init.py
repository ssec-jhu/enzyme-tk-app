"""Tests for ``get_task_scheduler()`` — the lazily-initialised singleton.

``get_task_scheduler`` uses double-checked locking so that gunicorn's
multi-threaded workers never construct the ``CeleryTaskScheduler`` more
than once.  These tests exercise both the trivial single-threaded case
and an actual concurrency race to catch a regression to the broken
(missing inner check) version of the pattern.
"""

import threading
import time

import pytest

import enzyme_tk_app.app.backend as backend_pkg
from enzyme_tk_app.app.backend import get_task_scheduler


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Reset the module-level ``_scheduler`` global before each test.

    Without this, whichever test runs first would permanently populate
    the singleton for the rest of the test session.
    """
    monkeypatch.setattr(backend_pkg, "_scheduler", None)


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


def test_get_task_scheduler_constructs_once_under_concurrency(monkeypatch):
    """Concurrent first-callers construct the scheduler exactly once.

    Regression test for the double-checked lock: if the inner ``None``
    re-check inside the lock is missing, every thread that passed the outer
    check builds its own instance (one per thread). The barrier races all
    threads at the same instant and the constructor sleeps to hold the lock
    long enough for the others to pile up — so the bug reliably shows up.
    """
    instances = []

    class FakeScheduler:
        def __init__(self):
            time.sleep(0.05)  # hold the lock so other threads pile up behind it
            instances.append(self)

    monkeypatch.setattr(
        "enzyme_tk_app.app.backend.task_scheduler_celery.CeleryTaskScheduler",
        FakeScheduler,
    )

    # Create a barrier so all threads start the call to get_task_scheduler
    # at the same time, forcing the race condition to test the singleton
    # construction under concurrency.
    barrier = threading.Barrier(20)

    def call():
        barrier.wait()  # release all threads at once to force the race
        get_task_scheduler()

    # Launch all threads to hit the barrier and call get_task_scheduler
    # concurrently. This simulates multiple threads racing to construct
    # the singleton at the same time.
    threads = [threading.Thread(target=call) for _ in range(20)]
    
    # Start all threads so they hit the barrier and attempt to construct
    # the scheduler concurrently. Then join them to wait for completion.
    for t in threads:
        # spawns the OS thread and begins running its target (call) concurrently. 
        #  The thread will block at the barrier until all threads are ready, 
        #  then proceed to call get_task_scheduler, simulating concurrent access.
        t.start()
    for t in threads:
        t.join()

    # Only one instance should have been constructed despite the
    # concurrent calls, verifying the singleton behavior under
    # multithreaded access.
    assert len(instances) == 1
