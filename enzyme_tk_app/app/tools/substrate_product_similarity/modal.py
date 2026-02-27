"""Modal layout for the Substrate/Product Similarity tool.

This modal appears when the user clicks the Launch button on the Substrate/Product
Similarity tool card. It collects inputs needed to run the molecular similarity search.
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE, ICON_TOOL_REACTION
from enzyme_tk_app.app.utils import get_reaction_database_options


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


def Modal():
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

    # Default database selection (enzymemap if available)
    default_db = None
    for opt in db_options:
        if "enzymemap" in opt["value"].lower():
            default_db = opt["value"]
            break
    if not default_db and db_options:
        default_db = db_options[0]["value"]

    return dbc.Modal(
        id="id-modal-substrate-product-similarity",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle(
                    children=[
                        html.I(
                            className=ICON_TOOL_REACTION,
                            style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                        ),
                        "Substrate/Product Similarity Search",
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
                        className="mb-3",
                    ),
                    # Database Selection
                    dbc.Label(
                        "Select Database",
                        className="form-label",
                    ),
                    dbc.Select(
                        id="id-select-subprod-database",
                        options=db_options,
                        value=default_db,
                        className="mb-3",
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
                        className="mb-3",
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
                        className="mb-2",
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
                            dbc.Select(
                                id="id-select-subprod-example",
                                options=[
                                    {
                                        "label": ex["label"],
                                        # Encode both SMILES and role so the callback can set both
                                        "value": f"{ex['role']}||{ex['value']}",
                                    }
                                    for ex in example_smiles
                                ],
                                placeholder="Select an example molecule...",
                                className="mt-1",
                                style={"fontSize": "0.9rem"},
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
