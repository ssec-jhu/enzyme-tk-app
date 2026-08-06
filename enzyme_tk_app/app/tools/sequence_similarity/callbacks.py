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
from enzyme_tk_app.app.paths import SEQUENCES_DIR
from enzyme_tk_app.app.tools.sequence_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.data_loading import (
    get_ec_numbers,
    get_sequence_database_options,
    scan_sequence_databases,
    validate_db_names,
)
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
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
)
def populate_ec_options(database_values):
    """Populate the EC number filter dropdown when the selection changes.

    Fires on initial load (when the default databases are set) and
    whenever the user changes the selection.  Reads each database and offers
    the **union** of their EC numbers, so a filter is available for any
    entry that could appear in the merged search.  Also clears any
    previously selected values so stale EC filters are never carried over.

    Args:
        database_values: The selected database filenames.

    Returns:
        Tuple of (options list, empty selection list).
    """
    if not database_values:
        raise PreventUpdate

    usable, _problems = scan_sequence_databases()
    usable_names = set(usable)

    ec_numbers: set[str] = set()
    for name in database_values:
        # Sanitise client-supplied filename: strip directory components so a
        # name can never escape data/sequences/, then accept it only if it is
        # currently a compliant database.
        safe_name = Path(name).name
        if safe_name not in usable_names:
            continue
        ec_numbers.update(get_ec_numbers(SEQUENCES_DIR / safe_name))

    return [{"label": ec, "value": ec} for ec in sorted(ec_numbers)], []


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
)
def validate_sequence_form(task_name, sequence, databases):
    """Enable/disable the submit button based on form validation.

    Requires a non-empty task name, protein sequence, and at least one
    selected database.  EC filter, cofactor filter, and predict checkbox
    are optional and do not affect validation.

    Args:
        task_name: The task name input value.
        sequence: The protein sequence textarea value.
        databases: List of selected database values.

    Returns:
        Boolean indicating whether submit should be disabled.
    """
    has_name = task_name and task_name.strip()
    has_sequence = sequence and sequence.strip()
    has_databases = databases and len(databases) > 0
    # Disable the submit button if any required field is missing or empty.
    return not (has_name and has_sequence and has_databases)


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
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
    databases,
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
        databases: List of selected database filenames.
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
    if not task_name or not task_name.strip() or not sequence or not sequence.strip():
        raise PreventUpdate

    # Database names become file paths on the backend.
    error = validate_db_names(databases, get_sequence_database_options())
    if error:
        return error

    # Validate top_n.
    error = validate_top_n(top_n)
    if error:
        return error
    top_n = int(top_n)

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        # Key order mirrors the modal's field order — the results page renders
        # the Input Parameters rows in this order.
        params={
            "task_name": task_name.strip(),
            "sequence": sequence.strip(),
            "databases": databases,
            "ec_filter": ec_filter if ec_filter else [],
            "cofactor_filter": cofactor_filter if cofactor_filter else [],
            "top_n": top_n,
            "predict_catalytic": bool(predict_catalytic),
        },
        session_id=g.session_id,
    )

    # Format the message to include the job ID and any applied filters.
    msg = f"Job submitted — ID: {job_id} (searching for top {top_n} results"
    # Only mention filters if they are applied, to avoid cluttering the message.
    if ec_filter:
        msg += f", filtered by {len(ec_filter)} EC number(s)"
    msg += ")"

    return msg
