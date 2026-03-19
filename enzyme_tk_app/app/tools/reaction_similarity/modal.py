"""Modal layout for the Reaction Similarity tool.

This modal appears when the user clicks the Launch button on the Reaction Similarity
tool card. It collects inputs needed to run the reaction similarity search.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_DATABASE, ICON_MODAL_EXAMPLE
from enzyme_tk_app.app.tools.reaction_similarity import TOOL_DEF, get_similarity_algorithms
from enzyme_tk_app.app.utils.data_loading import get_reaction_database_options


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


def modal():
    """Build the Reaction Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Query name
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
                    # --------------------------------
                    # Query Name Input
                    # --------------------------------
                    dbc.Label("Query Name", className="form-label"),
                    dbc.Input(
                        id="id-input-reaction-query-name",
                        type="text",
                        placeholder="Enter a name for this query (e.g., 'Hydrolysis search')",
                        className="mb-3 themed-control",
                    ),
                    # --------------------------------------------
                    # Database Selection (multi-select dropdown)
                    # --------------------------------------------
                    dbc.Label(
                        children=[
                            html.I(
                                className=ICON_MODAL_DATABASE,
                                style={"marginRight": "0.4rem", "color": "var(--primary-color)"},
                            ),
                            "Select Databases",
                        ],
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
                    # --------------------------------------------
                    # Similarity Algorithm Selection (multi-select)
                    # --------------------------------------------
                    dbc.Label("Similarity Algorithms", className="form-label"),
                    dcc.Dropdown(
                        id=f"id-dropdown-{TOOL_DEF['slug']}-algorithms",
                        options=algo_dropdown_options,
                        value=all_algo_values,
                        multi=True,
                        placeholder="Select one or more algorithms...",
                        className="mb-3 themed-control",
                    ),
                    # --------------------------------------------
                    # Reaction SMILES Input
                    # --------------------------------------------
                    dbc.Label("Reaction SMILES", className="form-label"),
                    dbc.Textarea(
                        id="id-textarea-reaction-smiles",
                        placeholder="Enter reaction SMILES (e.g., CC(=O)O.CCO>>CC(=O)OCC.O)",
                        rows=3,
                        className="mb-2 themed-control",
                        style={"fontFamily": "monospace", "fontSize": "0.9rem"},
                    ),
                    # --------------------------------------------
                    # Try an Example section
                    # --------------------------------------------
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
                                options=[{"label": ex["label"], "value": ex["value"]} for ex in example_reactions],
                                placeholder="Select an example reaction...",
                                className="mt-1 themed-control",
                                searchable=False,
                            ),
                        ],
                    ),
                    # --------------------------------------------
                    # Top-N Results
                    # --------------------------------------------
                    dbc.Label("Top N Results", className="form-label"),
                    dbc.Input(
                        id=f"id-input-{TOOL_DEF['slug']}-top-n",
                        type="number",
                        value=10,
                        min=1,
                        max=500,
                        step=1,
                        placeholder="Number of top results to return",
                        className="mb-3 themed-control",
                    ),
                    # --------------------------------------------
                    html.Div(id=f"id-div-{TOOL_DEF['slug']}-results"),
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
