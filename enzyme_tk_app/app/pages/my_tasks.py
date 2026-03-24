"""My Tasks page — lists all tasks submitted by the current session.

Displays a stats summary, toolbar with bulk actions, and a table of tasks
with per-row cancel and view-results buttons.  Auto-polls every 5 seconds
to refresh running task statuses.

Callbacks handle:
- Auto-polling to refresh the tasks table and stats summary.
- Cancelling individual tasks via pattern-matching callbacks.
- Bulk cancel of all running tasks.
- Clearing all finished tasks.
"""

from __future__ import annotations

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate
from dash.html import Div, Table
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.components.icons import (
    ICON_JOB_CANCEL,
    ICON_JOB_CANCEL_ALL,
    ICON_JOB_CLEAR,
    ICON_JOB_VIEW,
    ICON_JOBS_PAGE,
    ICON_STATUS_FAILURE,
    ICON_STATUS_PENDING,
    ICON_STATUS_REVOKED,
    ICON_STATUS_STARTED,
    ICON_STATUS_SUCCESS,
    ICON_STATUS_TIMEOUT,
)
from enzyme_tk_app.app.tools import TOOLS
from enzyme_tk_app.app.utils.formatting import expires_in, format_duration, format_timestamp

dash.register_page(__name__, path="/my-tasks")

# ----------------
# Constants
# ----------------

# Map tool slug → tool title for display.
_TOOL_TITLE_MAP: dict[str, str] = {t["slug"]: t["title"] for t in TOOLS}

# Map tool slug → max_duration for "expected runtime" display.
_TOOL_MAX_DURATION: dict[str, int] = {t["slug"]: t.get("max_duration", 3600) for t in TOOLS}

# Map JobStatus → (icon class, CSS badge class suffix).
_STATUS_ICONS: dict[JobStatus, str] = {
    JobStatus.PENDING: ICON_STATUS_PENDING,
    JobStatus.STARTED: ICON_STATUS_STARTED,
    JobStatus.SUCCESS: ICON_STATUS_SUCCESS,
    JobStatus.FAILURE: ICON_STATUS_FAILURE,
    JobStatus.REVOKED: ICON_STATUS_REVOKED,
    JobStatus.TIMEOUT: ICON_STATUS_TIMEOUT,
}

# Terminal statuses — jobs in these states can be cleared.
_TERMINAL = {JobStatus.SUCCESS, JobStatus.FAILURE, JobStatus.REVOKED, JobStatus.TIMEOUT}

# Active statuses — jobs in these states can be cancelled.
_ACTIVE = {JobStatus.PENDING, JobStatus.STARTED}


# ----------------
# Layout
# ----------------


def _build_status_badge(status: JobStatus) -> html.Span:
    """Render a colored status badge.

    Args:
        status: The job's current status.

    Returns:
        An ``html.Span`` with the appropriate CSS class and icon.
    """
    icon_class = _STATUS_ICONS.get(status, ICON_STATUS_PENDING)
    return html.Span(
        className=f"badge-status badge-{status.value}",
        children=[
            html.I(className=f"{icon_class} badge-status-icon"),
            status.value,
        ],
    )


def _build_stat_card(value: int | str, label: str) -> html.Div:
    """Render a single stat card for the summary row.

    Args:
        value: The numeric or string value to display.
        label: The label beneath the value.

    Returns:
        An ``html.Div`` styled as a stat card.
    """
    return html.Div(
        className="jobs-stat-card",
        children=[
            html.Div(str(value), className="jobs-stat-value"),
            html.Div(label, className="jobs-stat-label"),
        ],
    )


def _build_stats(jobs: list[JobInfo]) -> list:
    """Build the stats summary cards from a list of jobs.

    Args:
        jobs: All jobs for the current session.

    Returns:
        List of stat card components.
    """
    total = len(jobs)
    running = sum(1 for j in jobs if j.status in _ACTIVE)
    completed = sum(1 for j in jobs if j.status == JobStatus.SUCCESS)
    failed = sum(1 for j in jobs if j.status in {JobStatus.FAILURE, JobStatus.TIMEOUT, JobStatus.REVOKED})
    return [
        _build_stat_card(total, "Total Tasks"),
        _build_stat_card(running, "Running"),
        _build_stat_card(completed, "Completed"),
        _build_stat_card(failed, "Failed / Cancelled"),
    ]


