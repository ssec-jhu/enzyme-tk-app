"""Modal layout for the Substrate/Product Similarity tool.

This modal appears when the user clicks the Launch button on the Substrate/Product
Similarity tool card. It collects inputs needed to run the molecular similarity search.

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
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
from enzyme_tk_app.app.tools.substrate_product_similarity import TOOL_DEF, get_similarity_algorithms
from enzyme_tk_app.app.utils.data_loading import get_reaction_database_options


def _get_example_smiles():
    """Return a list of example SMILES strings for substrates and products.

    Each example includes a human-readable label, the SMILES string, and
    the molecule role (substrate or product).
    """
    return [
        {
            "label": "Substrate: Glucose",
            "value": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "role": "substrate",
        },
        {
            "label": "Substrate: L-Alanine",
            "value": "C[C@@H](N)C(=O)O",
            "role": "substrate",
        },
        {
            "label": "Product: Pyruvate",
            "value": "CC(=O)C(=O)O",
            "role": "product",
        },
        {
            "label": "Product: Ethanol",
            "value": "CCO",
            "role": "product",
        },
    ]


def modal():
    """Build the Substrate/Product Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Task name
        - Database selection
        - Molecule role (substrate or product)
        - SMILES input
        - Example SMILES dropdown
    """
    db_options = get_reaction_database_options()
    example_smiles = _get_example_smiles()

    # Pre-select all databases by default
    all_db_values = [opt["value"] for opt in db_options]

    # Build algorithm options from the shared registry
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
                            # MODAL INPUTS GO HERE — this tool collects a task name,
                            # molecule role, and SMILES string with example picker.
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
                                            placeholder="e.g. 'Glucose substrate search'",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Molecule Role — radio buttons for substrate vs product
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Molecule Role", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.RadioItems(
                                            id=f"id-radio-{TOOL_DEF['slug']}-role",
                                            options=[
                                                {"label": "Substrate", "value": "substrate"},
                                                {"label": "Product", "value": "product"},
                                            ],
                                            value="substrate",
                                            inline=False,
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # SMILES Input — textarea with example picker dropdown
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("SMILES", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Textarea(
                                                id=f"id-textarea-{TOOL_DEF['slug']}-smiles",
                                                placeholder="e.g. CCO",
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
                                                            {
                                                                "label": ex["label"],
                                                                "value": f"{ex['role']}||{ex['value']}",
                                                            }
                                                            for ex in example_smiles
                                                        ],
                                                        placeholder="Select an example molecule...",
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
                                    dbc.Col(
                                        dbc.Label("Databases", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dcc.Dropdown(
                                                id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                                                options=db_options,
                                                value=all_db_values,
                                                multi=True,
                                                placeholder="Select one or more databases...",
                                                className="themed-control",
                                            ),
                                        ]
                                        + (
                                            [
                                                html.Small(
                                                    "No reaction databases found. "
                                                    "Check that CSV files exist in data/reactions/.",
                                                    className="text-danger mt-1 d-block",
                                                ),
                                            ]
                                            if not db_options
                                            else []
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
