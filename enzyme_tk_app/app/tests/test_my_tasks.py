"""Tests for the My Tasks page and View Results page — layout, helpers, and callbacks."""

from unittest.mock import MagicMock, patch

import pytest
from dash import dcc, html
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server
from enzyme_tk_app.app.backend.models import JobStatus
from enzyme_tk_app.app.components.icons import ICON_JOB_BACK
from enzyme_tk_app.app.pages.my_tasks import (
    _build_job_row,
    _build_jobs_table,
    _build_stats,
    _build_status_badge,
    cancel_all_running_jobs,
    cancel_single_job,
    clear_finished_jobs,
    layout,
    load_jobs_table,
)
from enzyme_tk_app.app.pages.my_tasks_view_results import (
    _build_back_link,
    _build_job_info_header,
)
from enzyme_tk_app.app.pages.my_tasks_view_results import (
    layout as view_results_layout,
)

from .conftest import find_components, get_text, make_job

# ── _build_status_badge ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    list(JobStatus),
    ids=[s.value for s in JobStatus],
)
def test_build_status_badge_renders_for_every_status(status):
    """_build_status_badge must return a Span with the correct badge class and status text."""
    badge = _build_status_badge(status)

    assert isinstance(badge, html.Span)
    assert f"badge-{status.value}" in badge.className
    text = get_text(badge)
    assert status.value in text


# ── build_stat_card ──────────────────────────────────────────────────────────


def test_build_stat_card_renders_value_and_label():
    """build_stat_card must produce a card with the given value and label."""
    from enzyme_tk_app.app.components.results_helpers import build_stat_card

    card = build_stat_card(42, "Total Tasks")

    assert isinstance(card, html.Div)
    assert card.className == "jobs-stat-card"
    text = get_text(card)
    assert "42" in text
    assert "Total Tasks" in text


# ── _build_stats ─────────────────────────────────────────────────────────────


def test_build_stats_counts_jobs_correctly():
    """_build_stats must produce four stat cards with correct counts."""
    jobs = [
        make_job(status=JobStatus.SUCCESS),
        make_job(status=JobStatus.SUCCESS),
        make_job(status=JobStatus.PENDING),
        make_job(status=JobStatus.FAILURE),
        make_job(status=JobStatus.REVOKED),
    ]
    cards = _build_stats(jobs)

    assert len(cards) == 4

    # Total: 5, Running: 1, Completed: 2, Failed/Cancelled: 2
    assert "5" in get_text(cards[0])
    assert "1" in get_text(cards[1])
    assert "2" in get_text(cards[2])
    assert "2" in get_text(cards[3])


# ── _build_job_row ───────────────────────────────────────────────────────────


def test_build_job_row_success_has_view_results_link():
    """A successful job row must include a 'View Results' link."""
    job = make_job(job_id="abc-123456", status=JobStatus.SUCCESS)
    row = _build_job_row(job)

    assert isinstance(row, html.Tr)
    links = find_components(row, html.A)
    view_links = [a for a in links if "View Results" in get_text(a)]
    assert len(view_links) == 1
    assert f"/my-tasks/{job.job_id}" in view_links[0].href


def test_build_job_row_pending_has_cancel_button():
    """A pending job row must include a 'Cancel' button."""
    job = make_job(status=JobStatus.PENDING)
    row = _build_job_row(job)

    buttons = find_components(row, html.Button)
    cancel_buttons = [b for b in buttons if "Cancel" in get_text(b)]
    assert len(cancel_buttons) == 1


@pytest.mark.parametrize(
    "status",
    [JobStatus.FAILURE, JobStatus.REVOKED, JobStatus.TIMEOUT],
    ids=["failure", "revoked", "timeout"],
)
def test_build_job_row_terminal_non_success_has_view_details_link(status):
    """Terminal non-success jobs (FAILURE, REVOKED, TIMEOUT) must show a 'View Details' link."""
    job = make_job(job_id="abc-terminal", status=status)
    row = _build_job_row(job)

    links = find_components(row, html.A)
    detail_links = [a for a in links if "View Details" in get_text(a)]
    assert len(detail_links) == 1
    assert f"/my-tasks/{job.job_id}" in detail_links[0].href


