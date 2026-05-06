"""Tests for the Sequence & Structure-Based Similarity tool.

Exercises ``results_layout()`` and ``_get_column_defs()`` to verify that
the results grid is rendered correctly for various job result payloads
(valid data, empty data, missing dataframe, etc.).
"""

from unittest.mock import MagicMock, patch

import dash_ag_grid as dag
import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.sequence_structure_similarity import TOOL_DEF
from enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks import (
    display_uploaded_filename,
    populate_example_sequence,
    submit_structure_similarity_job,
    toggle_structure_similarity_modal,
    validate_structure_similarity_form,
)
from enzyme_tk_app.app.tools.sequence_structure_similarity.results import (
    _get_column_defs,
    results_layout,
)

# ── Column definitions ────────────────────────────────────────────────────────


def test_get_column_defs_expected_fields():
    """The column defs should include the core FoldSeek output fields."""
    fields = {col["field"] for col in _get_column_defs()}

    # Core fields that must always be present
    expected = {"query", "target", "database", "fident", "bits", "evalue", "alnlen"}
    assert expected.issubset(fields), f"Missing fields: {expected - fields}"


def test_results_layout_renders_grid():
    """Valid result data should produce a layout containing an AG Grid."""
    sample_job = {
        "columns": ["query", "target", "database", "fident", "bits", "evalue"],
        "data": [
            {"query": "Q1", "target": "T1", "database": "pdb", "fident": 0.95, "bits": 120.5, "evalue": 1e-10},
            {"query": "Q1", "target": "T2", "database": "afdb", "fident": 0.80, "bits": 90.2, "evalue": 1e-5},
        ],
    }
    job = make_job(result={"dataframe": sample_job})
    layout = results_layout(job)

    # Layout should be a html.Div
    assert isinstance(layout, html.Div)

    # Should contain an AG Grid component
    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AG Grid in the results layout"


@pytest.mark.parametrize(
    ("input_result", "expected_message"),
    [
        (None, "Results could not be loaded"),
        ({"dataframe": None}, "Results could not be loaded"),
        ({"dataframe": {}}, "Results could not be loaded"),
        ({"dataframe": "not_a_dict"}, "Results could not be loaded"),
        ({"dataframe": {"columns": ["query"], "data": []}}, "No similar sequences or structures found"),
        ({"dataframe": {"columns": ["query"]}}, "No similar sequences or structures found"),
    ],
)
def test_results_layout_no_data_shows_message(input_result, expected_message):
    """Results with no valid data should render an appropriate message instead of a grid."""
    job = make_job(result=input_result)
    layout = results_layout(job)

    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 0

    paragraphs = find_components(layout, html.P)
    assert len(paragraphs) == 1
    assert expected_message in paragraphs[0].children


# ── Callback logic ───────────────────────────────────────────────────────────


def test_toggle_modal_opens_on_launch():
    """The modal must open when the launch button is clicked."""
    with patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        assert toggle_structure_similarity_modal(1, 0) is True


def test_toggle_modal_closes_on_cancel():
    """The modal must close when the cancel button is clicked."""
    with patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-cancel"
        assert toggle_structure_similarity_modal(0, 1) is False


# ── populate_example_sequence ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "some_id",
    [
        None,
        "",
        0,
        "nonexistent-example-id",
    ],
)
def test_populate_example_raises_on_falsy_id(some_id):
    """A falsy example_id must raise PreventUpdate."""
    with pytest.raises(PreventUpdate):
        populate_example_sequence(some_id)


def test_populate_example_sequence_only():
    """A sequence-only example returns (sequence, no_update, no_update)."""
    # "A0A009IHW8-seq" is a sequence-only example (structure_file is None)
    seq, contents, filename = populate_example_sequence("A0A009IHW8-seq")

    assert seq.startswith("MSLEQKKGADIIS")
    assert contents is no_update
    assert filename is no_update


