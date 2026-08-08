"""Modal layout for the Timer tool — **canonical example** for new tool modals.

This modal appears when the user clicks the Launch button on the Timer tool
card. It collects a task name and the number of seconds the background task
should sleep for.

Layout rules  (see the create-modal subagent)
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
  - ``create_modal_databases_label(TOOL_DEF["slug"], contents)``
  - ``create_modal_submission_results(TOOL_DEF["slug"])``
  - ``create_modal_footer(TOOL_DEF["slug"])``
- Use ``dcc.Dropdown`` (not ``dbc.Select``) for dropdowns.
- Use ``themed-control`` on every form control (Input, Dropdown,
  RadioItems, Checkbox, Textarea).

This tool has no databases, so it is the one helper above it does not call.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
from enzyme_tk_app.app.tools.timer_tool_template import TOOL_DEF


def _get_example_durations():
    """Return the example durations offered by the modal's example picker.

    Every tool ships a list like this — one dict per example, with a
    human-readable ``label``, the ``value`` that lands in the input, and a
    ``task_name``.  The ``task_name`` is prefilled into the Task Name field
    verbatim (see ``callbacks.populate_example_duration``) — no tool prefix,
    because the My Tasks table already has a Tool column beside Task Name.
    Keep it short: it shares that column with names the user types.
    """
    return [
        {"label": "5 seconds", "value": 5, "task_name": "5-seconds"},
        {"label": "15 seconds", "value": 15, "task_name": "15-seconds"},
        {"label": "30 seconds", "value": 30, "task_name": "30-seconds"},
        {"label": "60 seconds", "value": 60, "task_name": "60-seconds"},
    ]


def modal():
    """Build the Timer modal component.

    Returns:
        A ``dbc.Modal`` component with two sections:

        **Section 1 — Input Data:** the task name, the duration input and
        the example picker.

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
                            # MODAL INPUTS GO HERE — this example has a task name and
                            # a number input, but your tool may differ.
                            # The ID pattern for inputs is:
                            # id-<component-type>-<slug>-<name>
                            # where <component-type> is input, dropdown, radio, check, etc.
                            # and <name> is a descriptive name for the input's purpose.
                            # uses dbc.Row for label ↔ control alignment.
                            #
                            # TASK NAME: MUST BE THE FIRST ROW of Section 1 in every
                            # tool.  It is required — validate_timer_form disables the
                            # Run button until it is filled — and it labels the job in
                            # the My Tasks table and on the results page.
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Task Name", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            id=f"id-input-{TOOL_DEF['slug']}-task-name",
                                            type="text",
                                            placeholder="e.g. 'Backend smoke test'",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Duration (seconds)", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
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
                                            # EXAMPLE PICKER: nested under the input it fills.
                                            # Selecting an example fills that input *and* the
                                            # Task Name, so a demo run is one click away.
                                            html.Div(
                                                className="mt-1",
                                                children=[
                                                    html.Small(
                                                        children=[
                                                            html.I(
                                                                className=ICON_MODAL_EXAMPLE,
                                                                style={
                                                                    "marginRight": "0.25rem",
                                                                    "color": "var(--accent-color)",
                                                                },
                                                            ),
                                                            "Try an example:",
                                                        ],
                                                        style={"color": "var(--text-tertiary)"},
                                                    ),
                                                    dcc.Dropdown(
                                                        id=f"id-dropdown-{TOOL_DEF['slug']}-example",
                                                        options=[
                                                            {"label": ex["label"], "value": ex["value"]}
                                                            for ex in _get_example_durations()
                                                        ],
                                                        placeholder="Select an example duration...",
                                                        className="mt-1 themed-control",
                                                        searchable=False,
                                                    ),
                                                ],
                                            ),
                                        ],
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
