"""Callbacks for the Substrate/Product Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input and role from example selection
- Validate the form and enable/disable the submit button
- Submit a substrate/product similarity job to the backend scheduler
"""

from dash import Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.tools.substrate_product_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.formatting import validate_top_n


@callback(
    # The "is_open" property of the modal is toggled by clicks on the
    # launch and cancel buttons.
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_substrate_product_similarity_modal(launch_clicks, cancel_clicks):
    """Open or close the Substrate/Product Similarity modal.

    The modal opens when the launch button is clicked and closes only via
    the Cancel button (or the header X).  The Submit button does **not**
    auto-close the modal so the user can see the returned job ID.

    Args:
        launch_clicks: Number of clicks on the launch button.
        cancel_clicks: Number of clicks on the cancel button.

    Returns:
        True to open the modal (launch), False to close it (cancel).
    """

    # only open the modal when the launch button is clicked;
    # the cancel button and header X will auto-close it via built-in behavior,
    # so we don't need to explicitly return False for those cases.
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return True
    return False


@callback(
    # Populate the SMILES textarea and role selector when an example is selected.
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Output(f"id-radio-{TOOL_DEF['slug']}-role", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
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
        # The example value is expected to be in the format "role||smiles",
        #  e.g. "substrate||CCO".
        role, smiles = example_value.split("||", 1)
        return smiles, role
    raise PreventUpdate


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
)
def validate_substrate_product_form(task_name, smiles, selected_databases, selected_algorithms):
    """Enable/disable the submit button based on form validation.

    Requires a non-empty task name, SMILES string, at least one
    selected database, and at least one selected algorithm.

    Args:
        task_name: The task name input value.
        smiles: The SMILES input value.
        selected_databases: List of selected database values.
        selected_algorithms: List of selected algorithm values.

    Returns:
        Boolean indicating whether the submit button should be disabled.
    """
    has_name = task_name and task_name.strip()
    has_smiles = smiles and smiles.strip()
    has_databases = selected_databases and len(selected_databases) > 0
    has_algorithms = selected_algorithms and len(selected_algorithms) > 0
    if has_name and has_smiles and has_databases and has_algorithms:
        return False
    return True


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    State(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
    State(f"id-input-{TOOL_DEF['slug']}-top-n", "value"),
    State(f"id-radio-{TOOL_DEF['slug']}-role", "value"),
    prevent_initial_call=True,
)
def submit_substrate_product_similarity_job(
    submit_clicks, launch_clicks, task_name, databases, smiles, algorithms, top_n, role
):
    """Submit a substrate/product similarity job or clear stale results on modal reopen.

    When triggered by the launch button, clears the results placeholder
    so stale job IDs from a previous submission are not shown.

    When triggered by the submit button, validates the inputs and
    submits the job to the backend scheduler.

    Args:
        submit_clicks: Number of clicks on the submit button.
        launch_clicks: Number of clicks on the launch button.
        task_name: The task name for identification.
        databases: List of selected database filenames.
        smiles: The molecule SMILES to search.
        algorithms: List of selected algorithm values.
        top_n: Number of top results to return.
        role: The molecule role — ``"substrate"`` or ``"product"``.

    Returns:
        A status message with the submitted job ID, or an empty string
        when clearing stale state.
    """
    # Clear stale results when the modal is freshly opened
    # do not use prevent update here because we want to return 
    # an empty string to clear the results div

    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Server-side validation — the client disables the submit button
    # when fields are empty, but a crafted request could bypass that.
    if (
        not task_name
        or not task_name.strip()
        or not smiles
        or not smiles.strip()
        or not databases
        or not algorithms
        or not role
    ):
        raise PreventUpdate

    # Validate top_n
    error = validate_top_n(top_n)
    if error:
        return error
    top_n = int(top_n)

    # get the task scheduler and submit the job with the collected parameters
    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        # The parameters dict will be passed to the backend job for processing.
        # We include all the relevant form inputs so the backend has everything it
        # needs to run the similarity search.
        params={
            "task_name": task_name.strip(),
            "databases": databases,  # list of selected database filenames
            "smiles": smiles.strip(),
            "algorithms": algorithms,  # list of selected algorithm values
            "top_n": top_n,
            "role": role,  # "substrate" or "product"
        },
        # We also pass the session ID from Flask's `g` so the backend
        # can associate the job with the user's session if needed.
        session_id=g.session_id,
    )

    # Construct a user-friendly message that includes the job ID and a
    # summary of the search parameters.
    n_dbs = len(databases) if databases else 0
    role_label = role.capitalize() if role else "Substrate"
    return f"Job submitted — ID: {job_id} ({role_label} search across {n_dbs} database(s) for top {top_n} results)"
