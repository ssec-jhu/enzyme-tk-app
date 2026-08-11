"""Modal layout for the Func-E Activity Prediction tool.

This modal appears when the user clicks the Launch button on the Func-E tool
card. It collects a reaction SMILES plus the pre-encoded protein database to
score it against.

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
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_databases_label,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
from enzyme_tk_app.app.tools.funce import EXAMPLE_REACTIONS, TOOL_DEF
from enzyme_tk_app.app.utils.data_loading import get_sequence_embedding_database_options


def modal():
    """Build the Func-E Activity Prediction modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Task name
        - Reaction SMILES input
        - Example reactions dropdown
        - Pre-encoded protein database selection
        - Top-N results limit
    """
    db_options = get_sequence_embedding_database_options()

    # Preselect every database — hits from all of them are merged and ranked
    # together, so the default is the broadest search.
    all_db_values = [opt["value"] for opt in db_options]

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
                            # MODAL INPUTS GO HERE — this tool collects a task name
                            # and the reaction SMILES to score, with an example picker.
                            # The ID pattern for inputs is:
                            # id-<component-type>-<slug>-<name>
                            # Task Name
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
                                            placeholder="e.g. 'DEHP degraders'",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Reaction SMILES
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Reaction SMILES", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Textarea(
                                                id=f"id-textarea-{TOOL_DEF['slug']}-smiles",
                                                # One molecule per side.  The dot-joined
                                                # "CC(=O)O.CCO" this used to show is the one
                                                # shape that fails silently here: UniMol embeds
                                                # a whole side as a single structure, so the
                                                # released alcohol is better left out entirely
                                                # (see EXAMPLE_REACTIONS in __init__.py).
                                                placeholder="e.g. CC(=O)OCC>>CC(=O)O",
                                                rows=3,
                                                className="themed-control",
                                                style={"fontFamily": "monospace", "fontSize": "0.9rem"},
                                                # Milliseconds, not True.  Validating every keystroke
                                                # puts several round-trips in flight at once and the
                                                # field ends up showing whichever verdict landed last
                                                # — reproducibly, an earlier keystroke's.  True would
                                                # defer to blur and strand Run disabled under a click.
                                                debounce=300,
                                            ),
                                            # Why the reaction was rejected.  Bootstrap reveals it via
                                            # `.is-invalid ~ .invalid-feedback`, so it must stay a
                                            # sibling *after* the textarea; validate_funce_form
                                            # fills it and flips the textarea's `invalid`.
                                            dbc.FormFeedback(
                                                id=f"id-feedback-{TOOL_DEF['slug']}-smiles",
                                                type="invalid",
                                            ),
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
                                                            for ex in EXAMPLE_REACTIONS
                                                        ],
                                                        placeholder="Select an example reaction...",
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
                            ),
                        ],
                    ),
                    # ------------------------------------------------
                    # Section 2: Tool Configuration
                    # ------------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            # CONFIGURATION HEADER:
                            # MUST ADD the section header using the shared helper
                            create_modal_config_section_header(),
                            # MODAL CONFIGURATION INPUTS GO HERE
                            # This tool has database selection and a top-N results limit.
                            # Database Selection
                            dbc.Row(
                                [
                                    create_modal_databases_label(
                                        TOOL_DEF["slug"],
                                        "Entry and Sequence columns with pre-computed embeddings.",
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                                            options=db_options,
                                            value=all_db_values,
                                            multi=True,
                                            placeholder="Select one or more pre-encoded databases...",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Top-N Results
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Top N Results", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            id=f"id-input-{TOOL_DEF['slug']}-top-n",
                                            type="number",
                                            value=10,
                                            min=1,
                                            max=500,
                                            step=1,
                                            placeholder="Number of top results",
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
