"""Callbacks for the Sequence & Structure-Based Similarity tool modal.

This module defines callbacks that:
- Open/close the modal when the launch button is clicked
- Populate the sequence textarea and optionally the structure upload from example selection
- Display the uploaded structure filename
- Validate the form and enable/disable the submit button
- Submit a FoldSeek similarity job to the backend scheduler
"""

import base64
import re
from pathlib import Path

from dash import Input, Output, State, callback, ctx, html, no_update
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.paths import STRUCTURES_DIR
from enzyme_tk_app.app.tools.sequence_structure_similarity import ALLOWED_EXTENSIONS, TOOL_DEF
from enzyme_tk_app.app.tools.sequence_structure_similarity.modal import _get_example_entries

# Build lookup dict: example id -> entry.
_EXAMPLES_BY_ID = {ex["value"]: ex for ex in _get_example_entries()}

# Map structure file extensions to MIME types for data-URI encoding.
_MIME_BY_EXT: dict[str, str] = {
    ".cif": "chemical/x-cif",
    ".mmcif": "chemical/x-mmcif",
    ".pdb": "chemical/x-pdb",
}


@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_structure_similarity_modal(launch_clicks, cancel_clicks):
    """Open or close the Sequence & Structure-Based Similarity modal.

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
    Output(f"id-upload-{TOOL_DEF['slug']}-structure", "contents"),
    Output(f"id-upload-{TOOL_DEF['slug']}-structure", "filename"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
    prevent_initial_call=True,
)
def populate_example_sequence(example_id):
    """Populate the sequence textarea and optionally the structure upload.

    When an example with a bundled structure file is selected, the
    structure file is read from disk, base64-encoded, and injected into
    the ``dcc.Upload`` component.  For sequence-only examples, the
    upload fields are left unchanged via ``no_update``.

    Args:
        example_id: The ID of the selected example entry.

    Returns:
        Tuple of (sequence, structure_contents, structure_filename).
    """
    # Don't update anything if the example ID is invalid or not found.
    if not example_id:
        raise PreventUpdate

    # get the example entry from the lookup dict; if not found, do not update.
    entry = _EXAMPLES_BY_ID.get(example_id)
    if not entry:
        raise PreventUpdate

    # Extract the sequence and structure info from the entry.
    sequence = entry["sequence"]
    structure_file = entry.get("structure_file")

    # This is only for the example sequences that ship with a structure
    if structure_file:
        file_path = STRUCTURES_DIR / structure_file
        raw_bytes = file_path.read_bytes()
        encoded = base64.b64encode(raw_bytes).decode("ascii")
        mime_type = _MIME_BY_EXT.get(file_path.suffix.lower(), "application/octet-stream")
        contents = f"data:{mime_type};base64,{encoded}"
        return sequence, contents, structure_file

    # return the sequence and leave the upload unchanged for sequence-only examples
    return sequence, no_update, no_update


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-upload-filename", "children"),
    Input(f"id-upload-{TOOL_DEF['slug']}-structure", "filename"),
    prevent_initial_call=True,
)
def display_uploaded_filename(filename):
    """Show the uploaded structure filename below the upload area.

    Args:
        filename: The name of the uploaded file (or None).

    Returns:
        A small text element showing the filename, or empty string.
    """
    # if a structure file is uploaded, display its filename; otherwise, show nothing
    if filename:
        return html.Small(
            f"Uploaded: {filename}",
            style={"color": "var(--primary-color)", "fontWeight": "600"},
        )
    return ""


@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
)
def validate_structure_similarity_form(task_name, sequence, databases):
    """Enable/disable the submit button based on form validation.

    Requires a non-empty task name, protein sequence, and at least one
    database selection.  Structure file upload is optional.

    Args:
        task_name: The task name input value.
        sequence: The protein sequence textarea value.
        databases: The selected database values (list).

    Returns:
        Boolean indicating whether submit should be disabled.
    """
    has_name = task_name and task_name.strip()
    has_sequence = sequence and sequence.strip()
    has_databases = databases and len(databases) > 0

    # Enable the submit button only if all required fields are valid; otherwise, disable it.
    if has_name and has_sequence and has_databases:
        return False

    # keep the button disabled if any required field is missing or invalid
    return True


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-textarea-{TOOL_DEF['slug']}-sequence", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    State(f"id-upload-{TOOL_DEF['slug']}-structure", "contents"),
    State(f"id-upload-{TOOL_DEF['slug']}-structure", "filename"),
    prevent_initial_call=True,
)
def submit_structure_similarity_job(
    submit_clicks,
    launch_clicks,
    task_name,
    sequence,
    databases,
    structure_contents,
    structure_filename,
):
    """Submit a FoldSeek similarity job or clear stale results on modal reopen.

    When triggered by the launch button, clears the results placeholder
    so stale job IDs from a previous submission are not shown.

    When triggered by the submit button, validates the inputs and
    submits the job to the backend scheduler.

    Args:
        submit_clicks: Number of clicks on the submit button.
        launch_clicks: Number of clicks on the launch button.
        task_name: The task name for identification.
        sequence: The protein sequence to search.
        databases: List of selected database folder names.
        structure_contents: Base64-encoded file content from dcc.Upload (or None).
        structure_filename: Uploaded file name (or None).

    Returns:
        A status message with the submitted job ID, or an empty string
        when clearing stale state.
    """
    # Clear stale results when the modal is freshly opened.
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Server-side validation.
    if not task_name or not task_name.strip() or not sequence or not sequence.strip() or not databases:
        raise PreventUpdate

    # Validate database names — only allow alphanumeric, underscores, and hyphens.
    # this should not happen if the dropdown options are properly generated from the filesystem,
    # but we check again here to be safe since these values will be used in file paths on the backend.
    sanitized_dbs = []
    for db_name in databases:
        # Strip whitespace
        safe = str(db_name).strip()
        # Reject any names that contain characters other than letters, numbers, underscores, or hyphens.
        if not re.match(r"^[0-9A-Za-z_-]+$", safe):
            return f"Invalid database name: {db_name}. Name must only contain numbers, letters, and _ or -"
        sanitized_dbs.append(safe)

    # sanity check: ensure we have at least one valid database after sanitization
    if not sanitized_dbs:
        return "No valid databases found in the selection. Check the database names and try again."

    # Validate structure file extension if provided.
    if structure_filename:
        # Extract the file extension and check against allowed extensions.
        ext = Path(structure_filename).suffix.lower()
        # the UI upload component should prevent disallowed file types,
        # but we validate again here to be safe since the file will be processed on the backend.
        if ext not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            return f"Unsupported file type: {structure_filename}. Allowed: {allowed}"

    # Determine mode for the status message.
    mode = "structure" if structure_contents else "sequence"

    params = {
        "task_name": task_name.strip(),
        "sequence": sequence.strip(),
        "databases": sanitized_dbs,
        "structure_content": structure_contents if structure_contents else None,
        "structure_filename": structure_filename if structure_contents else None,
    }

    # ready to submit the job to the backend scheduler
    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        params=params,
        session_id=g.session_id,
    )

    # common feedback to the user amongst all tools
    db_list = ", ".join(sanitized_dbs)
    msg = f"Job submitted — ID: {job_id} ({mode} mode, databases: {db_list})"
    return msg