def test_populate_example_with_structure():
    """An example with a structure file returns base64-encoded content."""
    # "A0A009IHW8-struct" ships with a .cif structure file
    seq, contents, filename = populate_example_sequence("A0A009IHW8-struct")

    assert seq.startswith("MSLEQKKGADIIS")
    # contents should be a data URI with base64-encoded CIF data
    assert contents.startswith("data:chemical/x-cif;base64,")
    assert filename == "A0A009IHW8-chai.cif"


# ── display_uploaded_filename ─────────────────────────────────────────────────


def test_display_uploaded_filename_shows_name():
    """A truthy filename returns an html.Small element with the filename."""
    result = display_uploaded_filename("structure.cif")

    assert isinstance(result, html.Small)
    assert "structure.cif" in result.children


def test_display_uploaded_filename_returns_empty_on_none():
    """A falsy filename returns an empty string."""
    assert display_uploaded_filename(None) == ""


# ── validate_structure_similarity_form ────────────────────────────────────────


def test_validate_form_enables_when_all_fields_valid():
    """Submit button is enabled (False) when all required fields are provided."""
    assert validate_structure_similarity_form("My Task", "MKTAYIAK", ["pdb"]) is False


@pytest.mark.parametrize(
    ("task_name", "sequence", "databases"),
    [
        (None, "MKTAYIAK", ["pdb"]),
        ("  ", "MKTAYIAK", ["pdb"]),
        ("My Task", None, ["pdb"]),
        ("My Task", "  ", ["pdb"]),
        ("My Task", "MKTAYIAK", None),
        ("My Task", "MKTAYIAK", []),
    ],
    ids=["no-name", "blank-name", "no-seq", "blank-seq", "no-dbs", "empty-dbs"],
)
def test_validate_form_disables_when_field_missing(task_name, sequence, databases):
    """Submit button stays disabled (True) when any required field is missing."""
    assert validate_structure_similarity_form(task_name, sequence, databases) is True


# ── submit_structure_similarity_job ───────────────────────────────────────────


def test_submit_job_rejects_invalid_database_name():
    """Database names with disallowed characters must be rejected before reaching the scheduler."""
    with patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_structure_similarity_job(
            submit_clicks=1,
            launch_clicks=0,
            task_name="Bad DB test",
            sequence="MKTAYIAK",
            # bad database names
            databases=["valid-db", "../etc/passwd"],
            structure_contents=None,
            structure_filename=None,
        )

    # Must return an error message for the malicious database name.
    assert "Invalid database name" in result
    assert "../etc/passwd" in result


def test_submit_job_rejects_unsupported_structure_extension():
    """An uploaded structure file with a disallowed extension must be rejected."""
    with patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_structure_similarity_job(
            submit_clicks=1,
            launch_clicks=0,
            task_name="Extension test",
            sequence="MKTAYIAK",
            databases=["pdb"],
            structure_contents="data:application/octet-stream;base64,AAAA",
            # filename with unsupported extension
            structure_filename="protein.xyz",
        )

    assert "Unsupported file type" in result
    assert "protein.xyz" in result


def test_submit_job_sequence_mode_calls_scheduler():
    """A valid sequence-only submission calls the scheduler and returns a confirmation message."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415

    # Create a mock scheduler to verify that the job submission logic is
    # triggered correctly. The scheduler should be called with the expected parameters,
    # and we mock it to return a known job ID.
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-seq-99"

    # Use the Flask test request context to allow the callback
    # to access the session and other context variables.
    with server.test_request_context():
        # Set a session ID in the Flask global context,
        # as the callback expects it to be present.
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-123"
        with (
            # mock the Dash callback context to simulate the button click that triggers the job submission
            patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx,
            # mock the get_task_scheduler function to return our mock scheduler
            patch(
                "enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"

            # valid inputs for a sequence-only job (no structure content or filename)
            result = submit_structure_similarity_job(
                submit_clicks=1,
                launch_clicks=0,
                task_name="Seq search",
                sequence="MKTAYIAK",
                databases=["pdb"],
                structure_contents=None,
                structure_filename=None,
            )
    # Verify that the scheduler's submit_job method was called once with the expected parameters.
    mock_scheduler.submit_job.assert_called_once()
    assert "job-seq-99" in result
    assert "sequence" in result
