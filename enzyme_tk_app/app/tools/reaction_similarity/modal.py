"""Modal layout for the Reaction Similarity tool.

This modal appears when the user clicks the Launch button on the Reaction Similarity
tool card. It collects inputs needed to run the reaction similarity search.
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE, ICON_TOOL_REACTION
from enzyme_tk_app.app.utils import get_reaction_database_options


def _get_example_reactions():
    """Return a list of example reaction SMILES from the enzymemap database.

    These are simplified, shorter examples suitable for demonstration.
    """
    return [
        {
            "label": "Hydrolysis: Lactone ring opening",
            "value": "CCCC(=O)N[C@H]1CCOC1=O.O>>CCCC(=O)N[C@@H](CCO)C(=O)O",
        },
        {
            "label": "Phosphate transfer",
            "value": "O=P(O)(O)OCC1OC(O)C(O)C(O)C1O.O>>O=P(O)(O)O.OCC1OC(O)C(O)C(O)C1O",
        },
        {
            "label": "Glutathione conjugation",
            "value": (
                "N[C@@H](CCC(=O)N[C@@H](CS)C(=O)NCC(=O)O)C(=O)O."
                "O=[N+]([O-])c1ccc(Cl)c([N+](=O)[O-])c1>>"
                "Cl.N[C@@H](CCC(=O)N[C@@H](CSc1ccc([N+](=O)[O-])cc1[N+](=O)[O-])C(=O)NCC(=O)O)C(=O)O"
            ),
        },
    ]


def Modal():
    """Build the Reaction Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Query name
        - Database selection
        - Reaction SMILES input
        - Example reactions dropdown
    """
    db_options = get_reaction_database_options()
    example_reactions = _get_example_reactions()

    # Default database selection (enzymemap if available)
    default_db = None
    for opt in db_options:
        if "enzymemap" in opt["value"].lower():
            default_db = opt["value"]
            break
    if not default_db and db_options:
        default_db = db_options[0]["value"]

    return dbc.Modal(
        id="id-modal-reaction-similarity",
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
                        "Reaction Similarity Search",
                    ]
                ),
                close_button=True,
            ),
            dbc.ModalBody(
                children=[
                    # Query Name Input
                    dbc.Label("Query Name", html_for="id-input-reaction-query-name", className="form-label"),
                    dbc.Input(
                        id="id-input-reaction-query-name",
                        type="text",
                        placeholder="Enter a name for this query (e.g., 'Hydrolysis search')",
                        className="mb-3",
                    ),
                    # Database Selection
                    dbc.Label("Select Database", html_for="id-select-reaction-database", className="form-label"),
                    dbc.Select(
                        id="id-select-reaction-database",
                        options=db_options,
                        value=default_db,
                        className="mb-3",
                    ),
                    # Reaction SMILES Input
                    dbc.Label("Reaction SMILES", html_for="id-textarea-reaction-smiles", className="form-label"),
                    dbc.Textarea(
                        id="id-textarea-reaction-smiles",
                        placeholder="Enter reaction SMILES (e.g., CC(=O)O.CCO>>CC(=O)OCC.O)",
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
                                id="id-select-reaction-example",
                                options=[{"label": ex["label"], "value": ex["value"]} for ex in example_reactions],
                                placeholder="Select an example reaction...",
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
                        id="id-btn-reaction-cancel",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Run Search",
                        id="id-btn-reaction-submit",
                        color="primary",
                    ),
                ],
            ),
        ],
    )
