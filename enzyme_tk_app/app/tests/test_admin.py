"""Tests for the hidden Admin dashboard — auth gate, builders, and callbacks."""

import time
from unittest.mock import MagicMock, patch

import dash_ag_grid as dag
import pytest
from dash import dcc, html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server
from enzyme_tk_app.app.backend.models import JobStatus
from enzyme_tk_app.app.pages.admin import (
    _build_jobs_grid,
    _build_sessions_grid,
    _compute_stats,
    _grant_admin,
    _is_admin,
    _jobs_to_rows,
    _sessions_to_rows,
    _verify_token,
    cancel_selected_admin_jobs,
    layout,
    prompt_admin_clear,
    prompt_admin_purge,
    refresh_admin_dashboard,
    run_admin_clear,
    run_admin_purge,
    unlock_admin_dashboard,
)

from .conftest import find_components, get_text, make_job

ADMIN_TOKEN_PATH = "enzyme_tk_app.app.pages.admin.ADMIN_TOKEN"
SCHEDULER_PATH = "enzyme_tk_app.app.pages.admin.get_task_scheduler"


# ── _verify_token ────────────────────────────────────────────────────────────


def test_verify_token_rejects_when_token_unset():
    """An empty configured token must reject every candidate (fail-closed)."""
    with patch(ADMIN_TOKEN_PATH, ""):
        assert _verify_token("anything") is False
        assert _verify_token("") is False
        assert _verify_token(None) is False


def test_verify_token_accepts_exact_match():
    """A non-empty configured token must accept only an exact match."""
    with patch(ADMIN_TOKEN_PATH, "s3cret-token"):
        assert _verify_token("s3cret-token") is True


def test_verify_token_rejects_wrong_value():
    """A non-empty configured token must reject a mismatched candidate."""
    with patch(ADMIN_TOKEN_PATH, "s3cret-token"):
        assert _verify_token("wrong") is False
        assert _verify_token(None) is False


# ── _is_admin ────────────────────────────────────────────────────────────────


def test_is_admin_false_by_default():
    """A fresh session must not be considered admin."""
    with server.test_request_context():
        assert _is_admin() is False


def test_is_admin_true_when_flag_set():
    """A freshly granted admin session must be considered admin."""
    with server.test_request_context():
        _grant_admin()
        assert _is_admin() is True


def test_grant_admin_sets_future_expiry():
    """_grant_admin must record an expiry timestamp in the future."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        _grant_admin()
        assert session["is_admin"] is True
        assert session["admin_expires_at"] > time.time()


def test_is_admin_false_when_expired():
    """An admin session whose idle window has elapsed must not be admin."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        session["is_admin"] = True
        session["admin_expires_at"] = time.time() - 1
        assert _is_admin() is False


def test_is_admin_clears_stale_keys_when_expired():
    """An expired session must have its admin keys purged."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        session["is_admin"] = True
        session["admin_expires_at"] = time.time() - 1
        _is_admin()
        assert "is_admin" not in session
        assert "admin_expires_at" not in session


def test_is_admin_false_when_expiry_missing():
    """A flag without an expiry timestamp must be treated as expired."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        session["is_admin"] = True
        assert _is_admin() is False


