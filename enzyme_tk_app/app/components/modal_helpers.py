"""Shared UI helpers for tool modal layouts.

Provides factory functions for the standardized header, section headers,
databases label, results placeholder, and footer used across all tool
modals.  Every modal should use these helpers instead of inlining the
boilerplate — this guarantees consistent styling and makes future design
changes a single-file edit.

Usage::

    from enzyme_tk_app.app.components.modal_helpers import (
        build_submission_success,
        create_modal_config_section_header,
        create_modal_databases_label,
        create_modal_footer,
        create_modal_header,
        create_modal_input_section_header,
        create_modal_submission_results,
    )

    # Modal children list:
    children=[
        create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),
        dbc.ModalBody(
            className="p-4",
            children=[
                html.Div(
                    className="bg-light p-3 rounded mb-3",
                    children=[
                        create_modal_input_section_header(),
                        # ... form rows ...
                    ],
                ),
                create_modal_submission_results(TOOL_DEF["slug"]),
            ],
        ),
        create_modal_footer(TOOL_DEF["slug"]),
    ]
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import (
    ICON_MODAL_INFO,
    ICON_SECTION_CONFIG,
    ICON_SECTION_INPUT,
    ICON_STATUS_SUCCESS,
    ICON_SUBMISSION_TRACK,
)
from enzyme_tk_app.app.utils import captcha
from enzyme_tk_app.app.utils.formatting import truncate_id

# Contract with assets/12-altcha-bridge.js, which finds holders by this class and derives the
# Store id from the holder id.  Renaming either means editing that file in the same change —
# the same page-to-JS contract as results_helpers.QUERY_PREVIEW_CLASS.
CAPTCHA_HOLDER_CLASS = "etk-captcha"


def create_modal_header(icon, title):
    """Return the standard modal header with tool icon and title.

    Args:
        icon: The FontAwesome icon class string (e.g. from
            ``TOOL_DEF["icon"]``).
        title: The display title string (e.g. from
            ``TOOL_DEF["title"]``).

    Returns:
        A ``dbc.ModalHeader`` with a ``dbc.ModalTitle`` showing the
        tool icon and title, plus a close button.
    """
    return dbc.ModalHeader(
        dbc.ModalTitle(
            children=[
                html.I(
                    className=icon,
                    style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                ),
                title,
            ]
        ),
        close_button=True,
    )


def create_modal_input_section_header():
    """Return the standard *Input Data* section header for tool modals.

    Returns:
        An ``html.H6`` component with the flask icon, uppercase title
        "Input Data", and a bottom border.
    """
    return html.H6(
        children=[
            html.I(
                className=ICON_SECTION_INPUT,
                style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
            ),
            "Input Data",
        ],
        className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-2",
    )


def create_modal_config_section_header():
    """Return the standard *Tool Configurations* section header for tool modals.

    Returns:
        An ``html.H6`` component with the gear icon, uppercase title
        "Tool Configurations", and a bottom border.
    """
    return html.H6(
        children=[
            html.I(
                className=ICON_SECTION_CONFIG,
                style={"marginRight": "0.5rem", "color": "var(--text-secondary)"},
            ),
            "Tool Configurations",
        ],
        className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-2",
    )


def create_modal_databases_label(slug, contents):
    """Return the *Databases* label column with an info icon and content tooltip.

    Args:
        slug: The tool slug from ``TOOL_DEF["slug"]``, used to build the
            tooltip target id.
        contents: One sentence naming what this tool's databases hold
            (e.g. "Entry, Sequence and EC number columns, plus any
            metadata the file carries.").

    Returns:
        A ``dbc.Col(width=3)`` holding the label, the info icon, and the
        ``dbc.Tooltip`` bound to it.  No callback is needed — the tooltip's
        default trigger is "hover focus".
    """
    icon_id = f"id-icon-{slug}-databases-info"
    return dbc.Col(
        children=[
            dbc.Label("Databases", className="col-form-label fw-bold"),
            html.I(
                id=icon_id,
                className=f"{ICON_MODAL_INFO} field-info-icon",
                # tabIndex makes the icon focusable so the tooltip's default
                # "hover focus" trigger reaches keyboard users too.
                tabIndex="0",
            ),
            dbc.Tooltip(contents, target=icon_id, placement="top"),
        ],
        width=3,
    )


def create_modal_footer(slug):
    """Return the standard modal footer with Close and Run buttons.

    Args:
        slug: The tool slug from ``TOOL_DEF["slug"]``, used to build
            the button component IDs.

    Returns:
        A ``dbc.ModalFooter`` with the captcha holder and payload Store, a
        secondary outline Close button, and a primary Run button.
    """
    return dbc.ModalFooter(
        children=[
            # Empty on purpose: assets/12-altcha-bridge.js creates <altcha-widget> in here.
            # A custom element is not something Dash's html namespace can emit, and dbc.Modal
            # unmounts its children on close, so mounting is a per-open job either way.
            # Rendered only in production — a local checkout shows no widget and app.py
            # registers no challenge route.
            *(
                [html.Div(id=f"id-div-{slug}-captcha", className=CAPTCHA_HOLDER_CLASS)]
                if captcha.PRODUCTION_MODE
                else []
            ),
            # Rendered ALWAYS, even locally: a State pointing at a component that is not in the
            # layout stops the submit callback from firing at all, which would dead-button Run
            # for everyone running the app locally.
            dcc.Store(id=f"id-store-{slug}-captcha"),
            dbc.Button(
                "Close",
                id=f"id-btn-{slug}-cancel",
                color="secondary",
                outline=True,
                className="me-2",
            ),
            dbc.Button(
                "Run",
                id=f"id-btn-{slug}-submit",
                color="primary",
            ),
        ],
    )


def create_modal_submission_results(slug):
    """Return the job-ID / status placeholder div.

    This is populated by the submit callback in callbacks.py of the tool
    with a job-ID confirmation message or a validation error.

    The two are told apart by *type*, and ``07-modals.css`` styles them
    differently off that distinction: a **bare string** here is a validation
    error (red), while every success path returns
    :func:`build_submission_success` (green, with the My Tasks link).  A
    success message returned as a plain string would render as an error.

    Args:
        slug: The tool slug from ``TOOL_DEF["slug"]``.

    Returns:
        An ``html.Div`` with ``id=f"id-div-{slug}-results"``.
    """
    return html.Div(id=f"id-div-{slug}-results", className="modal-submission-results")


def build_submission_success(job_id, detail):
    """Return the post-submit success row: job ID, terse detail, My Tasks link.

    The link is the only thing on screen telling a first-time user their job is
    now tracked somewhere.  The modal deliberately stays open after Run, so
    submitting another job needs no affordance of its own — this only has to
    signpost the page that follows the one already running.

    **One line, deliberately.**  Every tool modal already overruns a laptop
    viewport, so this row is kept to a single line: the job id goes through the
    shared :func:`~enzyme_tk_app.app.utils.formatting.truncate_id` with the full
    value in its tooltip (the full uuid measures 416 px and wraps, which used to
    cost a whole extra line), and ``detail`` is a terse fragment rather than a
    sentence.  Measured budget is ~720 px of block width on a 1366 px laptop.

    Args:
        job_id: The id returned by ``TaskScheduler.submit_job()``.  Shown
            truncated; the full value goes in the tooltip.
        detail: A terse fragment naming what was submitted, e.g.
            ``"2 database(s) · top 10"`` — not a sentence, and short enough to
            share one line with the id and the link.

    Returns:
        An ``html.Div`` with ``className="modal-submission-success"``.
    """
    return html.Div(
        className="modal-submission-success",
        children=[
            html.I(className=ICON_STATUS_SUCCESS),
            # truncate_id, not a local slice: the My Tasks Task ID column and /admin use the
            # same helper, so the modal and the page its link leads to show the same string.
            html.Span(
                f"Job submitted — {truncate_id(job_id)}",
                title=job_id,
                className="modal-submission-success-id",
            ),
            html.Span(f"· {detail}", className="modal-submission-success-detail"),
            # html.A, not dcc.Link: every other /my-tasks link in the app is a plain anchor
            # (navbar.make_nav_link, my_tasks_view_results._build_back_link), and a full load
            # leaves no open modal mounted on the page being navigated away from.
            html.A(
                className="modal-submission-success-link",
                href="/my-tasks",
                children=[
                    "Track progress",
                    html.I(className=f"{ICON_SUBMISSION_TRACK} modal-submission-success-arrow"),
                ],
            ),
        ],
    )
