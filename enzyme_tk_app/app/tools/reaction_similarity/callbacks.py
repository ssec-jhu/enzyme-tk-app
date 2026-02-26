"""Callbacks for the Reaction Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input from example selection
- Handle the form submission (TODO)
"""

from dash import Input, Output, State, callback


@callback(
    Output("id-modal-reaction-similarity", "is_open"),
    [
        Input("id-btn-launch-reaction-similarity", "n_clicks"),
        Input("id-btn-reaction-cancel", "n_clicks"),
        Input("id-btn-reaction-submit", "n_clicks"),
    ],
    State("id-modal-reaction-similarity", "is_open"),
    prevent_initial_call=True,
)
def toggle_reaction_similarity_modal(launch_clicks, cancel_clicks, submit_clicks, is_open):
    """Toggle the Reaction Similarity modal open/closed.

    Args:
        launch_clicks: Number of clicks on the launch button.
        cancel_clicks: Number of clicks on the cancel button.
        submit_clicks: Number of clicks on the submit button.
        is_open: Current open state of the modal.

    Returns:
        Boolean indicating whether the modal should be open.
    """
    return not is_open


@callback(
    Output("id-textarea-reaction-smiles", "value"),
    Input("id-select-reaction-example", "value"),
    prevent_initial_call=True,
)
def populate_example_reaction(example_value):
    """Populate the SMILES textarea when an example is selected.

    Args:
        example_value: The selected example reaction SMILES string.

    Returns:
        The SMILES string to put in the textarea.
    """
    if example_value:
        return example_value
    return ""


@callback(
    Output("id-btn-reaction-submit", "disabled"),
    [
        Input("id-input-reaction-query-name", "value"),
        Input("id-textarea-reaction-smiles", "value"),
    ],
)
def validate_reaction_form(query_name, smiles):
    """Enable/disable the submit button based on form validation.

    Args:
        query_name: The query name input value.
        smiles: The reaction SMILES input value.

    Returns:
        Boolean indicating whether submit should be disabled.
    """
    # Require both query name and SMILES to be non-empty
    if query_name and smiles and query_name.strip() and smiles.strip():
        return False
    return True


# TODO: Implement the actual search callback
# @callback(
#     Output("id-div-reaction-results", "children"),
#     Input("id-btn-reaction-submit", "n_clicks"),
#     [
#         State("id-input-reaction-query-name", "value"),
#         State("id-select-reaction-database", "value"),
#         State("id-textarea-reaction-smiles", "value"),
#     ],
#     prevent_initial_call=True,
# )
# def run_reaction_similarity_search(n_clicks, query_name, database, smiles):
#     """Execute the reaction similarity search.
#
#     TODO: Implement the actual search logic:
#     1. Load the selected database
#     2. Parse the query SMILES
#     3. Compute reaction fingerprints
#     4. Calculate Tanimoto/Russell/Cosine similarity
#     5. Return sorted results
#
#     Args:
#         n_clicks: Number of clicks on the submit button.
#         query_name: The query name for identification.
#         database: The selected database filename.
#         smiles: The reaction SMILES to search.
#
#     Returns:
#         Dash components displaying the search results.
#     """
#     pass