def _build_job_row(job: JobInfo) -> html.Tr:
    """Render a single table row for a task.

    Args:
        job: The ``JobInfo`` to render.

    Returns:
        An ``html.Tr`` with task ID, task name, tool name, status badge,
        submitted time, expected duration, expiry countdown, and action buttons.
    """
    tool_title = _TOOL_TITLE_MAP.get(job.tool_slug, job.tool_slug)
    max_dur = _TOOL_MAX_DURATION.get(job.tool_slug, 3600)
    task_name = (job.params or {}).get("task_name", "") or ""

    # Truncated task ID: show last 6 characters, hover reveals the full ID.
    short_id = f"...{job.job_id[-6:]}" if len(job.job_id) > 6 else job.job_id

    # Action buttons
    actions = []
    if job.status == JobStatus.SUCCESS:
        actions.append(
            html.A(
                className="btn-job-action view-results",
                href=f"/my-tasks/{job.job_id}",
                children=[
                    html.I(className=ICON_JOB_VIEW),
                    "View Results",
                ],
            ),
        )
    elif job.status in {JobStatus.FAILURE, JobStatus.REVOKED, JobStatus.TIMEOUT}:
        # Terminal non-success states — let the user inspect error / status info
        actions.append(
            html.A(
                className="btn-job-action view-results",
                href=f"/my-tasks/{job.job_id}",
                children=[
                    html.I(className=ICON_JOB_VIEW),
                    "View Details",
                ],
            ),
        )
    if job.status in _ACTIVE:
        actions.append(
            html.A(
                className="btn-job-action view-results",
                href=f"/my-tasks/{job.job_id}",
                children=[
                    html.I(className=ICON_JOB_VIEW),
                    "View Details",
                ],
            ),
        )
        actions.append(
            html.Button(
                id={"type": "id-btn-job-cancel", "index": job.job_id},
                className="btn-job-action cancel",
                children=[
                    html.I(className=ICON_JOB_CANCEL),
                    "Cancel",
                ],
                n_clicks=0,
            ),
        )

    return html.Tr(
        children=[
            html.Td(
                html.Span(short_id, title=job.job_id, style={"cursor": "help"}),
            ),
            html.Td(task_name or "—"),
            html.Td(tool_title),
            html.Td(_build_status_badge(job.status)),
            html.Td(format_timestamp(job.submitted_at)),
            html.Td(format_duration(max_dur)),
            html.Td(expires_in(job.submitted_at)),
            html.Td(
                html.Div(
                    className="jobs-actions-cell",
                    children=actions if actions else [html.Span("—", className="text-secondary")],
                ),
            ),
        ],
    )


def _build_jobs_table(jobs: list[JobInfo]) -> Div | Table:
    """Build the full jobs table or an empty-state placeholder.

    Args:
        jobs: All jobs for the current session.

    Returns:
        An ``html.Div`` containing the table or empty state.
    """
    if not jobs:
        return html.Div(
            className="jobs-empty",
            children=[
                html.Div(
                    html.I(className=ICON_JOBS_PAGE),
                    className="jobs-empty-icon",
                ),
                html.P("No tasks yet. Submit a task from any tool to get started."),
            ],
        )

    # Sort jobs: active first, then by submitted_at descending.
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (j.status not in _ACTIVE, j.submitted_at or ""),
        reverse=False,
    )
    # Within the active group we want newest first, terminal group also newest first
    active = [j for j in sorted_jobs if j.status in _ACTIVE]
    terminal = [j for j in sorted_jobs if j.status not in _ACTIVE]
    active.sort(key=lambda j: j.submitted_at or "", reverse=True)
    terminal.sort(key=lambda j: j.submitted_at or "", reverse=True)
    ordered = active + terminal

    return html.Table(
        className="jobs-table",
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Task ID"),
                        html.Th("Task Name"),
                        html.Th("Tool"),
                        html.Th("Status"),
                        html.Th("Submitted (UTC)"),
                        html.Th("Max Runtime"),
                        html.Th("Expires In"),
                        html.Th("Actions"),
                    ]
                ),
            ),
            html.Tbody([_build_job_row(j) for j in ordered]),
        ],
    )


