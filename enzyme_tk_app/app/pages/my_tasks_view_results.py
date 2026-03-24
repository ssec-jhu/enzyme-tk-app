"""Task Results page — renders tool-specific output for a given task."""

from __future__ import annotations

import dash
from dash import Input, Output, dcc, html
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.components.icons import (
    ICON_JOB_BACK,
    ICON_JOBS_PAGE,
    ICON_STATUS_FAILURE,
    ICON_STATUS_PENDING,
    ICON_STATUS_REVOKED,
    ICON_STATUS_STARTED,
    ICON_STATUS_SUCCESS,
    ICON_STATUS_TIMEOUT,
)
from enzyme_tk_app.app.components.results_helpers import build_result_input_params
from enzyme_tk_app.app.tools import RESULTS_LAYOUTS, TOOLS, default_results_layout
from enzyme_tk_app.app.utils.formatting import compute_duration, expires_in, format_timestamp

dash.register_page(__name__, path_template="/my-tasks/<job_id>")

# Active statuses — tasks still in progress.
_ACTIVE = {JobStatus.PENDING, JobStatus.STARTED}

# Status messages for the in-progress banner.
_STATUS_MESSAGES: dict[JobStatus, str] = {
    JobStatus.PENDING: "Your task is queued and waiting to start.",
    JobStatus.STARTED: "Your task is currently running.",
}

# --- Helpers ---------------------------------------------------------------

# Map slug → title for display.
_TOOL_TITLE_MAP: dict[str, str] = {t["slug"]: t["title"] for t in TOOLS}

# Map status → icon.
_STATUS_ICONS: dict[JobStatus, str] = {
    JobStatus.PENDING: ICON_STATUS_PENDING,
    JobStatus.STARTED: ICON_STATUS_STARTED,
    JobStatus.SUCCESS: ICON_STATUS_SUCCESS,
    JobStatus.FAILURE: ICON_STATUS_FAILURE,
    JobStatus.REVOKED: ICON_STATUS_REVOKED,
    JobStatus.TIMEOUT: ICON_STATUS_TIMEOUT,
}


def _build_back_link() -> html.A:
    """Build the 'Back to My Tasks' navigation link.

    Returns:
        An ``html.A`` anchor linking back to the ``/my-tasks`` page.
    """
    return html.A(
        className="jobs-back-link",
        href="/my-tasks",
        children=[
            html.I(className=f"{ICON_JOB_BACK} jobs-back-link-icon"),
            "Back to My Tasks",
        ],
    )


def _build_job_info_header(job: JobInfo) -> html.Div:
    """Build the unified task info header shown on every results page.

    Args:
        job: The ``JobInfo`` object to display.

    Returns:
        An ``html.Div`` with a page header, subtitle, and stat cards.
    """
    # Get the tool title and status icon, with fallbacks for unknown slugs or statuses.
    tool_title = _TOOL_TITLE_MAP.get(job.tool_slug, job.tool_slug)
    status_icon = _STATUS_ICONS.get(job.status, ICON_STATUS_PENDING)

    # Page header: icon + title + status badge (matches my_tasks page header)
    page_header = html.Div(
        className="jobs-page-header",
        children=[
            # Icon + title + status badge
            html.I(className=f"{ICON_JOBS_PAGE} jobs-page-header-icon"),
            html.H2(f"{tool_title} — Task Details", style={"margin": "0"}),
            html.Span(
                className=f"badge-status badge-{job.status.value}",
                children=[
                    html.I(className=f"{status_icon} badge-status-icon"),
                    job.status.value,
                ],
            ),
        ],
    )
    # Task ID has a tooltip showing the full UUID, and the submission time is formatted for readability.
    subtitle = html.P(
        children=[
            html.Span(
                f"Task {job.job_id}",
                title=job.job_id,
                style={"cursor": "help"},
            ),
            f"  ·  Submitted {format_timestamp(job.submitted_at)}",
        ],
        className="jobs-page-subtitle",
    )

    # Core job stats — show "TBD" for duration when the job is still active.
    is_active = job.status in _ACTIVE
    duration_value = "TBD" if is_active else compute_duration(job.started_at, job.completed_at)
    stats: list[tuple[str, str]] = [
        ("Duration", duration_value),
        ("Expires In", expires_in(job.submitted_at)),
    ]

    # ------------------------------
    # If the tool returns custom _meta stats,
    # they will be appended to the Duration and Expires In cards.
    # ---------------------------------
    # Merge tool-specific _meta items (e.g. Summary stats) into the grid
    meta_items = (job.result or {}).get("_meta")
    if meta_items and isinstance(meta_items, list):
        stats.extend(
            (str(item.get("label", "")), str(item.get("value", ""))) for item in meta_items if isinstance(item, dict)
        )

    # Build unified stat cards (same style as My Tasks page)
    stat_cards = html.Div(
        className="jobs-stats-row",
        children=[
            html.Div(
                className="jobs-stat-card",
                children=[
                    html.Div(value, className="jobs-stat-value"),
                    html.Div(label, className="jobs-stat-label"),
                ],
            )
            for label, value in stats
        ],
    )

    return html.Div(children=[page_header, subtitle, stat_cards])


# --- Layout ----------------------------------------------------------------


