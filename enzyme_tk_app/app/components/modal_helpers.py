"""Shared UI helpers for tool modal layouts.

Provides factory functions for the standardized header, section headers,
results placeholder, and footer used across all tool modals.  Every
modal should use these helpers instead of inlining the boilerplate —
this guarantees consistent styling and makes future design changes a
single-file edit.

Usage::

    from enzyme_tk_app.app.components.modal_helpers import (
        create_modal_config_section_header,
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
from dash import html

from enzyme_tk_app.app.components.icons import ICON_SECTION_CONFIG, ICON_SECTION_INPUT


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


def create_modal_footer(slug):
    """Return the standard modal footer with Close and Run buttons.

    Args:
        slug: The tool slug from ``TOOL_DEF["slug"]``, used to build
            the button component IDs.

    Returns:
        A ``dbc.ModalFooter`` with a secondary outline Close button and
        a primary Run button.
    """
    return dbc.ModalFooter(
        children=[
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