def test_is_admin_slides_expiry_forward():
    """Each authenticated check must push the idle expiry further out."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        _grant_admin()
        session["admin_expires_at"] = time.time() + 1
        near_expiry = session["admin_expires_at"]
        assert _is_admin() is True
        assert session["admin_expires_at"] > near_expiry


# ── build_stat_card ──────────────────────────────────────────────────────────


def test_build_stat_card_renders_value_and_label():
    """build_stat_card must produce a card with the given value and label."""
    from enzyme_tk_app.app.components.results_helpers import build_stat_card

    card = build_stat_card(7, "Active Sessions")

    assert isinstance(card, html.Div)
    assert card.className == "jobs-stat-card"
    text = get_text(card)
    assert "7" in text
    assert "Active Sessions" in text


# ── _compute_stats ───────────────────────────────────────────────────────────


def test_compute_stats_returns_five_cards_with_correct_counts():
    """_compute_stats must produce five cards with correct aggregate counts."""
    jobs = [
        make_job(job_id="a", session_id="s1", status=JobStatus.SUCCESS),
        make_job(job_id="b", session_id="s1", status=JobStatus.PENDING),
        make_job(job_id="c", session_id="s2", status=JobStatus.STARTED),
        make_job(job_id="d", session_id="s2", status=JobStatus.FAILURE),
        make_job(job_id="e", session_id="s2", status=JobStatus.TIMEOUT),
    ]
    cards = _compute_stats(jobs)

    assert len(cards) == 5
    # Active sessions: 2, Total: 5, Running: 2, Succeeded: 1, Failed/Errored: 2.
    assert "2" in get_text(cards[0])
    assert "5" in get_text(cards[1])
    assert "2" in get_text(cards[2])
    assert "1" in get_text(cards[3])
    assert "2" in get_text(cards[4])


# ── _jobs_to_rows ────────────────────────────────────────────────────────────


def test_jobs_to_rows_carries_full_job_id_and_active_first():
    """_jobs_to_rows must carry the full job_id and order active jobs first."""
    jobs = [
        make_job(job_id="terminal-1", status=JobStatus.SUCCESS, submitted_at="2025-01-01T00:00:00+00:00"),
        make_job(job_id="active-1", status=JobStatus.PENDING, submitted_at="2025-01-01T00:01:00+00:00"),
    ]
    rows = _jobs_to_rows(jobs)

    assert rows[0]["job_id"] == "active-1"
    assert rows[0]["status"] == "PENDING"
    assert {r["job_id"] for r in rows} == {"active-1", "terminal-1"}


def test_jobs_to_rows_running_job_duration_is_tbd():
    """A running job's duration cell must be 'TBD'."""
    rows = _jobs_to_rows([make_job(job_id="j", status=JobStatus.STARTED)])

    assert rows[0]["duration"] == "TBD"


# ── _sessions_to_rows ────────────────────────────────────────────────────────


def test_sessions_to_rows_aggregates_by_session():
    """_sessions_to_rows must aggregate job counts per session."""
    jobs = [
        make_job(job_id="a", session_id="s1", status=JobStatus.PENDING),
        make_job(job_id="b", session_id="s1", status=JobStatus.SUCCESS),
        make_job(job_id="c", session_id="s2", status=JobStatus.SUCCESS),
    ]
    rows = _sessions_to_rows(jobs)

    by_id = {r["session_id"]: r for r in rows}
    assert by_id["s1"]["total"] == 2
    assert by_id["s1"]["running"] == 1
    assert by_id["s2"]["total"] == 1
    assert by_id["s2"]["running"] == 0


# ── Grid factories ───────────────────────────────────────────────────────────


def test_build_sessions_grid_has_expected_id():
    """The sessions grid must be an AgGrid with the expected id."""
    grid = _build_sessions_grid()

    assert isinstance(grid, dag.AgGrid)
    assert grid.id == "id-grid-admin-sessions"


def test_build_jobs_grid_enables_multi_selection():
    """The jobs grid must enable multiple row selection with a checkbox column."""
    grid = _build_jobs_grid()

    assert isinstance(grid, dag.AgGrid)
    assert grid.id == "id-grid-admin-jobs"
    assert grid.dashGridOptions["rowSelection"] == "multiple"
    checkbox_cols = [c for c in grid.columnDefs if c.get("checkboxSelection")]
    assert len(checkbox_cols) == 1


# ── layout ───────────────────────────────────────────────────────────────────


def test_layout_shows_login_when_not_admin():
    """layout() must render the login card for a non-admin session."""
    with server.test_request_context():
        result = layout()

    assert isinstance(result, html.Div)
    inputs = find_components(result, dcc.Input)
    assert any(getattr(i, "id", None) == "id-input-admin-token" for i in inputs)


