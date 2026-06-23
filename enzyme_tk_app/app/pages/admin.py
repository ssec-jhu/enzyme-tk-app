"""Hidden admin dashboard — cross-session job and session management.

This page is intentionally **not** linked anywhere in the navbar.  It is
gated behind a shared token supplied at deploy time via the
``ETK_ADMIN_TOKEN`` environment variable (never committed to the repo).
When the token is unset the gate fails closed and the dashboard can never
be unlocked.

Once unlocked, the dashboard shows — across **all** anonymous sessions:

- Summary stat cards (sessions, jobs, running, succeeded, failed).
- A table of active sessions derived from job data.
- An AG Grid of every job with multi-row selection + bulk cancel.
- Two destructive maintenance actions, each behind a confirm dialog:
  - **Clear finished jobs** (``admin_clear_all_jobs``) — removes terminal
    jobs everywhere; users will no longer see their completed jobs.
  - **Purge everything** (``admin_purge_all``) — revokes running tasks and
    wipes all jobs, session sets, and volume files.

Every destructive callback re-verifies the admin flag server-side — hiding
the UI is never treated as sufficient protection.
"""

from __future__ import annotations

import hmac
import time

import dash
import dash_ag_grid as dag
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask import session

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.backend.config import ADMIN_SESSION_TTL_SECONDS, ADMIN_TOKEN
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.components.icons import (
    ICON_ADMIN_CANCEL_SELECTED,
    ICON_ADMIN_CLEAR,
    ICON_ADMIN_INFO,
    ICON_ADMIN_LOCK,
    ICON_ADMIN_PAGE,
    ICON_ADMIN_PURGE,
    ICON_ADMIN_SESSIONS,
)
from enzyme_tk_app.app.components.results_helpers import build_stat_card
from enzyme_tk_app.app.tools import TOOL_TITLE_MAP
from enzyme_tk_app.app.utils.formatting import compute_duration, expires_in, format_timestamp, truncate_id

dash.register_page(__name__, path="/admin")

# ----------------
# Constants
# ----------------

# Active statuses — jobs in these states are still running and can be cancelled.
_ACTIVE = {JobStatus.PENDING, JobStatus.STARTED}

# Auto-refresh cadence (ms).  Lighter than My Tasks (5 s) since admin polls
# scan every job across all sessions.
_POLL_INTERVAL_MS = 10_000


# ----------------
# Auth helpers
# ----------------


def _is_admin() -> bool:
    """Return ``True`` if the current Flask session is an unlocked admin.

    Enforces an idle timeout: a session is valid only while its sliding
    expiry is in the future.  Every authenticated check (including the
    dashboard's 10 s poll) pushes the expiry forward by
    ``ADMIN_SESSION_TTL_SECONDS``.  Once the tab closes the polling stops
    and the session lapses after that window, so admin access never lives
    on a device indefinitely.
    """
    if not session.get("is_admin", False):
        return False
    if time.time() >= session.get("admin_expires_at", 0):
        # Idle window elapsed — drop admin access.
        session.pop("is_admin", None)
        session.pop("admin_expires_at", None)
        return False
    # Slide the idle window forward on each authenticated request.
    session["admin_expires_at"] = time.time() + ADMIN_SESSION_TTL_SECONDS
    return True


def _grant_admin() -> None:
    """Mark the current session as an unlocked admin with a fresh idle window.

    The session is intentionally **not** made permanent, so the cookie
    remains a browser-session cookie that clears on browser close.
    """
    session["is_admin"] = True
    session["admin_expires_at"] = time.time() + ADMIN_SESSION_TTL_SECONDS


def _verify_token(token: str | None) -> bool:
    """Constant-time check of *token* against the configured admin token.

    Fails closed: when ``ADMIN_TOKEN`` is empty (the default for a public
    deployment with no token provisioned) no token can ever match.

    Args:
        token: The candidate token submitted via the login form.

    Returns:
        ``True`` only if a non-empty configured token matches *token*.
    """
    if not ADMIN_TOKEN:
        return False
    return hmac.compare_digest(token or "", ADMIN_TOKEN)


