"""Modal layout for the Substrate/Product Similarity tool.

This modal appears when the user clicks the Launch button on the Substrate/Product
Similarity tool card. It collects inputs needed to run the molecular similarity search.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE
from enzyme_tk_app.app.tools.reaction_similarity import get_similarity_algorithms
from enzyme_tk_app.app.tools.substrate_product_similarity import TOOL_DEF
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
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
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
            dbc.ModalBody(
                className="p-4",
                children=[
                    # --------------------------------------------
                    # Section 1: Input Data
                    # --------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-3",
                        children=[
                            html.H6(
                                children=[
                                    html.I(
                                        className="fas fa-flask",
                                        style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                                    ),
                                    "Input Data",
                                ],
                                className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-2",
                            ),
                            # Task Name
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Task Name", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            id="id-input-subprod-task-name",
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
                            # Molecule Role
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Molecule Role", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.RadioItems(
                                            id="id-radio-subprod-role",
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
                            # SMILES Input
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("SMILES", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Textarea(
                                                id="id-textarea-subprod-smiles",
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
                    # --------------------------------------------
                    # Section 2: Search Configuration
                    # --------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            html.H6(
                                children=[
                                    html.I(
                                        className="fas fa-cog",
                                        style={"marginRight": "0.5rem", "color": "var(--text-secondary)"},
                                    ),
                                    "Search Configuration",
                                ],
                                className="text-uppercase fw-bold text-muted border-bottom pb-2 mb-2",
                            ),
                            # Database Selection
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Databases", className="col-form-label fw-bold"),
                                        width=3,
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
                ],
            ),
            dbc.ModalFooter(
                children=[
                    dbc.Button(
                        "Cancel",
                        id="id-btn-subprod-cancel",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Run Search",
                        id="id-btn-subprod-submit",
                        color="primary",
                    ),
                ],
            ),
        ],
    )