def test_layout_shows_dashboard_when_admin():
    """layout() must render the dashboard for an admin session."""
    with server.test_request_context():
        _grant_admin()
        result = layout()

    text = get_text(result)
    assert "Admin Dashboard" in text
    grids = find_components(result, dag.AgGrid)
    grid_ids = {getattr(g, "id", None) for g in grids}
    assert {"id-grid-admin-sessions", "id-grid-admin-jobs"} <= grid_ids


# ── unlock_admin_dashboard ───────────────────────────────────────────────────


def test_unlock_raises_prevent_update_without_submission():
    """unlock_admin_dashboard must raise PreventUpdate when nothing was submitted."""
    with pytest.raises(PreventUpdate):
        unlock_admin_dashboard(0, 0, "token")


def test_unlock_rejects_invalid_token():
    """An invalid token must return the login card with an error and not set admin."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        with patch(ADMIN_TOKEN_PATH, "right-token"):
            result = unlock_admin_dashboard(1, 0, "wrong-token")

        assert "is_admin" not in session
    assert "Invalid token" in get_text(result)


def test_unlock_accepts_valid_token_and_sets_session():
    """A valid token must set the admin flag and return the dashboard."""
    with server.test_request_context():
        from flask import session  # noqa: PLC0415

        with patch(ADMIN_TOKEN_PATH, "right-token"):
            result = unlock_admin_dashboard(1, 0, "right-token")

        assert session["is_admin"] is True
    assert "Admin Dashboard" in get_text(result)


# ── refresh_admin_dashboard ──────────────────────────────────────────────────


def test_refresh_raises_prevent_update_when_not_admin():
    """refresh_admin_dashboard must refuse to run for a non-admin session."""
    with server.test_request_context(), pytest.raises(PreventUpdate):
        refresh_admin_dashboard(1, 0)


def test_refresh_returns_stats_and_rows_for_admin():
    """refresh_admin_dashboard must return five stat cards and grid rows."""
    jobs = [
        make_job(job_id="a", session_id="s1", status=JobStatus.PENDING),
        make_job(job_id="b", session_id="s2", status=JobStatus.SUCCESS),
    ]
    mock_scheduler = MagicMock()
    mock_scheduler.admin_list_all_jobs.return_value = jobs
    mock_scheduler.admin_storage_usage.return_value = {"bytes": 0, "files": 0}

    with server.test_request_context():
        _grant_admin()
        with patch(SCHEDULER_PATH, return_value=mock_scheduler):
            stats, session_rows, job_rows = refresh_admin_dashboard(1, 0)

    assert len(stats) == 5
    assert len(session_rows) == 2
    assert len(job_rows) == 2


# ── cancel_selected_admin_jobs ───────────────────────────────────────────────


def test_cancel_selected_raises_prevent_update_when_not_admin():
    """cancel_selected_admin_jobs must refuse to run for a non-admin session."""
    with server.test_request_context(), pytest.raises(PreventUpdate):
        cancel_selected_admin_jobs(1, [{"job_id": "x"}])


def test_cancel_selected_no_selection_returns_message():
    """With no rows selected, the callback must report it and not bump the store."""
    with server.test_request_context():
        _grant_admin()
        bump, message = cancel_selected_admin_jobs(1, [])

    assert bump is no_update
    assert "No jobs selected" in message


def test_cancel_selected_cancels_each_selected_job():
    """The callback must call cancel_job (admin mode) for each selected row."""
    mock_scheduler = MagicMock()
    mock_scheduler.cancel_job.return_value = True

    with server.test_request_context():
        _grant_admin()
        with patch(SCHEDULER_PATH, return_value=mock_scheduler):
            bump, message = cancel_selected_admin_jobs(1, [{"job_id": "j1"}, {"job_id": "j2"}])

    cancelled_ids = [call.args[0] for call in mock_scheduler.cancel_job.call_args_list]
    assert cancelled_ids == ["j1", "j2"]
    assert bump is not no_update
    assert "Cancelled 2" in message


# ── prompt callbacks ─────────────────────────────────────────────────────────


def test_prompt_clear_raises_prevent_update_when_not_admin():
    """prompt_admin_clear must not display the dialog for a non-admin."""
    with server.test_request_context(), pytest.raises(PreventUpdate):
        prompt_admin_clear(1)


def test_prompt_clear_displays_dialog_for_admin():
    """prompt_admin_clear must return True to display the confirm dialog."""
    with server.test_request_context():
        _grant_admin()
        assert prompt_admin_clear(1) is True


def test_prompt_purge_displays_dialog_for_admin():
    """prompt_admin_purge must return True to display the confirm dialog."""
    with server.test_request_context():
        _grant_admin()
        assert prompt_admin_purge(1) is True


# ── run_admin_clear ──────────────────────────────────────────────────────────


def test_run_clear_raises_prevent_update_without_confirmation():
    """run_admin_clear must raise PreventUpdate when not confirmed."""
    with server.test_request_context(), pytest.raises(PreventUpdate):
        run_admin_clear(0)


def test_run_clear_calls_scheduler_and_reports_count():
    """run_admin_clear must call admin_clear_all_jobs and report the count."""
    mock_scheduler = MagicMock()
    mock_scheduler.admin_clear_all_jobs.return_value = 4

    with server.test_request_context():
        _grant_admin()
        with patch(SCHEDULER_PATH, return_value=mock_scheduler):
            bump, message = run_admin_clear(1)

    mock_scheduler.admin_clear_all_jobs.assert_called_once_with()
    assert bump is not no_update
    assert "Cleared 4" in message


# ── run_admin_purge ──────────────────────────────────────────────────────────


def test_run_purge_raises_prevent_update_without_confirmation():
    """run_admin_purge must raise PreventUpdate when not confirmed."""
    with server.test_request_context(), pytest.raises(PreventUpdate):
        run_admin_purge(0)


def test_run_purge_calls_scheduler_and_summarises():
    """run_admin_purge must call admin_purge_all and summarise the result."""
    mock_scheduler = MagicMock()
    mock_scheduler.admin_purge_all.return_value = {
        "jobs_deleted": 10,
        "sessions_cleared": 3,
        "tasks_revoked": 2,
        "volume_bytes_freed": 1024,
        "volume_files_deleted": 5,
    }

    with server.test_request_context():
        _grant_admin()
        with patch(SCHEDULER_PATH, return_value=mock_scheduler):
            bump, message = run_admin_purge(1)

    mock_scheduler.admin_purge_all.assert_called_once_with()
    assert bump is not no_update
    assert "10 jobs" in message
    assert "1.0 KB" in message


# ── admin_storage_usage (concrete ABC method) ────────────────────────────────


def test_admin_storage_usage_totals_files(task_scheduler_celery_service, tmp_path, monkeypatch):
    """admin_storage_usage must total the size and count of result files."""
    outputs_dir = tmp_path / "job_outputs"
    (outputs_dir / "job-1").mkdir(parents=True)
    (outputs_dir / "job-1" / "result.json").write_bytes(b"x" * 100)
    (outputs_dir / "job-2").mkdir(parents=True)
    (outputs_dir / "job-2" / "result.json").write_bytes(b"y" * 50)
    monkeypatch.setattr(
        "enzyme_tk_app.app.backend.task_scheduler.config.JOB_OUTPUTS_PATH",
        str(outputs_dir),
    )

    usage = task_scheduler_celery_service.admin_storage_usage()

    assert usage == {"bytes": 150, "files": 2}


def test_admin_storage_usage_zero_when_missing(task_scheduler_celery_service, tmp_path, monkeypatch):
    """admin_storage_usage must return zeros when the directory is absent."""
    monkeypatch.setattr(
        "enzyme_tk_app.app.backend.task_scheduler.config.JOB_OUTPUTS_PATH",
        str(tmp_path / "does-not-exist"),
    )

    usage = task_scheduler_celery_service.admin_storage_usage()

    assert usage == {"bytes": 0, "files": 0}
