"""Modal layout for the Reaction Similarity tool.

This modal appears when the user clicks the Launch button on the Reaction Similarity
tool card. It collects inputs needed to run the reaction similarity search.

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
from enzyme_tk_app.app.tools.reaction_similarity import TOOL_DEF, get_similarity_algorithms
from enzyme_tk_app.app.utils.data_loading import get_reaction_database_options


def _get_example_reactions():
    """Return a list of example reaction SMILES from the enzymemap database.

    These are simplified, shorter examples suitable for demonstration.  The
    ``task_name`` is the name the example picker prefills into the Task Name
    field (see ``callbacks.populate_example_reaction``).
    """
    return [
        {
            "label": "Hydrolysis: Lactone ring opening",
            "value": "CCCC(=O)N[C@H]1CCOC1=O.O>>CCCC(=O)N[C@@H](CCO)C(=O)O",
            "task_name": "lactone-hydrolysis",
        },
        {
            "label": "Phosphate transfer",
            "value": "O=P(O)(O)OCC1OC(O)C(O)C(O)C1O.O>>O=P(O)(O)O.OCC1OC(O)C(O)C(O)C1O",
            "task_name": "phosphate-transfer",
        },
        {
            "label": "Glutathione conjugation",
            "task_name": "glutathione-conjugation",
            "value": (
                "N[C@@H](CCC(=O)N[C@@H](CS)C(=O)NCC(=O)O)C(=O)O."
                "O=[N+]([O-])c1ccc(Cl)c([N+](=O)[O-])c1>>"
                "Cl.N[C@@H](CCC(=O)N[C@@H](CSc1ccc([N+](=O)[O-])cc1[N+](=O)[O-])C(=O)NCC(=O)O)C(=O)O"
            ),
        },
    ]


def modal():
    """Build the Reaction Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Task name
        - Database selection
        - Reaction SMILES input
        - Example reactions dropdown
        - Similarity algorithm selection
        - Top-N results limit
    """
    db_options = get_reaction_database_options()
    example_reactions = _get_example_reactions()

    # Pre-select all databases by default
    all_db_values = [opt["value"] for opt in db_options]

    # Build algorithm options from the single-source registry
    algo_options = get_similarity_algorithms()
    algo_dropdown_options = [{"label": a["label"], "value": a["value"]} for a in algo_options]
    all_algo_values = [a["value"] for a in algo_options]

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
                            # and reaction SMILES string with example picker.
                            # The ID pattern for inputs is:
                            # id-<component-type>-<slug>-<name>
                            # where <component-type> is input, dropdown, radio, check, etc.
                            # and <name> is a descriptive name for the input's purpose.
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
                                            placeholder="e.g. 'Hydrolysis search'",
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
                                                placeholder="e.g. CC(=O)O.CCO>>CC(=O)OCC.O",
                                                rows=3,
                                                className="themed-control",
                                                style={"fontFamily": "monospace", "fontSize": "0.9rem"},
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
                                                            for ex in example_reactions
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
                    # Section 2: Search Configuration
                    # ------------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            # CONFIGURATION HEADER:
                            # MUST ADD the section header using the shared helper
                            create_modal_config_section_header(),
                            # MODAL CONFIGURATION INPUTS GO HERE
                            # This tool has database selection, algorithm selection,
                            # and top-N results limit.
                            # Database Selection
                            dbc.Row(
                                [
                                    create_modal_databases_label(
                                        TOOL_DEF["slug"],
                                        "Reaction SMILES (substrates>>products) with a reaction id.",
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                                            options=db_options,
                                            value=all_db_values,
                                            multi=True,
                                            placeholder="Select one or more databases...",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Similarity Algorithm Selection
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Algorithms", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-algorithms",
                                            options=algo_dropdown_options,
                                            value=all_algo_values,
                                            multi=True,
                                            placeholder="Select one or more algorithms...",
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