# ----------------
# Data builders
# ----------------


def _compute_stats(jobs: list[JobInfo]) -> list:
    """Build the five summary stat cards from all jobs.

    Args:
        jobs: Every job across all sessions.

    Returns:
        List of stat card components.
    """
    total = len(jobs)
    running = sum(1 for j in jobs if j.status in _ACTIVE)
    succeeded = sum(1 for j in jobs if j.status == JobStatus.SUCCESS)
    failed = sum(1 for j in jobs if j.status in {JobStatus.FAILURE, JobStatus.TIMEOUT})
    sessions = len({j.session_id for j in jobs})
    return [
        build_stat_card(sessions, "Active Sessions"),
        build_stat_card(total, "Jobs in System"),
        build_stat_card(running, "Active Jobs"),
        build_stat_card(succeeded, "Succeeded"),
        build_stat_card(failed, "Failed / Errored"),
    ]


def _jobs_to_rows(jobs: list[JobInfo]) -> list[dict]:
    """Convert jobs into AG Grid row dicts (active first, newest first).

    Args:
        jobs: Every job across all sessions.

    Returns:
        List of row dicts.  Each carries the full ``job_id`` (for cancel
        actions) plus display-friendly fields.
    """
    active = sorted((j for j in jobs if j.status in _ACTIVE), key=lambda j: j.submitted_at or "", reverse=True)
    terminal = sorted((j for j in jobs if j.status not in _ACTIVE), key=lambda j: j.submitted_at or "", reverse=True)
    rows: list[dict] = []
    for job in [*active, *terminal]:
        rows.append(
            {
                "job_id": job.job_id,
                "short_id": truncate_id(job.job_id),
                "tool": TOOL_TITLE_MAP.get(job.tool_slug, job.tool_slug),
                "session_id": job.session_id,
                "short_session": truncate_id(job.session_id),
                "status": job.status.value,
                "submitted": format_timestamp(job.submitted_at),
                "duration": "TBD" if job.status in _ACTIVE else compute_duration(job.started_at, job.completed_at),
                "expires_in": expires_in(job.submitted_at),
            }
        )
    return rows


def _sessions_to_rows(jobs: list[JobInfo]) -> list[dict]:
    """Aggregate jobs by session into AG Grid row dicts.

    Sessions are anonymous and only materialise once they own a job, so
    this is derived entirely from job data (no separate session registry).

    Args:
        jobs: Every job across all sessions.

    Returns:
        List of row dicts sorted by running count (busiest first).
    """
    by_session: dict[str, dict] = {}
    for job in jobs:
        info = by_session.setdefault(job.session_id, {"total": 0, "running": 0, "last": ""})
        info["total"] += 1
        if job.status in _ACTIVE:
            info["running"] += 1
        ts = job.submitted_at or ""
        if ts > info["last"]:
            info["last"] = ts
    rows = [
        {
            "session_id": session_id,
            "total": info["total"],
            "running": info["running"],
            "last_activity": format_timestamp(info["last"]),
        }
        for session_id, info in by_session.items()
    ]
    rows.sort(key=lambda r: (r["running"], r["total"]), reverse=True)
    return rows


# ----------------
# Grid factories
# ----------------


def _build_sessions_grid() -> dag.AgGrid:
    """Build the active-sessions AG Grid (row data filled by callback)."""
    return dag.AgGrid(
        id="id-grid-admin-sessions",
        columnDefs=[
            {"headerName": "Session ID", "field": "session_id", "width": 240},
            {"headerName": "Total Jobs", "field": "total", "width": 130, "filter": "agNumberColumnFilter"},
            {"headerName": "Running", "field": "running", "width": 120, "filter": "agNumberColumnFilter"},
            {"headerName": "Last Activity (UTC)", "field": "last_activity", "width": 200},
        ],
        rowData=[],
        defaultColDef={
            "resizable": True,
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 10,
            "paginationPageSizeSelector": True,
            "domLayout": "autoHeight",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
        },
        columnSize="responsiveSizeToFit",
        style={"width": "100%"},
        className="ag-theme-balham",
    )


