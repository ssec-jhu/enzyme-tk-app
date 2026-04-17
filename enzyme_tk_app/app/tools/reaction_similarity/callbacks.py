"""Callbacks for the Reaction Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input from example selection
- Validate the form and enable/disable the submit button
- Submit a reaction similarity job to the backend scheduler
"""

from dash import Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.tools.reaction_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.formatting import validate_top_n


@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_reaction_similarity_modal(launch_clicks, cancel_clicks):
    """Open or close the Reaction Similarity modal.

    The modal opens when the launch button is clicked and closes only via
    the Cancel button (or the header X).  The Submit button no longer
    auto-closes the modal so the user can see the returned job ID.

    Args:
        launch_clicks: Number of clicks on the launch button.
        cancel_clicks: Number of clicks on the cancel button.

    Returns:
        True to open the modal (launch), False to close it (cancel).
    """
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return True
    return False


@callback(
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
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
    raise PreventUpdate


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
)
def validate_reaction_form(task_name, smiles, selected_databases, selected_algorithms):
    """Enable/disable the submit button based on form validation.

    Requires a non-empty task name, SMILES string, at least one
    selected database, and at least one selected algorithm.

    Args:
        task_name: The task name input value.
        smiles: The reaction SMILES input value.
        selected_databases: List of selected database values.
        selected_algorithms: List of selected algorithm values.

    Returns:
        Boolean indicating whether submit should be disabled.
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
    prevent_initial_call=True,
)
def submit_reaction_similarity_job(submit_clicks, launch_clicks, task_name, databases, smiles, algorithms, top_n):
    """Submit a reaction similarity job or clear stale results on modal reopen.

    When triggered by the launch button, clears the results placeholder
    so stale job IDs from a previous submission are not shown.

    When triggered by the submit button, validates the inputs and
    submits the job to the backend scheduler.

    Args:
        submit_clicks: Number of clicks on the submit button.
        launch_clicks: Number of clicks on the launch button.
        task_name: The task name for identification.
        databases: List of selected database filenames.
        smiles: The reaction SMILES to search.
        algorithms: List of selected algorithm values.
        top_n: Number of top results to return.

    Returns:
        A status message with the submitted job ID, or an empty string
        when clearing stale state.
    """
    # Clear stale results when the modal is freshly opened
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Validate top_n
    error = validate_top_n(top_n)
    if error:
        return error
    top_n = int(top_n)

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        params={
            "task_name": task_name.strip(),
            "databases": databases,
            "smiles": smiles.strip(),
            "algorithms": algorithms,
            "top_n": top_n,
        },
        session_id=g.session_id,
    )

    n_dbs = len(databases) if databases else 0
    return f"Job submitted — ID: {job_id} (searching {n_dbs} database(s) for top {top_n} results)"
