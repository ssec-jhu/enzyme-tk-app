"""Modal layout for the Timer tool — **canonical example** for new tool modals.

This modal appears when the user clicks the Launch button on the Timer tool card.
It collects the number of seconds the background task should sleep for.

Layout rules  (see ``.github/agents/create-modal.md``)
------------------------------------------------------
1. Top-level: ``dbc.Modal(size="lg", centered=True)``.
2. ``dbc.ModalBody`` gets ``className="p-4"``.
3. Each logical section is wrapped in
   ``html.Div(className="bg-light p-3 rounded mb-3")``.
4. Shared helpers from ``modal_helpers`` handle all repeated
   boilerplate — header, section headers, footer, and results
   placeholder.
5. Inputs use ``dbc.Row`` / ``dbc.Col`` for label ↔ control alignment.
6. All interactive controls get ``className="... themed-control"`` for
   dark-mode-aware styling.

Key conventions
---------------
- All component IDs are f-strings of ``TOOL_DEF["slug"]`` — never
  hardcode the slug string.
- The modal ID **must** be ``f"id-modal-{TOOL_DEF['slug']}"``.
- Use shared helpers for modal structure:
  - ``create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"])``
  - ``create_modal_input_section_header()``
  - ``create_modal_config_section_header()``
  - ``create_modal_submission_results(TOOL_DEF["slug"])``
  - ``create_modal_footer(TOOL_DEF["slug"])``
- Use ``dcc.Dropdown`` (not ``dbc.Select``) for dropdowns.
- Use ``themed-control`` on every form control (Input, Dropdown,
  RadioItems, Checkbox, Textarea).
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
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
            # ------------------------------------------------
            # MODAL Header: MUST ADD using the shared helper for consistent styling.
            # ------------------------------------------------
            create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),
            # ------------------------------------------------
            # MODAL BODY
            # ------------------------------------------------
            dbc.ModalBody(
                className="p-4",
                children=[
                    # ------------------------------------------------
                    # Section 1: Input Data
                    # ------------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-3",
                        children=[
                            # INPUT DATA HEADER:
                            # MUST ADD the section header using the shared helper
                            create_modal_input_section_header(),
                            # MODAL INPUTS GO HERE — this example has a number input
                            # and quick-select radios, but your tool may differ.
                            # The ID pattern for inputs is:
                            # id-<component-type>-<slug>-<name>
                            # where <component-type> is input, dropdown, radio, check, etc.
                            # and <name> is a descriptive name for the input's purpose.
                            # uses dbc.Row for label ↔ control alignment.
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
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            # CONFIGURATION HEADER:
                            # MUST ADD the section header using the shared helper
                            create_modal_config_section_header(),
                            # MODAL CONFIGURATION INPUTS GO HERE
                            # This example has a single simulate-failure toggle,
                            # but your tool may have different or additional config options.
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
                    # ------------------------------------------------
                    # Section 3: MUST ADD Status / job ID placeholder
                    # ------------------------------------------------
                    # This div is populated by the submit callback with
                    # a job-ID confirmation message or a validation error.
                    create_modal_submission_results(TOOL_DEF["slug"]),
                ],
            ),
            # ------------------------------------------------
            # Footer:  Cancel (outline) + Submit (primary) — standard for all modals.
            # ------------------------------------------------
            create_modal_footer(TOOL_DEF["slug"]),
        ],
    )