def _build_jobs_grid() -> dag.AgGrid:
    """Build the all-jobs AG Grid with multi-row checkbox selection."""
    return dag.AgGrid(
        id="id-grid-admin-jobs",
        columnDefs=[
            # Full job id retained off-screen so selected rows carry it.
            {"headerName": "Session", "field": "short_session", "width": 130},
            {"field": "job_id", "hide": True},
            {
                "headerName": "Job",
                "field": "short_id",
                "width": 140,
                "checkboxSelection": True,
                "headerCheckboxSelection": True,
            },
            {"headerName": "Tool", "field": "tool", "width": 190},
            {
                "headerName": "Status",
                "field": "status",
                "width": 130,
                # render the status as a badge,
                # use the StatusBadgeRenderer javascript function to color the text
                "cellRenderer": "StatusBadgeRenderer",
            },
            {
                "headerName": "Submitted (UTC)",
                "field": "submitted",
                "width": 180,
                # sort the table on this column from latest time to oldest time
                "sort": "desc",
            },
            {"headerName": "Duration", "field": "duration", "width": 120},
            {"headerName": "Expires In", "field": "expires_in", "width": 130},
        ],
        rowData=[],
        defaultColDef={
            "resizable": True,
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
            "filterParams": {"buttons": ["reset", "apply"], "closeOnApply": True},
        },
        dashGridOptions={
            "rowSelection": "multiple",
            "suppressRowClickSelection": True,
            "pagination": True,
            "paginationPageSize": 20,
            "paginationPageSizeSelector": True,
            "domLayout": "normal",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            # "rowClassRules": {
            #     "ag-row-status-FAILURE": "params.data && params.data.status === 'FAILURE'",
            #     "ag-row-status-TIMEOUT": "params.data && params.data.status === 'TIMEOUT'",
            #     "ag-row-status-REVOKED": "params.data && params.data.status === 'REVOKED'",
            #     #"ag-row-status-SUCCESS": "params.data && params.data.status === 'SUCCESS'",
            #     "ag-row-status-STARTED": "params.data && params.data.status === 'STARTED'",
            # },
        },
        columnSize="responsiveSizeToFit",
        style={"width": "100%", "height": "600px"},
        className="ag-theme-balham",
    )


# ----------------
# Layout sections
# ----------------


def _login_layout(error: str | None = None) -> html.Div:
    """Render the token login card.

    Args:
        error: Optional error message to show beneath the input.

    Returns:
        An ``html.Div`` containing the login form.
    """
    children = [
        # icon for the admin login card
        html.Div(html.I(className=ICON_ADMIN_LOCK), className="admin-login-icon"),
        html.H2("Admin Access", style={"margin": "0 0 0.5rem 0"}),
        html.P(
            "Enter the admin token to manage sessions and jobs.",
            className="jobs-page-subtitle",
            style={"marginBottom": "1rem"},
        ),
        # user input for the admin token
        dcc.Input(
            id="id-input-admin-token",
            type="password",
            placeholder="Admin token",
            className="admin-login-input",
            n_submit=0,
            debounce=False,
        ),
        # submit button for the admin token
        html.Button(
            children=[html.I(className=ICON_ADMIN_LOCK), "Unlock"],
            id="id-btn-admin-login",
            className="btn-toolbar danger",
            n_clicks=0,
        ),
    ]
    # append error message if present
    if error:
        children.append(html.Div(error, className="admin-login-error"))

    # return the login card container layout,
    # no action here just creating the layout
    return html.Div(html.Div(children, className="admin-login-card"), className="admin-login-wrap")


