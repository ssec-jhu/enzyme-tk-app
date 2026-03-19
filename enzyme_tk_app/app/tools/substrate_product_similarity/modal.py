"""Modal layout for the Substrate/Product Similarity tool.

This modal appears when the user clicks the Launch button on the Substrate/Product
Similarity tool card. It collects inputs needed to run the molecular similarity search.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE
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
        - Query name
        - Database selection
        - Molecule role (substrate or product)
        - SMILES input
        - Example SMILES dropdown
    """
    db_options = get_reaction_database_options()
    example_smiles = _get_example_smiles()

    # Pre-select all databases by default
    all_db_values = [opt["value"] for opt in db_options]

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
                children=[
                    # Query Name Input
                    dbc.Label(
                        "Query Name",
                        className="form-label",
                    ),
                    dbc.Input(
                        id="id-input-subprod-query-name",
                        type="text",
                        placeholder="Enter a name for this query (e.g., 'Glucose substrate search')",
                        className="mb-3 themed-control",
                    ),
                    # Database Selection (multi-select dropdown)
                    dbc.Label(
                        "Select Databases",
                        className="form-label",
                    ),
                    dcc.Dropdown(
                        id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                        options=db_options,
                        value=all_db_values,
                        multi=True,
                        placeholder="Select one or more databases...",
                        className="mb-3 themed-control",
                    ),
                    # Molecule Role Selection (substrate or product)
                    dbc.Label(
                        "Molecule Role",
                        className="form-label",
                    ),
                    dbc.RadioItems(
                        id="id-radio-subprod-role",
                        options=[
                            {"label": "Substrate", "value": "substrate"},
                            {"label": "Product", "value": "product"},
                        ],
                        value="substrate",
                        inline=True,
                        className="mb-3 themed-control",
                    ),
                    # SMILES Input
                    dbc.Label(
                        "SMILES",
                        className="form-label",
                    ),
                    dbc.Textarea(
                        id="id-textarea-subprod-smiles",
                        placeholder="Enter a SMILES string (e.g., CCO)",
                        rows=3,
                        className="mb-2 themed-control",
                        style={"fontFamily": "monospace", "fontSize": "0.9rem"},
                    ),
                    # Try an Example section
                    html.Div(
                        className="mt-2 mb-3",
                        children=[
                            html.Small(
                                children=[
                                    html.I(
                                        className=ICON_MODAL_EXAMPLE,
                                        style={"marginRight": "0.25rem", "color": "var(--accent-color)"},
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
                                        # Encode both SMILES and role so the callback can set both
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
