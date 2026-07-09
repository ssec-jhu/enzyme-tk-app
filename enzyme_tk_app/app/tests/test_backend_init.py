"""Tests for ``get_task_scheduler()`` — the lazily-initialised singleton.

``get_task_scheduler`` uses double-checked locking so that gunicorn's
multi-threaded workers never construct the ``CeleryTaskScheduler`` more
than once.  These tests exercise both the trivial single-threaded case
and an actual concurrency race to catch a regression to the broken
(missing inner check) version of the pattern.
"""

import os
import threading
import time

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


@pytest.mark.skipif(
    os.environ.get("CI", "").lower() in ("1", "true", "yes"),
    reason="Timing-dependent thread race is flaky on shared CI runners; run locally via tox.",
)
def test_get_task_scheduler_constructs_once_under_concurrency(monkeypatch):
    """Concurrent first-callers construct the scheduler exactly once.

    Regression test for the double-checked lock: if the inner ``None``
    re-check inside the lock is missing, every thread that passed the outer
    check builds its own instance (one per thread). The barrier races all
    threads at the same instant and the constructor sleeps to hold the lock
    long enough for the others to pile up — so the bug reliably shows up.
    """
    instances = []
    errors = []  # thread exceptions land here so they can fail the test body

    class FakeScheduler:
        def __init__(self):
            time.sleep(0.05)  # hold the lock so other threads pile up behind it
            instances.append(self)

    monkeypatch.setattr(
        "enzyme_tk_app.app.backend.task_scheduler_celery.CeleryTaskScheduler",
        FakeScheduler,
    )

    # Barrier with a timeout so all threads start the call to get_task_scheduler
    # at the same instant, forcing the race — and so a thread that never
    # rendezvous raises BrokenBarrierError instead of wedging the suite forever.
    barrier = threading.Barrier(20, timeout=5)

    def call():
        try:
            barrier.wait()  # release all threads at once to force the race
            get_task_scheduler()
        except Exception as exc:  # surface thread failures to the test body
            errors.append(exc)

    # Launch all threads to hit the barrier and call get_task_scheduler
    # concurrently. This simulates multiple threads racing to construct
    # the singleton at the same time.
    threads = [threading.Thread(target=call) for _ in range(20)]

    for t in threads:
        t.start()
    # join with a timeout so a stuck thread can't hang the run; assert liveness
    # so a deadlock fails the test loudly instead of passing on partial results.
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "thread did not finish — possible deadlock"

    # No thread raised, and only one instance was constructed despite the
    # concurrent calls, verifying the singleton behavior under multithreaded access.
    assert not errors, f"threads raised: {errors}"
    assert len(instances) == 1