def _dashboard_layout() -> html.Div:
    """Render the full admin dashboard (populated by callbacks)."""
    return html.Div(
        className="jobs-page",
        children=[
            # Page header with the icon and title
            html.Div(
                className="jobs-page-header",
                children=[
                    html.I(className=f"{ICON_ADMIN_PAGE} jobs-page-header-icon"),
                    html.H2("Admin Dashboard", style={"margin": "0"}),
                ],
            ),
            html.P(
                "Monitor and manage sessions and jobs across all users.",
                className="jobs-page-subtitle",
            ),
            # Live dashboard info banner.
            html.Div(
                className="admin-info-banner",
                children=[
                    html.I(className=ICON_ADMIN_INFO),
                    html.Span(
                        [
                            html.Strong("Live Dashboard"),
                            " — This dashboard shows a real-time snapshot. If a user clears "
                            "their session or deletes jobs, those entries disappear from the "
                            "tables and counts below immediately.",
                        ]
                    ),
                ],
            ),
            # Summary stat cards — populated by callback.
            html.Div(id="id-div-admin-stats", className="jobs-stats-row"),
            # Action feedback (populated by destructive-action callbacks).
            html.Div(id="id-div-admin-action-result", className="admin-action-result"),
            # --------------------
            # All jobs section
            # --------------------
            html.Div(
                children=[
                    html.Div(
                        className="jobs-page-header",
                        # style={"marginBottom": "0"},
                        children=[
                            html.I(className=f"{ICON_ADMIN_PAGE} jobs-page-header-icon"),
                            html.H3("All Jobs", style={"margin": "0"}),
                        ],
                    ),
                    html.Button(
                        children=[html.I(className=ICON_ADMIN_CANCEL_SELECTED), "Cancel Selected"],
                        id="id-btn-admin-cancel-selected",
                        className="btn-toolbar danger",
                        n_clicks=0,
                    ),
                ],
                # I need the title, icon and button to be aligned properly.
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "marginTop": "1.5rem",
                    "marginBottom": "0.5rem",
                },
            ),
            _build_jobs_grid(),
            # --------------------
            # Active sessions section.
            # --------------------
            html.Div(
                className="jobs-page-header",
                style={"marginTop": "1.5rem"},
                children=[
                    html.I(className=f"{ICON_ADMIN_SESSIONS} jobs-page-header-icon"),
                    html.H3("Active Sessions", style={"margin": "0"}),
                ],
            ),
            _build_sessions_grid(),
            # --------------------
            # Danger zone — destructive maintenance actions.
            # --------------------
            html.Div(
                className="admin-danger-zone",
                children=[
                    html.H3("Danger Zone", className="admin-danger-title"),
                    html.P(
                        "These actions affect every user and cannot be undone.",
                        className="jobs-page-subtitle",
                    ),
                    html.Div(
                        className="admin-danger-desc",
                        children=[
                            html.P(
                                [
                                    html.Strong("Clear Finished Jobs"),
                                    " — Removes all completed, failed, timed-out, and revoked "
                                    "jobs from Redis. Running and pending jobs are not affected. "
                                    "Users will no longer see cleared jobs on their My Tasks page, "
                                    "but any result files on the shared volume are left intact.",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Purge Everything"),
                                    " — Full reset: revokes all running tasks, deletes every job "
                                    "and session record from Redis, and wipes all result files "
                                    "from the shared volume. This is irreversible and affects "
                                    "every user immediately.",
                                ]
                            ),
                        ],
                    ),
                    html.Div(
                        className="jobs-toolbar",
                        children=[
                            html.Button(
                                children=[html.I(className=ICON_ADMIN_CLEAR), "Clear Finished Jobs"],
                                id="id-btn-admin-clear",
                                className="btn-toolbar",
                                n_clicks=0,
                            ),
                            html.Button(
                                children=[html.I(className=ICON_ADMIN_PURGE), "Purge Everything"],
                                id="id-btn-admin-purge",
                                className="btn-toolbar danger",
                                n_clicks=0,
                            ),
                        ],
                    ),
                ],
            ),
            # Confirm dialogs for the two destructive actions.
            dcc.ConfirmDialog(
                id="id-confirm-admin-clear",
                message=(
                    "Clear ALL finished jobs across every session?\n\n"
                    "This permanently removes completed, failed, revoked, and timed-out "
                    "jobs from Redis. Affected users will no longer see those jobs in "
                    "their My Tasks page. Running jobs are not affected."
                ),
            ),
            dcc.ConfirmDialog(
                id="id-confirm-admin-purge",
                message=(
                    "PURGE EVERYTHING?\n\n"
                    "This revokes all running tasks and permanently deletes ALL jobs, "
                    "session data, and result files from the shared volume. This is a "
                    "full reset and cannot be undone."
                ),
            ),
            # Auto-refresh interval + store that bumps after each action.
            dcc.Interval(id="id-interval-admin-poll", interval=_POLL_INTERVAL_MS, n_intervals=0),
            dcc.Store(id="id-store-admin-refresh", data=0),
        ],
    )


