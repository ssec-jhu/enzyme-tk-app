"""Shared UI helpers for tool modal layouts.

Provides factory functions for the standardized header, section headers,
databases label, results placeholder, and footer used across all tool
modals.  Every modal should use these helpers instead of inlining the
boilerplate — this guarantees consistent styling and makes future design
changes a single-file edit.

Usage::

    from enzyme_tk_app.app.components.modal_helpers import (
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

from enzyme_tk_app.app.components.icons import ICON_MODAL_INFO, ICON_SECTION_CONFIG, ICON_SECTION_INPUT
from enzyme_tk_app.app.utils import captcha

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
    Args:
        slug: The tool slug from ``TOOL_DEF["slug"]``.

    Returns:
        An ``html.Div`` with ``id=f"id-div-{slug}-results"``.
    """
    return html.Div(id=f"id-div-{slug}-results", className="modal-submission-results")
