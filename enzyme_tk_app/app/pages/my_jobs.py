"""My Tasks page — lists all tasks submitted by the current session.

Displays a stats summary, toolbar with bulk actions, and a table of tasks
with per-row cancel and view-results buttons.  Auto-polls every 5 seconds
to refresh running task statuses.
"""

import dash
from dash import dcc, html

from enzyme_tk_app.app.components.icons import (
    ICON_JOB_CANCEL_ALL,
    ICON_JOB_CLEAR,
    ICON_JOB_REFRESH,
    ICON_JOBS_PAGE,
)

dash.register_page(__name__, path="/my-tasks")


# --- Layout ----------------------------------------------------------------


def layout() -> html.Div:
    """Return the My Tasks page layout.

    The stats summary and tasks table are populated by callbacks
    in ``my_jobs_callbacks.py``.

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
                    html.Button(
                        id="id-btn-jobs-refresh",
                        className="btn-toolbar",
                        children=[
                            html.I(className=ICON_JOB_REFRESH),
                            "Refresh",
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


# Import callbacks for side effect registration (Dash @callback decorators).
# from enzyme_tk_app.app.pages import my_jobs_callbacks  # noqa: E402, F401
