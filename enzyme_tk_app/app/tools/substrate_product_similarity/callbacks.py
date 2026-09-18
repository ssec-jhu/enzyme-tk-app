"""Callbacks for the Substrate/Product Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the SMILES input and role from example selection
- Validate the form and enable/disable the submit button
- Submit a substrate/product similarity job to the backend scheduler
"""

from dash import Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.components.modal_helpers import build_submission_error, build_submission_success
from enzyme_tk_app.app.tools.substrate_product_similarity import TOOL_DEF, MoleculeRole
from enzyme_tk_app.app.tools.substrate_product_similarity.modal import _get_example_smiles
from enzyme_tk_app.app.utils.captcha import validate_captcha
from enzyme_tk_app.app.utils.data_availability import validate_tool_data
from enzyme_tk_app.app.utils.data_loading import get_reaction_database_options, validate_db_names
from enzyme_tk_app.app.utils.formatting import validate_top_n

# Safe at module scope: smiles_validation imports rdkit inside its functions, so
# nothing heavy loads until the user actually types into the SMILES field.
from enzyme_tk_app.app.utils.smiles_validation import validate_smiles
from enzyme_tk_app.app.utils.submission_limits import validate_active_job_limit

# Build lookup dict: encoded dropdown value ("role||smiles") -> task name.
_TASK_NAMES_BY_VALUE = {f"{ex['role']}||{ex['value']}": ex["task_name"] for ex in _get_example_smiles()}


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
    # Populate the SMILES textarea, role selector and Task Name when an example is selected.
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Output(f"id-radio-{TOOL_DEF['slug']}-role", "value"),
    Output(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
    prevent_initial_call=True,
)
def populate_example_smiles(example_value):
    """Populate the SMILES textarea, role selector and Task Name from an example.

    The example value is encoded as ``"role||smiles"`` so both the molecule
    role (substrate/product) and the SMILES string can be set from a single
    dropdown selection.  The Task Name is prefilled with the example's own
    name so a run is submittable in one click — it is the one field that
    otherwise blocks submit.  An already-typed name is overwritten, like every
    other example-filled field.

    Args:
        example_value: The encoded example string (``"role||smiles"``).

    Returns:
        Tuple of (smiles_string, role_value, task_name).  The task name is
        ``no_update`` for a value that is not one of the shipped examples.
    """
    if not example_value or "||" not in example_value:
        raise PreventUpdate

    # The example value is expected to be in the format "role||smiles",
    #  e.g. "substrate||CCO".
    role, smiles = example_value.split("||", 1)
    task_name = _TASK_NAMES_BY_VALUE.get(example_value)
    return smiles, role, task_name or no_update


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "invalid"),
    Output(f"id-feedback-{TOOL_DEF['slug']}-smiles", "children"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
)
def validate_substrate_product_form(task_name, smiles, selected_databases, selected_algorithms):
    """Enable/disable the submit button and mark an unusable SMILES.

    Requires a non-empty task name, a molecule SMILES that actually parses, at
    least one selected database, and at least one selected algorithm.  This
    field takes one structure, so a reaction pasted into it is rejected here
    with a message naming the ``>>`` rather than deep inside ``SubstrateDist``.

    Args:
        task_name: The task name input value.
        smiles: The SMILES input value.
        selected_databases: List of selected database values.
        selected_algorithms: List of selected algorithm values.

    Returns:
        Tuple of (submit disabled, textarea invalid, feedback message).
    """
    smiles_error = validate_smiles(smiles)
    # A blank field is not a mistake yet — it disables Run without turning red.
    show_error = bool(smiles and smiles.strip() and smiles_error)

    has_name = task_name and task_name.strip()
    has_databases = selected_databases and len(selected_databases) > 0
    has_algorithms = selected_algorithms and len(selected_algorithms) > 0
    # A tool whose reference data is absent cannot run whatever is typed, so the gate lives
    # here too — the modal's results row names the missing files.
    has_fields = has_name and not smiles_error and has_databases and has_algorithms
    disabled = not has_fields or validate_tool_data(TOOL_DEF["slug"]) is not None

    return disabled, show_error, smiles_error if show_error else ""


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
    State(f"id-store-{TOOL_DEF['slug']}-captcha", "data"),
    prevent_initial_call=True,
)
def submit_substrate_product_similarity_job(
    submit_clicks, launch_clicks, task_name, databases, smiles, algorithms, top_n, role, captcha_payload
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
        captcha_payload: Solved proof-of-work payload from the modal's captcha Store.

    Returns:
        A status message with the submitted job ID; on reopen, an empty string —
        or a missing-data error row when the tool has no data to run against.
    """
    # Clear stale results when the modal is freshly opened
    # do not use prevent update here because we want to return
    # an empty string to clear the results div

    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        # ...or, when the tool cannot run at all, say why: the card's badge is the first
        # warning, this is the second, beside the Run button the same check disables.
        error = validate_tool_data(TOOL_DEF["slug"])
        return build_submission_error(error) if error else ""

    # First, ahead of every field validator: missing data is a property of the deployment and
    # no correction to the form can fix it.  (The job cap is last, for the opposite reason.)
    error = validate_tool_data(TOOL_DEF["slug"])
    if error:
        return build_submission_error(error)

    # Server-side validation — the client disables the submit button
    # when fields are empty, but a crafted request could bypass that.
    if not task_name or not task_name.strip() or not algorithms or not role:
        raise PreventUpdate

    # Reject an unusable molecule here rather than inside SubstrateDist, where an
    # unparseable string reaches mfpgen.GetFingerprint(None) and raises a C++
    # signature dump.  Reports the empty case itself, like validate_db_names, so
    # the guard above must not test the SMILES and swallow that message.
    error = validate_smiles(smiles)
    if error:
        return build_submission_error(error)

    # Database names become file paths on the backend.
    error = validate_db_names(databases, get_reaction_database_options())
    if error:
        return build_submission_error(error)

    # Validate top_n
    error = validate_top_n(top_n)
    if error:
        return build_submission_error(error)
    top_n = int(top_n)

    # Both no-ops unless the deployment switched production mode on, and both sit after the
    # field validators so a malformed submit still shows its own error rather than "tick the
    # box".  The captcha goes first: it costs no Redis round-trip, so an unverified caller
    # never gets the cap's O(N) read for free.
    error = validate_captcha(captcha_payload, g.session_id)
    if error:
        return build_submission_error(error)

    error = validate_active_job_limit(g.session_id)
    if error:
        return build_submission_error(error)

    # get the task scheduler and submit the job with the collected parameters
    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        # The parameters dict will be passed to the backend job for processing.
        # We include all the relevant form inputs so the backend has everything it
        # needs to run the similarity search.  Key order mirrors the modal's field
        # order — the results page renders the Input Parameters rows in this order.
        params={
            "task_name": task_name.strip(),
            "role": role,  # "substrate" or "product"
            "smiles": smiles.strip(),
            "databases": databases,  # list of selected database filenames
            "algorithms": algorithms,  # list of selected algorithm values
            "top_n": top_n,
        },
        # We also pass the session ID from Flask's `g` so the backend
        # can associate the job with the user's session if needed.
        session_id=g.session_id,
    )

    n_dbs = len(databases) if databases else 0
    role_label = role.capitalize() if role else MoleculeRole.SUBSTRATE.value.capitalize()
    detail = f"{role_label} · {n_dbs} database(s) · top {top_n}"
    return build_submission_success(job_id, detail)