def layout() -> html.Div:
    """Return the admin page layout, gated by the session admin flag.

    Returns:
        The dashboard when the session is an unlocked admin, otherwise the
        token login card.  The root div is swapped by the login callback.
    """
    return html.Div(
        id="id-div-admin-root",
        children=_dashboard_layout() if _is_admin() else _login_layout(),
    )


# ----------------
# Callbacks
# ----------------


@callback(
    Output("id-div-admin-root", "children"),
    Input("id-btn-admin-login", "n_clicks"),
    Input("id-input-admin-token", "n_submit"),
    State("id-input-admin-token", "value"),
    prevent_initial_call=True,
)
def unlock_admin_dashboard(n_clicks: int, n_submit: int, token: str | None) -> html.Div:
    """Validate the submitted token and swap in the dashboard on success.

    Args:
        n_clicks: Unlock button click count.
        n_submit: Enter-key submit count from the token input.
        token: The submitted token value.

    Returns:
        The dashboard layout on success, otherwise the login card with an
        error message.

    Raises:
        PreventUpdate: When neither the button nor Enter was used.
    """
    if not n_clicks and not n_submit:
        raise PreventUpdate
    if not _verify_token(token):
        return _login_layout(error="Invalid token. Access denied.")
    _grant_admin()
    return _dashboard_layout()


@callback(
    Output("id-div-admin-stats", "children"),
    Output("id-grid-admin-sessions", "rowData"),
    Output("id-grid-admin-jobs", "rowData"),
    Input("id-interval-admin-poll", "n_intervals"),
    Input("id-store-admin-refresh", "data"),
)
def refresh_admin_dashboard(n_intervals: int, refresh_token: int) -> tuple:
    """Rebuild the stats cards and both grids from current backend state.

    Triggered by the poll interval and the post-action refresh store.

    Args:
        n_intervals: Auto-poll tick count.
        refresh_token: Bumped by action callbacks to force a refresh.

    Returns:
        Tuple of (stat cards, session rows, job rows).

    Raises:
        PreventUpdate: When the session is not an unlocked admin.
    """
    if not _is_admin():
        raise PreventUpdate
    scheduler = get_task_scheduler()
    jobs = scheduler.admin_list_all_jobs()
    return _compute_stats(jobs), _sessions_to_rows(jobs), _jobs_to_rows(jobs)


