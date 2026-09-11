"""Tests for the per-session concurrent-job cap.

The constants bind at import, so every test here overrides them with
``monkeypatch.setattr`` rather than ``setenv``.  The env-parsing tests reload the
module instead, which is the only way to exercise the parse itself (the pattern
``test_paths.py`` uses for ``ETK_DATA_DIR``).
"""

import importlib
from unittest import mock

import pytest

from enzyme_tk_app.app.utils import submission_limits

SCHEDULER_PATH = "enzyme_tk_app.app.utils.submission_limits.get_task_scheduler"


@pytest.fixture()
def limit_on(monkeypatch):
    """Switch the cap on at 3, as a production deployment would."""
    monkeypatch.setattr(submission_limits, "PRODUCTION_MODE", True)
    monkeypatch.setattr(submission_limits, "MAX_ACTIVE_JOBS_PER_SESSION", 3)


def _scheduler_reporting(active: int):
    """Return a mock scheduler whose count_active_jobs reports *active*."""
    scheduler = mock.MagicMock()
    scheduler.count_active_jobs.return_value = active
    return scheduler


# ── The switch ──────────────────────────────────────────────────────────────────


def test_disabled_returns_none_without_touching_the_scheduler(monkeypatch):
    """Local mode is the default, and it must not reach for Redis.

    The guard sits before ``get_task_scheduler()`` precisely so a scientist running
    the app locally never pays for a Redis round-trip on submit.
    """
    monkeypatch.setattr(submission_limits, "PRODUCTION_MODE", False)
    with mock.patch(SCHEDULER_PATH) as mock_get:
        assert submission_limits.validate_active_job_limit("sess-1") is None
    mock_get.assert_not_called()


# ── The cap ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("active", [0, 1, 2], ids=["none", "one", "one-below-cap"])
def test_under_the_cap_is_allowed(limit_on, active):
    """Anything below the cap submits normally."""
    with mock.patch(SCHEDULER_PATH, return_value=_scheduler_reporting(active)):
        assert submission_limits.validate_active_job_limit("sess-1") is None


@pytest.mark.parametrize("active", [3, 4, 10], ids=["at-cap", "one-over", "well-over"])
def test_at_or_over_the_cap_is_refused(limit_on, active):
    """At the cap and beyond, the submit is refused with a message.

    ``>=`` not ``==``: the check-then-act race means a session can legitimately be
    found holding more slots than the cap, and that must still refuse.
    """
    with mock.patch(SCHEDULER_PATH, return_value=_scheduler_reporting(active)):
        message = submission_limits.validate_active_job_limit("sess-1")

    assert message is not None
    assert str(active) in message
    assert "3" in message, "the message must name the actual cap, not a placeholder"
    # "Clear Finished" calls clear_jobs(), which refuses non-terminal jobs — a user
    # told to clear would free nothing.  Cancel does work on PENDING.
    assert "Cancel" in message
    assert "clear" not in message.lower()


def test_the_session_id_is_passed_through(limit_on):
    """The cap is scoped to the caller's session, not global."""
    scheduler = _scheduler_reporting(0)
    with mock.patch(SCHEDULER_PATH, return_value=scheduler):
        submission_limits.validate_active_job_limit("sess-abc")
    scheduler.count_active_jobs.assert_called_once_with("sess-abc")


# ── Env parsing — must never raise (see the module docstring) ───────────────────


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, False),
        ({"APP_IN_PRODUCTION_MODE": "true"}, True),
        ({"APP_IN_PRODUCTION_MODE": "TRUE"}, True),
        ({"APP_IN_PRODUCTION_MODE": "1"}, True),
        ({"APP_IN_PRODUCTION_MODE": " yes "}, True),
        ({"APP_IN_PRODUCTION_MODE": "false"}, False),
        ({"APP_IN_PRODUCTION_MODE": ""}, False),
        ({"APP_IN_PRODUCTION_MODE": "ture"}, False),
    ],
    ids=["unset", "true", "upper", "one", "padded-yes", "false", "blank", "typo"],
)
def test_production_mode_parsing(monkeypatch, env, expected):
    """A typo must resolve to False, never raise.

    ``tools/__init__.py`` swallows a callbacks import error *after* appending the tool,
    so a raising module would leave every tool card rendering with a dead Run button
    behind an HTTP 200.
    """
    monkeypatch.delenv("APP_IN_PRODUCTION_MODE", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    try:
        assert importlib.reload(submission_limits).PRODUCTION_MODE is expected
    finally:
        monkeypatch.undo()
        importlib.reload(submission_limits)


def test_the_cap_is_a_constant_not_an_environment_variable(monkeypatch):
    """The cap must not be settable from the environment.

    It is policy this app owns, not deployment config: a deployer who could raise it to 1000
    would quietly undo the protection. This test is what stops an env read being reintroduced
    as a convenience — the value must stay a code edit and a review.
    """
    for name in ("MAX_ACTIVE_JOBS_PER_SESSION", "LIMIT_ACTIVE_JOBS", "APP_MAX_ACTIVE_JOBS_PER_SESSION"):
        monkeypatch.setenv(name, "999")
    try:
        reloaded = importlib.reload(submission_limits)
        assert reloaded.MAX_ACTIVE_JOBS_PER_SESSION == 3
        # And no resurrected on/off flag: PRODUCTION_MODE is the only switch.
        assert not hasattr(reloaded, "LIMIT_ACTIVE_JOBS")
    finally:
        monkeypatch.undo()
        importlib.reload(submission_limits)