def test_build_job_row_shows_truncated_job_id():
    """The job row must show a truncated ID with the full ID as a tooltip."""
    job = make_job(job_id="abcdef-123456789")
    row = _build_job_row(job)

    spans = find_components(row, html.Span)
    id_spans = [s for s in spans if getattr(s, "title", None) == "abcdef-123456789"]
    assert len(id_spans) == 1
    assert id_spans[0].children == "abcdef"


def test_build_job_row_completed_shows_computed_duration():
    """A completed job row must display the computed duration, not 'TBD'."""
    job = make_job(
        status=JobStatus.SUCCESS,
        started_at="2025-01-01T00:00:00+00:00",
        completed_at="2025-01-01T00:02:30+00:00",
    )
    row = _build_job_row(job)

    cells = row.children
    duration_cell = cells[5]  # Duration is the 6th column (index 5)
    assert "TBD" not in str(duration_cell.children)
    assert "2m 30s" in str(duration_cell.children)


@pytest.mark.parametrize("status", [JobStatus.PENDING, JobStatus.STARTED], ids=["pending", "started"])
def test_build_job_row_active_shows_tbd_duration(status):
    """Active (PENDING/STARTED) job rows must show 'TBD' in the Duration column."""
    job = make_job(status=status)
    row = _build_job_row(job)

    cells = row.children
    duration_cell = cells[5]  # Duration is the 6th column (index 5)
    assert duration_cell.children == "TBD"


# ── _build_jobs_table ────────────────────────────────────────────────────────


def test_build_jobs_table_empty_shows_placeholder():
    """An empty job list must render the empty-state placeholder."""
    result = _build_jobs_table([])

    assert isinstance(result, html.Div)
    text = get_text(result)
    assert "No tasks yet" in text


def test_build_jobs_table_with_jobs_renders_html_table():
    """A non-empty job list must render an html.Table with the correct row count."""
    jobs = [
        make_job(job_id="j1", status=JobStatus.SUCCESS),
        make_job(job_id="j2", status=JobStatus.PENDING),
    ]
    table = _build_jobs_table(jobs)

    assert isinstance(table, html.Table)
    rows = find_components(table, html.Tr)
    # 1 header row + 2 data rows = 3
    assert len(rows) == 3


def test_build_jobs_table_header_includes_duration_column():
    """The table header must include a 'Duration' column."""
    jobs = [make_job(job_id="j1", status=JobStatus.SUCCESS)]
    table = _build_jobs_table(jobs)

    header_row = find_components(table, html.Thead)[0].children
    header_texts = [get_text(th) for th in find_components(header_row, html.Th)]
    assert "Duration" in header_texts


def test_build_jobs_table_active_jobs_sorted_first():
    """Active jobs must appear before terminal jobs in the table."""
    jobs = [
        make_job(job_id="terminal", status=JobStatus.SUCCESS, submitted_at="2025-01-01T00:00:00+00:00"),
        make_job(job_id="active", status=JobStatus.PENDING, submitted_at="2025-01-01T00:01:00+00:00"),
    ]
    table = _build_jobs_table(jobs)

    body_rows = find_components(table, html.Tbody)[0].children
    # First data row should be the active (PENDING) job.
    first_row_badges = find_components(body_rows[0], html.Span)
    badge_texts = [
        get_text(b) for b in first_row_badges if getattr(b, "className", "") and "badge-status" in b.className
    ]
    assert any("PENDING" in t for t in badge_texts)


# ── layout ───────────────────────────────────────────────────────────────────