def layout() -> html.Div:
    """Return the My Tasks page layout.

    The stats summary and tasks table are populated by the callbacks
    defined below.

    Returns:
        An ``html.Div`` containing the page header, stats, toolbar,
        and auto-refreshing tasks table.
    """
    return html.Div(
        className="jobs-page",
        children=[
            # Page header
            html.Div(
                className="jobs-page-header",
                children=[
                    html.I(
                        className=f"{ICON_JOBS_PAGE} jobs-page-header-icon",
                    ),
                    html.H2("My Tasks", style={"margin": "0"}),
                ],
            ),
            html.P(
                "Track your submitted tasks, view results, or cancel running ones.",
                className="jobs-page-subtitle",
            ),
            # Stats summary — populated by callback
            html.Div(id="id-div-jobs-stats", className="jobs-stats-row"),
            # -------------------------------------
            # Buttons for bulk actions on multiple jobs
            # -------------------------------------
            html.Div(
                className="jobs-toolbar",
                children=[
                    html.Button(
                        id="id-btn-jobs-cancel-all",
                        className="btn-toolbar danger",
                        children=[
                            html.I(className=ICON_JOB_CANCEL_ALL),
                            "Cancel All Running",
                        ],
                        n_clicks=0,
                    ),
                    html.Button(
                        id="id-btn-jobs-clear-finished",
                        className="btn-toolbar",
                        children=[
                            html.I(className=ICON_JOB_CLEAR),
                            "Clear Finished",
                        ],
                        n_clicks=0,
                    ),
                ],
            ),
            # -------------------------------------
            # Jobs table — populated by callback
            # -------------------------------------
            html.Div(id="id-div-jobs-table"),
            # Auto-poll interval (5 s)
            dcc.Interval(
                id="id-interval-jobs-poll",
                interval=5000,
                n_intervals=0,
            ),
            # Hidden div to absorb action callback outputs
            html.Div(id="id-div-jobs-action-sink", style={"display": "none"}),
        ],
    )


# --------------------
# Callbacks
# --------------------


@callback(
    Output("id-div-jobs-stats", "children"),
    Output("id-div-jobs-table", "children"),
    Input("id-interval-jobs-poll", "n_intervals"),
)
def load_jobs_table(n_intervals: int) -> tuple:
    """Refresh the tasks stats and table.

    Triggered by the 5-second poll interval.

    Args:
        n_intervals: Auto-poll tick count.

    Returns:
        Tuple of (stats children, table children).
    """
    scheduler = get_task_scheduler()
    jobs = scheduler.list_jobs(g.session_id)
    return _build_stats(jobs), _build_jobs_table(jobs)


@callback(
    Output("id-div-jobs-action-sink", "children", allow_duplicate=True),
    Input({"type": "id-btn-job-cancel", "index": ALL}, "n_clicks"),
    State({"type": "id-btn-job-cancel", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def cancel_single_job(n_clicks_list: list[int], ids: list[dict]) -> str:
    """Cancel an individual task when its cancel button is clicked.

    Args:
        n_clicks_list: Click counts for all cancel buttons.
        ids: Pattern-matching IDs containing the job_id in ``index``.

    Raises:
        PreventUpdate: When no cancel button was actually clicked.
    """
    if not ctx.triggered_id or not any(n_clicks_list):
        raise PreventUpdate
    job_id = ctx.triggered_id.get("index", "") if isinstance(ctx.triggered_id, dict) else ""
    if not job_id:
        raise PreventUpdate
    scheduler = get_task_scheduler()
    scheduler.cancel_job(job_id, g.session_id)
    return ""


@callback(
    Output("id-div-jobs-action-sink", "children", allow_duplicate=True),
    Input("id-btn-jobs-cancel-all", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_all_running_jobs(n_clicks: int) -> str:
    """Cancel every PENDING or STARTED task for the current session.

    Args:
        n_clicks: Button click count.

    Raises:
        PreventUpdate: When the button has not been clicked.
    """
    if not n_clicks:
        raise PreventUpdate
    scheduler = get_task_scheduler()
    jobs = scheduler.list_jobs(g.session_id)
    for job in jobs:
        if job.status in _ACTIVE:
            scheduler.cancel_job(job.job_id, g.session_id)
    return ""


@callback(
    Output("id-div-jobs-action-sink", "children", allow_duplicate=True),
    Input("id-btn-jobs-clear-finished", "n_clicks"),
    prevent_initial_call=True,
)
def clear_finished_jobs(n_clicks: int) -> str:
    """Remove all terminal-status tasks for the current session.

    Args:
        n_clicks: Button click count.

    Raises:
        PreventUpdate: When the button has not been clicked.
    """
    if not n_clicks:
        raise PreventUpdate
    scheduler = get_task_scheduler()
    scheduler.clear_jobs(g.session_id)
    return ""
