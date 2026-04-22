"""Callbacks for the Sequence Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Dynamically populate the EC number filter from the selected database
- Validate the form and enable/disable the submit button
- Submit a sequence similarity job to the backend scheduler
"""

from pathlib import Path

from dash import Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.tools.sequence_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.data_loading import DATA_DIR, get_ec_numbers
from enzyme_tk_app.app.utils.formatting import validate_top_n


@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_sequence_similarity_modal(launch_clicks, cancel_clicks):
    """Open or close the Sequence Similarity modal.

    The modal opens when the launch button is clicked and closes via
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
    Output(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
    prevent_initial_call=True,
)
def populate_example_sequence(example_value):
    """Populate the sequence textarea when an example is selected.

    Args:
        example_value: The selected example protein sequence string.

    Returns:
        The sequence string to put in the textarea.
    """
    if example_value:
        return example_value
    raise PreventUpdate


@callback(
    Output(f"id-dropdown-{TOOL_DEF['slug']}-ec-filter", "options"),
    Output(f"id-dropdown-{TOOL_DEF['slug']}-ec-filter", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-database", "value"),
)
def populate_ec_options(database_value):
    """Populate the EC number filter dropdown when the database changes.

    Fires on initial load (when the default database is set) and
    whenever the user selects a different database.  Reads the CSV,
    extracts sorted unique EC numbers, and returns them as dropdown
    options.  Also clears any previously selected values so stale
    EC filters are never carried over.

    Args:
        database_value: The selected database filename (e.g. ``protein.csv``).

    Returns:
        Tuple of (options list, empty selection list).
    """
    if not database_value:
        raise PreventUpdate

    # Sanitise client-supplied filename: strip directory components
    # to prevent path-traversal and enforce a .csv suffix.
    safe_name = Path(database_value).name
    if not safe_name.endswith(".csv"):
        return [], []

    csv_path = DATA_DIR / "sequences" / safe_name
    if not csv_path.exists():
        return [], []

    ec_numbers = get_ec_numbers(csv_path)
    return [{"label": ec, "value": ec} for ec in ec_numbers], []


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-database", "value"),
)
def validate_sequence_form(task_name, sequence, database):
    """Enable/disable the submit button based on form validation.

    Requires a non-empty task name, protein sequence, and database
    selection.  EC filter, cofactor filter, and predict checkbox are
    optional and do not affect validation.

    Args:
        task_name: The task name input value.
        sequence: The protein sequence textarea value.
        database: The selected database value.

    Returns:
        Boolean indicating whether submit should be disabled.
    """
    has_name = task_name and task_name.strip()
    has_sequence = sequence and sequence.strip()
    has_database = bool(database)
    if has_name and has_sequence and has_database:
        return False
    return True


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-database", "value"),
    State(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-ec-filter", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-cofactor-filter", "value"),
    State(f"id-input-{TOOL_DEF['slug']}-top-n", "value"),
    State(f"id-check-{TOOL_DEF['slug']}-predict-catalytic", "value"),
    prevent_initial_call=True,
)
def submit_sequence_similarity_job(
    submit_clicks,
    launch_clicks,
    task_name,
    database,
    sequence,
    ec_filter,
    cofactor_filter,
    top_n,
    predict_catalytic,
):
    """Submit a sequence similarity job or clear stale results on modal reopen.

    When triggered by the launch button, clears the results placeholder
    so stale job IDs from a previous submission are not shown.

    When triggered by the submit button, validates the inputs and
    submits the job to the backend scheduler.

    Args:
        submit_clicks: Number of clicks on the submit button.
        launch_clicks: Number of clicks on the launch button.
        task_name: The task name for identification.
        database: The selected database filename.
        sequence: The protein sequence to search.
        ec_filter: List of selected EC numbers (or None).
        cofactor_filter: List of selected cofactors (or None).
        top_n: Number of top results to return.
        predict_catalytic: Whether to predict catalytic residues.

    Returns:
        A status message with the submitted job ID, or an empty string
        when clearing stale state.
    """
    # Clear stale results when the modal is freshly opened.
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Server-side validation — the client disables the submit button
    # when fields are empty, but a crafted request could bypass that.
    if not task_name or not task_name.strip() or not sequence or not sequence.strip() or not database:
        raise PreventUpdate

    # Sanitise client-supplied filename: strip directory components
    # to prevent path-traversal and enforce a .csv suffix.
    safe_db = Path(database).name
    if not safe_db.endswith(".csv"):
        return "Invalid database filename."

    # Validate top_n.
    error = validate_top_n(top_n)
    if error:
        return error
    top_n = int(top_n)

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        params={
            "task_name": task_name.strip(),
            "database": safe_db,
            "sequence": sequence.strip(),
            "ec_filter": ec_filter if ec_filter else [],
            "cofactor_filter": cofactor_filter if cofactor_filter else [],
            "top_n": top_n,
            "predict_catalytic": bool(predict_catalytic),
        },
        session_id=g.session_id,
    )

    filters = []
    if ec_filter:
        filters.append(f"{len(ec_filter)} EC number(s)")
    msg = f"Job submitted — ID: {job_id} (searching for top {top_n} results"
    if filters:
        msg += f", filtered by {', '.join(filters)}"
    msg += ")"

    return msg