def test_layout_returns_div_with_required_elements():
    """layout() must return an html.Div with stats, table, toolbar, and auto-poll interval."""
    result = layout()

    assert isinstance(result, html.Div)

    # Must contain the auto-poll interval.
    intervals = find_components(result, dcc.Interval)
    assert any(getattr(i, "id", None) == "id-interval-jobs-poll" for i in intervals)

    # Must contain the page header text.
    text = get_text(result)
    assert "My Tasks" in text

    # Must contain toolbar buttons.
    buttons = find_components(result, html.Button)
    button_ids = [getattr(b, "id", None) for b in buttons]
    assert "id-btn-jobs-cancel-all" in button_ids
    assert "id-btn-jobs-clear-finished" in button_ids


# ── load_jobs_table (callback) ───────────────────────────────────────────────


def test_load_jobs_table_returns_stats_and_table():
    """load_jobs_table must return (stats children, table children)."""
    jobs = [make_job(status=JobStatus.SUCCESS)]
    mock_scheduler = MagicMock()
    mock_scheduler.list_jobs.return_value = jobs

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            stats, table = load_jobs_table(1)

    assert isinstance(stats, list)
    assert len(stats) == 4
    assert isinstance(table, html.Table)


# ── cancel_single_job (callback) ─────────────────────────────────────────────


def test_cancel_single_job_raises_prevent_update_when_no_click():
    """cancel_single_job must raise PreventUpdate when no button was clicked."""
    with patch("enzyme_tk_app.app.pages.my_tasks.ctx") as mock_ctx:
        mock_ctx.triggered_id = None
        with pytest.raises(PreventUpdate):
            cancel_single_job([], [])


