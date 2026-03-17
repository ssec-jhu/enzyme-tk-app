"""Tests for the ``TaskScheduler`` ABC contract."""

import pytest

from enzyme_tk_app.app.backend.task_scheduler import TaskScheduler


def test_abc_cannot_be_instantiated():
    """Attempting to instantiate the ABC directly raises TypeError.

    Why this matters: the ABC is a contract — UI code must always go
    through ``get_task_scheduler()`` which returns a concrete subclass.
    If the ABC were accidentally made instantiable (e.g. by removing all
    ``@abstractmethod`` decorators), callers could create a broken
    scheduler with no-op methods and silently lose jobs.
    """
    with pytest.raises(TypeError):
        TaskScheduler()


def test_abc_has_required_abstract_methods():
    """The ABC declares all 10 abstract methods from the design contract.

    Why this matters: if someone accidentally removes ``@abstractmethod``
    from a method, Python would let a subclass skip implementing it.
    That method would silently do nothing (return None) instead of
    raising NotImplementedError, causing subtle bugs at runtime.  This
    test ensures every method in the contract remains enforced.
    """
    expected_methods = {
        "submit_job",
        "cancel_job",
        "get_job",
        "get_job_status",
        "list_jobs",
        "admin_list_all_jobs",
        "delete_job",
        "clear_jobs",
        "admin_clear_all_jobs",
        "admin_purge_all",
    }
    assert expected_methods <= TaskScheduler.__abstractmethods__
