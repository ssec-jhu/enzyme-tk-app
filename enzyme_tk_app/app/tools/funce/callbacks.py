"""Callbacks for the Func-E Activity Prediction tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input from example selection
- Validate the form and enable/disable the submit button
- Submit a Func-E job to the backend scheduler
"""

from dash import Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.components.modal_helpers import build_submission_success
from enzyme_tk_app.app.tools.funce import EXAMPLE_REACTIONS, TOOL_DEF
from enzyme_tk_app.app.utils.captcha import validate_captcha
from enzyme_tk_app.app.utils.data_loading import get_sequence_embedding_database_options, validate_db_names
from enzyme_tk_app.app.utils.formatting import validate_top_n

# Safe at module scope: smiles_validation imports rdkit inside its functions, so
# nothing heavy loads until the user actually types into the SMILES field.
from enzyme_tk_app.app.utils.smiles_validation import validate_reaction_smiles
from enzyme_tk_app.app.utils.submission_limits import validate_active_job_limit

# Build lookup dict: example SMILES (the dropdown value) -> task name.
_TASK_NAMES_BY_VALUE = {ex["value"]: ex["task_name"] for ex in EXAMPLE_REACTIONS}


@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_funce_modal(launch_clicks, cancel_clicks):
    """Open or close the Func-E modal.

    The modal opens when the launch button is clicked and closes only via
    the Cancel button (or the header X).  The Submit button does not
    auto-close the modal so the user can see the returned job ID.

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
    Output(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
    prevent_initial_call=True,
)
def populate_example_reaction(example_value):
    """Populate the SMILES textarea and Task Name when an example is selected.

    The Task Name is prefilled with the example's own name so a run is
    submittable in one click — it is the one field that otherwise blocks submit.
    An already-typed name is overwritten, like every other example-filled field.

    Args:
        example_value: The selected example reaction SMILES string.

    Returns:
        Tuple of (smiles_string, task_name).  The task name is ``no_update``
        for a SMILES that is not one of the shipped examples.
    """
    if not example_value:
        raise PreventUpdate

    task_name = _TASK_NAMES_BY_VALUE.get(example_value)
    return example_value, task_name or no_update


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "invalid"),
    Output(f"id-feedback-{TOOL_DEF['slug']}-smiles", "children"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
)
def validate_funce_form(task_name, smiles, databases):
    """Enable/disable the submit button and mark an unusable reaction SMILES.

    Requires a non-empty task name, a reaction SMILES that actually parses, and
    at least one selected protein database.  Rejecting the structure here rather
    than on submit spares the user a minute-long job that would die inside UniMol.

    Args:
        task_name: The task name input value.
        smiles: The reaction SMILES input value.
        databases: List of selected database filenames.

    Returns:
        Tuple of (submit disabled, textarea invalid, feedback message).
    """
    smiles_error = validate_reaction_smiles(smiles)
    # A blank field is not a mistake yet — it disables Run without turning red.
    show_error = bool(smiles and smiles.strip() and smiles_error)

    has_name = task_name and task_name.strip()
    has_databases = databases and len(databases) > 0
    disabled = not (has_name and not smiles_error and has_databases)

    return disabled, show_error, smiles_error if show_error else ""


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    State(f"id-input-{TOOL_DEF['slug']}-top-n", "value"),
    State(f"id-store-{TOOL_DEF['slug']}-captcha", "data"),
    prevent_initial_call=True,
)
def submit_funce_job(submit_clicks, launch_clicks, task_name, smiles, databases, top_n, captcha_payload):
    """Submit a Func-E job or clear stale results on modal reopen.

    When triggered by the launch button, clears the results placeholder
    so stale job IDs from a previous submission are not shown.

    When triggered by the submit button, validates the inputs and
    submits the job to the backend scheduler.

    Args:
        submit_clicks: Number of clicks on the submit button.
        launch_clicks: Number of clicks on the launch button.
        task_name: The task name for identification.
        smiles: The reaction SMILES to score.
        databases: List of selected pre-encoded database filenames.
        top_n: Number of top results to return.
        captcha_payload: Solved proof-of-work payload from the modal's captcha Store.

    Returns:
        A status message with the submitted job ID, or an empty string
        when clearing stale state.
    """
    # Clear stale results when the modal is freshly opened
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Re-validate server-side even though the UI disables submit — the
    # database names become file paths.
    if not task_name or not task_name.strip():
        raise PreventUpdate

    # Reject a malformed reaction here rather than a minute into the worker, where
    # it dies inside UniMol.  Reports the empty case itself, like validate_db_names,
    # so the guard above must not test the SMILES and swallow that message.
    error = validate_reaction_smiles(smiles)
    if error:
        return error

    # Reject any name the dropdown is not currently offering — it becomes a file
    # path under SEQUENCE_EMBEDDINGS_DIR on the backend.
    error = validate_db_names(databases, get_sequence_embedding_database_options())
    if error:
        return error

    error = validate_top_n(top_n)
    if error:
        return error
    top_n = int(top_n)

    # Both no-ops unless the deployment switched production mode on, and both sit after the
    # field validators so a malformed submit still shows its own error rather than "tick the
    # box".  The captcha goes first: it costs no Redis round-trip, so an unverified caller
    # never gets the cap's O(N) read for free.
    error = validate_captcha(captcha_payload, g.session_id)
    if error:
        return error

    error = validate_active_job_limit(g.session_id)
    if error:
        return error

    # At this point every input has been validated.
    # Proceed to submit the job to the scheduler
    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        # Pass the validated parameters to the job submission.  Key order mirrors
        # the modal's field order — the results page renders the Input Parameters
        # rows in this order.
        params={
            "task_name": task_name.strip(),
            # Keyed "smiles" so the results page renders the reaction diagram
            # automatically (see results_helpers._SMILES_PARAM_KEYS).
            "smiles": smiles.strip(),
            "databases": databases,
            "top_n": top_n,
        },
        session_id=g.session_id,
    )

    detail = f"{len(databases)} database(s) · top {top_n}"
    return build_submission_success(job_id, detail)