@callback(
    Output("id-store-admin-refresh", "data", allow_duplicate=True),
    Output("id-div-admin-action-result", "children", allow_duplicate=True),
    Input("id-btn-admin-cancel-selected", "n_clicks"),
    State("id-grid-admin-jobs", "selectedRows"),
    prevent_initial_call=True,
)
def cancel_selected_admin_jobs(n_clicks: int, selected_rows: list[dict] | None) -> tuple:
    """Cancel every selected running job (admin override, no ownership check).

    Args:
        n_clicks: Cancel-selected button click count.
        selected_rows: Rows currently selected in the jobs grid.

    Returns:
        Tuple of (refresh-store bump, feedback message).

    Raises:
        PreventUpdate: When the button was not clicked or not an admin.
    """
    if not n_clicks or not _is_admin():
        raise PreventUpdate
    if not selected_rows:
        return no_update, "No jobs selected."
    scheduler = get_task_scheduler()
    cancelled = 0
    for row in selected_rows:
        job_id = row.get("job_id")
        if job_id and scheduler.cancel_job(job_id):
            cancelled += 1
    return time.time(), f"Cancelled {cancelled} running job(s)."


@callback(
    Output("id-confirm-admin-clear", "displayed"),
    Input("id-btn-admin-clear", "n_clicks"),
    prevent_initial_call=True,
)
def prompt_admin_clear(n_clicks: int) -> bool:
    """Open the confirm dialog for clearing all finished jobs.

    Args:
        n_clicks: Clear button click count.

    Returns:
        ``True`` to display the confirm dialog.

    Raises:
        PreventUpdate: When the button was not clicked or not an admin.
    """
    if not n_clicks or not _is_admin():
        raise PreventUpdate
    return True


@callback(
    Output("id-store-admin-refresh", "data", allow_duplicate=True),
    Output("id-div-admin-action-result", "children", allow_duplicate=True),
    Input("id-confirm-admin-clear", "submit_n_clicks"),
    prevent_initial_call=True,
)
def run_admin_clear(submit_n_clicks: int) -> tuple:
    """Clear all finished jobs across every session after confirmation.

    Args:
        submit_n_clicks: Confirm-dialog OK click count.

    Returns:
        Tuple of (refresh-store bump, feedback message).

    Raises:
        PreventUpdate: When not confirmed or not an admin.
    """
    if not submit_n_clicks or not _is_admin():
        raise PreventUpdate
    scheduler = get_task_scheduler()
    count = scheduler.admin_clear_all_jobs()
    return time.time(), f"Cleared {count} finished job(s)."


@callback(
    Output("id-confirm-admin-purge", "displayed"),
    Input("id-btn-admin-purge", "n_clicks"),
    prevent_initial_call=True,
)
def prompt_admin_purge(n_clicks: int) -> bool:
    """Open the confirm dialog for the full purge.

    Args:
        n_clicks: Purge button click count.

    Returns:
        ``True`` to display the confirm dialog.

    Raises:
        PreventUpdate: When the button was not clicked or not an admin.
    """
    if not n_clicks or not _is_admin():
        raise PreventUpdate
    return True


@callback(
    Output("id-store-admin-refresh", "data", allow_duplicate=True),
    Output("id-div-admin-action-result", "children", allow_duplicate=True),
    Input("id-confirm-admin-purge", "submit_n_clicks"),
    prevent_initial_call=True,
)
def run_admin_purge(submit_n_clicks: int) -> tuple:
    """Purge all jobs, sessions, and volume files after confirmation.

    Args:
        submit_n_clicks: Confirm-dialog OK click count.

    Returns:
        Tuple of (refresh-store bump, feedback message summarising the purge).

    Raises:
        PreventUpdate: When not confirmed or not an admin.
    """
    if not submit_n_clicks or not _is_admin():
        raise PreventUpdate
    scheduler = get_task_scheduler()
    summary = scheduler.admin_purge_all()
    message = (
        f"Purged everything — {summary.get('jobs_deleted', 0)} jobs, "
        f"{summary.get('sessions_cleared', 0)} sessions, "
        f"{summary.get('tasks_revoked', 0)} tasks revoked, "
        # f"{format_bytes(summary.get('volume_bytes_freed', 0))} freed "
        f"({summary.get('volume_files_deleted', 0)} files)."
    )
    return time.time(), message