def layout(job_id: str | None = None) -> html.Div:
    """Render the results page for a specific job.

    The page has two sections:

    1. **Job info header** — common to all tools (tool name, status,
       timestamps, duration, expiry): ``_build_job_info_header()``
    2. **Tool-specific content** — rendered by the tool's
       ``results_layout(job_info)`` if available, otherwise by
       ``default_results_layout``.

    Args:
        job_id: The UUID of the task to display.  Injected by Dash
            from the URL path ``/my-tasks/<job_id>``.

    Returns:
        An ``html.Div`` with the back link, job info header, and
        tool-specific results or status message.
    """
    # Back link always shown
    shared_back_to_my_tasks_link = _build_back_link()

    # Validate job_id and fetch job info.
    # If invalid or inaccessible, show an error message but keep the back link.
    if not job_id:
        return html.Div(className="jobs-page", children=[shared_back_to_my_tasks_link, html.P("No task ID provided.")])

    # get_job may return None if the job_id is invalid or does not belong to this session
    job = get_task_scheduler().get_job(job_id, g.session_id)

    if job is None:
        # Show an error message if the job doesn't exist or isn't accessible, but still render the back link.
        return html.Div(
            className="jobs-page",
            children=[
                shared_back_to_my_tasks_link,
                html.H3("Task Not Found", style={"marginTop": "1rem"}),
                html.P(
                    "This task does not exist or does not belong to your session. It may have expired.",
                    style={"color": "var(--text-secondary)"},
                ),
            ],
        )

    # Shared job info header (same for ALL tools)
    shared_info_header = _build_job_info_header(job)

    # This section is rendered for all tools, but will be empty if the job has
    # no params or if the tool uses _params_exclude to hide them.
    tool_input_params = build_result_input_params(job)

    # ------------------------------
    # Tool-specific content section —
    # rendered by the tool's results_layout function if defined,
    # otherwise default_results_layout.
    # ------------------------------
    tool_result_content = []

    if job.status in _ACTIVE:
        # Status banner with contextual message and cancel button.
        tool_result_content.append(
            html.Div(
                className="jobs-status-banner",
                children=[
                    # Status message with icon (e.g. clock for pending, gear for started)
                    html.Div(
                        className="jobs-status-banner-text",
                        children=[
                            html.I(
                                className=(
                                    f"{_STATUS_ICONS.get(job.status, ICON_STATUS_PENDING)} jobs-status-banner-icon"
                                ),
                            ),
                            # Status message based on the current job status
                            html.Span(_STATUS_MESSAGES.get(job.status, "Your task is in progress.")),
                        ],
                    ),
                    # Hint about auto-refreshing the page while the task is active.
                    html.Div(
                        "This page refreshes automatically.",
                        className="jobs-status-banner-hint",
                    ),
                ],
            ),
        )
        # Plumbing for auto-refresh callback.
        tool_result_content.append(html.Div(id="id-div-job-detail-refresh-sink", style={"display": "none"}))
        tool_result_content.append(
            dcc.Interval(
                id="id-interval-job-detail-poll",
                interval=5000,
                n_intervals=0,
            ),
        )

    elif job.status == JobStatus.SUCCESS:
        # For successful jobs, render the tool-specific results layout if available, otherwise show the raw JSON.
        tool_result_content.append(html.H4("Results", className="jobs-section-title"))
        # RESULTS_LAYOUTS maps tool_slug → results_layout function.
        # If the tool doesn't have a custom layout, use the default.
        tool_result_content.append((RESULTS_LAYOUTS.get(job.tool_slug, default_results_layout))(job))

    elif job.status == JobStatus.FAILURE:
        # For failed jobs, display error details if available.
        tool_result_content.append(html.Hr(className="jobs-divider"))
        tool_result_content.append(html.H5("Error Details"))
        if job.error:
            tool_result_content.append(html.Div(job.error, className="jobs-error-box"))
        else:
            tool_result_content.append(html.Div("No error details available.", className="jobs-error-box"))

    elif job.status == JobStatus.REVOKED:
        # For revoked jobs, show a cancellation message.
        tool_result_content.append(html.Hr(className="jobs-divider"))
        tool_result_content.append(html.H5("Cancelled"))
        tool_result_content.append(
            html.Div("This job was cancelled before completion.", className="jobs-error-box"),
        )

    elif job.status == JobStatus.TIMEOUT:
        # For timed-out jobs, show a timeout message.
        tool_result_content.append(html.Hr(className="jobs-divider"))
        tool_result_content.append(html.H5("Timed Out"))
        tool_result_content.append(
            html.Div(
                "This job exceeded its time limit and was terminated.",
                className="jobs-error-box",
            ),
        )

    # ------------------------------
    # Output Log
    # ------------------------------
    # If the job has an output log (available for some tools),
    # display it in a scrollable box.
    if job.output_log:
        tool_result_content.append(html.H5("Output Log", style={"marginTop": "2rem"}))
        tool_result_content.append(html.Div(job.output_log, className="jobs-log-box"))

    return html.Div(
        className="jobs-page",
        children=[
            shared_back_to_my_tasks_link,  # Back link at top for easy navigation.
            shared_info_header,  # Tool name, status, timestamps, duration, expiry.
            tool_input_params,  # Empty if job has no params or tool uses _params_exclude.
            *tool_result_content,  # Status banner / results / error details.
        ],
    )


# ---------------------------------------------------------------------------
# Auto-refresh: reload the browser every 5 s while the job is active.
# The dcc.Interval only exists in the DOM for active jobs, so once the
# page re-renders with a terminal status the interval (and this callback)
# disappear automatically.
# ---------------------------------------------------------------------------
dash.clientside_callback(
    "function(n) { if (n > 0) { window.location.reload(); } return ''; }",
    Output("id-div-job-detail-refresh-sink", "children"),
    Input("id-interval-job-detail-poll", "n_intervals"),
    prevent_initial_call=True,
)