def test_cancel_single_job_calls_scheduler():
    """cancel_single_job must call scheduler.cancel_job with the correct job ID."""
    mock_scheduler = MagicMock()

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with (
            patch("enzyme_tk_app.app.pages.my_tasks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.pages.my_tasks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = {"type": "id-btn-job-cancel", "index": "job-42"}
            cancel_single_job([1], [{"type": "id-btn-job-cancel", "index": "job-42"}])

    mock_scheduler.cancel_job.assert_called_once_with("job-42", "sess-test")


def test_cancel_single_job_raises_prevent_update_when_triggered_id_is_not_dict():
    """cancel_single_job must raise PreventUpdate when triggered_id is a string (not a dict)."""
    with patch("enzyme_tk_app.app.pages.my_tasks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "some-string-id"
        with pytest.raises(PreventUpdate):
            cancel_single_job([1], [{"type": "id-btn-job-cancel", "index": "job-42"}])


# ── cancel_all_running_jobs (callback) ───────────────────────────────────────


def test_cancel_all_running_jobs_raises_prevent_update_when_no_click():
    """cancel_all_running_jobs must raise PreventUpdate when n_clicks is 0."""
    with pytest.raises(PreventUpdate):
        cancel_all_running_jobs(0)


def test_cancel_all_running_jobs_cancels_only_active():
    """cancel_all_running_jobs must cancel PENDING/STARTED jobs but not terminal ones."""
    jobs = [
        make_job(job_id="active-1", status=JobStatus.PENDING),
        make_job(job_id="active-2", status=JobStatus.STARTED),
        make_job(job_id="done", status=JobStatus.SUCCESS),
    ]
    mock_scheduler = MagicMock()
    mock_scheduler.list_jobs.return_value = jobs

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            cancel_all_running_jobs(1)

    cancelled_ids = [call.args[0] for call in mock_scheduler.cancel_job.call_args_list]
    assert "active-1" in cancelled_ids
    assert "active-2" in cancelled_ids
    assert "done" not in cancelled_ids


# ── clear_finished_jobs (callback) ───────────────────────────────────────────


def test_clear_finished_jobs_raises_prevent_update_when_no_click():
    """clear_finished_jobs must raise PreventUpdate when n_clicks is 0."""
    with pytest.raises(PreventUpdate):
        clear_finished_jobs(0)


def test_clear_finished_jobs_calls_scheduler():
    """clear_finished_jobs must call scheduler.clear_jobs for the current session."""
    mock_scheduler = MagicMock()

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            clear_finished_jobs(1)

    mock_scheduler.clear_jobs.assert_called_once_with("sess-test")


# ══════════════════════════════════════════════════════════════════════════════
# View Results page (my_tasks_view_results.py)
# ══════════════════════════════════════════════════════════════════════════════


# ── _build_back_link ─────────────────────────────────────────────────────────


def test_build_back_link_returns_anchor_to_my_tasks():
    """_build_back_link must return an html.A linking to /my-tasks."""
    link = _build_back_link()

    assert isinstance(link, html.A)
    assert link.href == "/my-tasks"
    assert link.className == "jobs-back-link"


def test_build_back_link_contains_icon_and_text():
    """_build_back_link must contain a back-arrow icon and 'Back to My Tasks' text."""
    link = _build_back_link()

    icons = find_components(link, html.I)
    assert len(icons) == 1
    assert ICON_JOB_BACK in icons[0].className

    text = get_text(link)
    assert "Back to My Tasks" in text


# ── _build_job_info_header ───────────────────────────────────────────────────


def test_build_job_info_header_shows_tool_title():
    """The header must contain the tool title or fall back to the slug."""
    job = make_job(tool_slug="unknown-slug")
    header = _build_job_info_header(job)

    # Falls back to slug when no title found in _TOOL_TITLE_MAP.
    text = get_text(header)
    assert "unknown-slug" in text


def test_build_job_info_header_shows_status_badge():
    """The header must include a status badge matching the job status."""
    job = make_job(status=JobStatus.SUCCESS)
    header = _build_job_info_header(job)

    spans = find_components(header, html.Span)
    badge_spans = [s for s in spans if hasattr(s, "className") and s.className and "badge-status" in s.className]
    assert len(badge_spans) == 1
    assert "badge-SUCCESS" in badge_spans[0].className


def test_build_job_info_header_shows_job_id():
    """The header subtitle must contain the job ID."""
    job = make_job(job_id="abc-123")
    header = _build_job_info_header(job)

    text = get_text(header)
    assert "abc-123" in text


def test_build_job_info_header_duration_tbd_for_active_job():
    """Duration stat must show 'TBD' when the job is still active."""
    job = make_job(status=JobStatus.PENDING)
    header = _build_job_info_header(job)

    text = get_text(header)
    assert "TBD" in text


def test_build_job_info_header_includes_custom_stat_cards():
    """Custom _stat_cards from result must appear as extra stat cards."""
    job = make_job(
        result={
            "_stat_cards": [
                {"label": "Molecules", "value": "42"},
                {"label": "Databases", "value": "3"},
            ],
        },
    )
    header = _build_job_info_header(job)

    text = get_text(header)
    assert "Molecules" in text
    assert "42" in text
    assert "Databases" in text
    assert "3" in text


def test_build_job_info_header_ignores_non_list_stat_cards():
    """When _stat_cards is not a list, no extra stat cards should appear."""
    job = make_job(result={"_stat_cards": "not-a-list"})
    header = _build_job_info_header(job)

    # Should still render without error — only Duration and Expires In.
    stat_cards = [d for d in find_components(header, html.Div) if getattr(d, "className", None) == "jobs-stat-card"]
    assert len(stat_cards) == 2


def test_build_job_info_header_ignores_non_dict_items_in_stat_cards():
    """Non-dict items in _stat_cards must be silently skipped."""
    job = make_job(
        result={
            "_stat_cards": [
                {"label": "Valid", "value": "1"},
                "not-a-dict",
                42,
            ],
        },
    )
    header = _build_job_info_header(job)

    stat_cards = [d for d in find_components(header, html.Div) if getattr(d, "className", None) == "jobs-stat-card"]
    # Duration + Expires In + 1 valid custom card = 3
    assert len(stat_cards) == 3


def test_build_job_info_header_shows_computed_duration_for_completed_job():
    """Duration stat must show a computed value (not 'TBD') for a completed job."""
    job = make_job(
        status=JobStatus.SUCCESS,
        started_at="2025-01-01T00:00:00+00:00",
        completed_at="2025-01-01T00:05:30+00:00",
    )
    header = _build_job_info_header(job)

    text = get_text(header)
    assert "TBD" not in text
    assert "5m 30s" in text


def test_build_job_info_header_uses_known_tool_title():
    """When the tool slug matches a registered tool, the header must use its human-readable title."""
    from enzyme_tk_app.app.tools import TOOL_TITLE_MAP

    # Pick the first registered tool slug/title pair.
    slug, title = next(iter(TOOL_TITLE_MAP.items()))
    job = make_job(tool_slug=slug)
    header = _build_job_info_header(job)

    text = get_text(header)
    assert title in text


# ── view_results_layout — early returns ──────────────────────────────────────


@pytest.mark.parametrize("job_id", [None, ""], ids=["none", "empty"])
def test_view_results_layout_falsy_job_id_shows_error_message(job_id):
    """view_results_layout with a falsy job_id must show an error and a back link."""
    result = view_results_layout(job_id=job_id)

    assert isinstance(result, html.Div)
    text = get_text(result)
    assert "task id" in text.lower()

    # Back link must still be present.
    links = find_components(result, html.A)
    assert any(a.href == "/my-tasks" for a in links)


def test_view_results_layout_job_not_found_shows_not_found_message():
    """When get_job returns None, the page must show 'Task Not Found'."""
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = None

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="nonexistent-id")

    assert isinstance(result, html.Div)
    text = get_text(result)
    assert "Task Not Found" in text
    assert "does not exist" in text

    # Back link must still be present.
    links = find_components(result, html.A)
    assert any(a.href == "/my-tasks" for a in links)


# ── view_results_layout — status-specific content ────────────────────────────


def test_view_results_layout_success_renders_results_section():
    """A successful job must render a 'Results' heading and tool-specific content."""
    job = make_job(status=JobStatus.SUCCESS, result={"key": "value"})
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert "Results" in text


def test_view_results_layout_failure_renders_error_details():
    """A failed job must render error details."""
    job = make_job(status=JobStatus.FAILURE, error="Something went wrong")
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert "Error Details" in text
    assert "Something went wrong" in text


def test_view_results_layout_failure_no_error_shows_fallback():
    """A failed job with no error string must show a fallback message."""
    job = make_job(status=JobStatus.FAILURE, error=None)
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert "no error" in text.lower()


@pytest.mark.parametrize(
    "status, expected_keyword",
    [
        (JobStatus.PENDING, "queued"),
        (JobStatus.STARTED, "currently running"),
    ],
    ids=["pending", "started"],
)
def test_view_results_layout_active_shows_status_banner(status, expected_keyword):
    """An active job must show a status banner with a contextual message and auto-refresh interval."""
    job = make_job(status=status)
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert expected_keyword in text

    # Must include a dcc.Interval for auto-refresh.
    intervals = find_components(result, dcc.Interval)
    assert len(intervals) == 1


@pytest.mark.parametrize(
    "status, expected_heading",
    [
        (JobStatus.REVOKED, "Cancelled"),
        (JobStatus.TIMEOUT, "Timed Out"),
    ],
    ids=["revoked", "timeout"],
)
def test_view_results_layout_terminal_non_success_shows_message(status, expected_heading):
    """Terminal non-success jobs must show the appropriate heading."""
    job = make_job(status=status)
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert expected_heading in text


def test_view_results_layout_output_log_rendered_when_present():
    """When a job has an output_log, it must appear in the layout."""
    job = make_job(status=JobStatus.SUCCESS, output_log="Log line 1\nLog line 2")
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert "Output Log" in text
    assert "Log line 1" in text


def test_view_results_layout_no_output_log_omits_log_section():
    """When output_log is empty, the 'Output Log' heading must not appear."""
    job = make_job(status=JobStatus.SUCCESS, output_log="")
    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = job

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with patch(
            "enzyme_tk_app.app.pages.my_tasks_view_results.get_task_scheduler",
            return_value=mock_scheduler,
        ):
            result = view_results_layout(job_id="test-id")

    text = get_text(result)
    assert "Output Log" not in text
