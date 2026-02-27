"""Callbacks for the Substrate/Product Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input and role from example selection
- Handle form validation
"""

from dash import Input, Output, callback, ctx


@callback(
    Output("id-modal-substrate-product-similarity", "is_open"),
    [
        Input("id-btn-launch-substrate-product-similarity", "n_clicks"),
        Input("id-btn-subprod-cancel", "n_clicks"),
        Input("id-btn-subprod-submit", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def toggle_substrate_product_similarity_modal(launch_clicks, cancel_clicks, submit_clicks):
    """Open or close the Substrate/Product Similarity modal.

    Opens the modal when the launch button is clicked, and closes it
    when the cancel or submit button is clicked.

    Args:
        launch_clicks: Number of clicks on the launch button.
        cancel_clicks: Number of clicks on the cancel button.
        submit_clicks: Number of clicks on the submit button.

    Returns:
        True to open the modal (launch), False to close it (cancel/submit).
    """
    if ctx.triggered_id == "id-btn-launch-substrate-product-similarity":
        return True
    return False


@callback(
    [
        Output("id-textarea-subprod-smiles", "value"),
        Output("id-radio-subprod-role", "value"),
    ],
    Input("id-select-subprod-example", "value"),
    prevent_initial_call=True,
)
def populate_example_smiles(example_value):
    """Populate the SMILES textarea and role selector when an example is selected.

    The example value is encoded as ``"role||smiles"`` so both the molecule
    role (substrate/product) and the SMILES string can be set from a single
    dropdown selection.

    Args:
        example_value: The encoded example string (``"role||smiles"``).

    Returns:
        Tuple of (smiles_string, role_value) to populate the form fields.
    """
    if example_value and "||" in example_value:
        role, smiles = example_value.split("||", 1)
        return smiles, role
    return "", "substrate"


@callback(
    Output("id-btn-subprod-submit", "disabled"),
    [
        Input("id-input-subprod-query-name", "value"),
        Input("id-textarea-subprod-smiles", "value"),
    ],
)
def validate_substrate_product_form(query_name, smiles):
    """Enable/disable the submit button based on form validation.

    Both query name and SMILES must be non-empty for the form to be valid.

    Args:
        query_name: The query name input value.
        smiles: The SMILES input value.

    Returns:
        Boolean indicating whether the submit button should be disabled.
    """
    if query_name and smiles and query_name.strip() and smiles.strip():
        return False
    return True
