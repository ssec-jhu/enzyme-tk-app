"""Modal layout for the Timer tool — **canonical example** for new tool modals.

This modal appears when the user clicks the Launch button on the Timer tool card.
It collects the number of seconds the background task should sleep for.

Layout rules  (see ``.github/agents/create-modal.md``)
------------------------------------------------------
1. Top-level: ``dbc.Modal(size="lg", centered=True)``.
2. ``dbc.ModalBody`` gets ``className="p-4"``.
3. Each logical section is wrapped in
   ``html.Div(className="bg-light p-3 rounded mb-3")``.
4. Section headers use ``html.H6`` with an icon, uppercase, bold, muted,
   and a bottom border.
5. Inputs use ``dbc.Row`` / ``dbc.Col`` for label ↔ control alignment.
6. All interactive controls get ``className="... themed-control"`` for
   dark-mode-aware styling.

Key conventions
---------------
- All component IDs are f-strings of ``TOOL_DEF["slug"]`` — never
  hardcode the slug string.
- The modal ID **must** be ``f"id-modal-{TOOL_DEF['slug']}"``.
- The modal title comes from ``TOOL_DEF["title"]``.
- Use ``dcc.Dropdown`` (not ``dbc.Select``) for dropdowns.
- Use ``themed-control`` on every form control (Input, Dropdown,
  RadioItems, Checkbox, Textarea).
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_SECTION_CONFIG, ICON_SECTION_INPUT
from enzyme_tk_app.app.tools.timer_tool_template import TOOL_DEF

# Pre-defined quick-select durations shown as radio options.
# These demonstrate how to offer convenient defaults in Section 1.
QUICK_DURATIONS = [
    {"label": "5 seconds", "value": 5},
    {"label": "15 seconds", "value": 15},
    {"label": "30 seconds", "value": 30},
    {"label": "60 seconds", "value": 60},
]


def modal():
    """Build the Timer modal component.

    Returns:
        A ``dbc.Modal`` component with two sections:

        **Section 1 — Input Data:** the duration input and quick-select
        radio buttons.

        **Section 2 — Timer Configuration:** the simulate-failure
        toggle and any optional tuning parameters.
    """
    return dbc.Modal(
        # Modal ID follows the convention: id-modal-<slug>
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            # ── Header ──────────────────────────────────────────────
            # Shows the tool icon and title from TOOL_DEF.
            dbc.ModalHeader(
                dbc.ModalTitle(
                    children=[
                        html.I(
                            className=TOOL_DEF["icon"],
                            style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                        ),
                        TOOL_DEF["title"],
                    ]
                ),
                close_button=True,
            ),
            # ── Body ────────────────────────────────────────────────
            # className="p-4" adds consistent internal padding.
            dbc.ModalBody(
                className="p-4",
                children=[
                    # ------------------------------------------------
                    # Section 1: Input Data
                    # ------------------------------------------------
                    # Use bg-light + rounded wrapper for visual grouping.
                    html.Div(
                        className="bg-light p-3 rounded mb-3",
                        children=[
                            # Section header: icon + uppercase title + bottom border
                            html.H6(
                                children=[
                                    html.I(
                                        className=ICON_SECTION_INPUT,
                                        style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                                    ),
                                    "Input Data",
                                ],
                                className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-3",
                            ),
                            # Duration Input — uses dbc.Row for label ↔ control alignment.
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Duration (seconds)", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            # ID pattern: id-<component-type>-<slug>-<name>
                                            id=f"id-input-{TOOL_DEF['slug']}-duration",
                                            type="number",
                                            min=1,
                                            max=300,
                                            step=1,
                                            value=5,
                                            placeholder="Enter duration in seconds (1–300)",
                                            # themed-control is required for dark-mode styling
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Quick-select radio buttons
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Quick select", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.RadioItems(
                                            id=f"id-radio-{TOOL_DEF['slug']}-quick",
                                            options=[
                                                {"label": d["label"], "value": d["value"]} for d in QUICK_DURATIONS
                                            ],
                                            value=5,
                                            inline=True,
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                        ],
                    ),
                    # ------------------------------------------------
                    # Section 2: Timer Configuration
                    # ------------------------------------------------
                    # Second section — optional tuning / advanced settings.
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            html.H6(
                                children=[
                                    html.I(
                                        className=ICON_SECTION_CONFIG,
                                        style={"marginRight": "0.5rem", "color": "var(--text-secondary)"},
                                    ),
                                    "Timer Configuration",
                                ],
                                className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-3",
                            ),
                            # Simulate failure toggle — demonstrates a boolean config option.
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Simulate Failure", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Checkbox(
                                            id=f"id-check-{TOOL_DEF['slug']}-fail",
                                            label="Throw exception halfway through (for testing)",
                                            value=False,
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                        ],
                    ),
                    # ── Status / job ID placeholder ────────────────
                    # This div is populated by the submit callback with
                    # a job-ID confirmation message or a validation error.
                    html.Div(id=f"id-div-{TOOL_DEF['slug']}-results"),
                ],
            ),
            # ── Footer ─────────────────────────────────────────────
            # Cancel (outline) + Submit (primary) — standard for all modals.
            dbc.ModalFooter(
                children=[
                    dbc.Button(
                        "Close",
                        id=f"id-btn-{TOOL_DEF['slug']}-cancel",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Start Timer",
                        id=f"id-btn-{TOOL_DEF['slug']}-submit",
                        color="primary",
                    ),
                ],
            ),
        ],
    )
