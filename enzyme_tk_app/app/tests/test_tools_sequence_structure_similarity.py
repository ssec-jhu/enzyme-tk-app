"""Tests for the Sequence & Structure-Based Similarity tool.

Exercises ``results_layout()`` and ``_get_column_defs()`` to verify that
the results grid is rendered correctly for various job result payloads
(valid data, empty data, missing dataframe, etc.).

Tests that call FoldSeek require the ``foldseek`` binary in ``$PATH``
(installed in the Docker worker image).  They are automatically
skipped when foldseek is unavailable so the rest of the suite keeps
passing in local development.
"""

import base64
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import dash_ag_grid as dag
import pandas as pd
import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.paths import STRUCTURES_DIR
from enzyme_tk_app.app.tests.conftest import find_components, get_text, make_job, offered_databases, submitted_job_id
from enzyme_tk_app.app.tools.sequence_structure_similarity import TOOL_DEF
from enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks import (
    display_uploaded_filename,
    populate_example_sequence,
    submit_structure_similarity_job,
    toggle_structure_similarity_modal,
    validate_structure_similarity_form,
)
from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import _decode_structure_file
from enzyme_tk_app.app.tools.sequence_structure_similarity.results import (
    _get_column_defs,
    results_layout,
)

# ── FoldSeek availability check ───────────────────────────────────────────────

_foldseek_available = shutil.which("foldseek") is not None
_skip_no_foldseek = pytest.mark.skipif(
    not _foldseek_available,
    reason="foldseek binary not found in $PATH (install foldseek or run in Docker)",
)

# ── Constants ─────────────────────────────────────────────────────────────────

# 1AKI lysozyme — 129 residues; used as both the query and DB entry.
_SEQ_1AKI = (
    "KVFGRCELAAAMKRHGLDNYRGYSLGNWVCAAKFESNFNTQATNRNTDGSTDYGILQINS"
    "RWWCNDGRTPGSRNLCNIPCSALLSSDITASVNCAKKIVSDGNGMNAWVAWRNRCKGTDVQ"
    "AWIRGCRL"
)

# Path to the bundled 1AKI CIF file shipped with the app.
_CIF_1AKI = STRUCTURES_DIR / "1AKI.cif"

# ── _decode_structure_file ────────────────────────────────────────────────────


def test_decode_structure_file_writes_and_returns_path(tmp_path):
    """A base64 data-URI is decoded, written to tmpdir, and the returned path has the correct suffix and content."""
    original_bytes = b"HEADER    TEST STRUCTURE"
    encoded = base64.b64encode(original_bytes).decode()
    data_uri = f"data:application/octet-stream;base64,{encoded}"

    result_path = _decode_structure_file(data_uri, "my_protein.cif", str(tmp_path))

    result = Path(result_path)
    # File must live inside the provided temp directory.
    assert result.parent == tmp_path
    # Suffix must match the original filename's extension.
    assert result.suffix == ".cif"
    # Decoded content must match the original bytes.
    assert result.read_bytes() == original_bytes


def test_decode_structure_file_raw_base64_without_data_uri(tmp_path):
    """When *structure_content* has no comma (raw base64, no data-URI prefix), the payload is used as-is."""
    original_bytes = b"HEADER    RAW TEST STRUCTURE"
    encoded = base64.b64encode(original_bytes).decode()

    result_path = _decode_structure_file(encoded, "protein.pdb", str(tmp_path))

    result = Path(result_path)
    assert result.parent == tmp_path
    assert result.suffix == ".pdb"
    assert result.read_bytes() == original_bytes


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
    """A falsy or nonexistent example_id must raise PreventUpdate."""
    with pytest.raises(PreventUpdate):
        populate_example_sequence(some_id)


def test_populate_example_sequence_only():
    """A sequence-only example returns (sequence, no_update, no_update, task_name)."""
    # "A0A009IHW8-seq" is a sequence-only example (structure_file is None)
    seq, contents, filename, task_name = populate_example_sequence("A0A009IHW8-seq")

    assert seq.startswith("MSLEQKKGADIIS")
    assert contents is no_update
    assert filename is no_update
    assert task_name == "A0A009IHW8-sequence"


def test_populate_example_with_structure():
    """An example with a structure file returns base64-encoded content."""
    # "A0A009IHW8-struct" ships with a .cif structure file
    seq, contents, filename, task_name = populate_example_sequence("A0A009IHW8-struct")

    assert seq.startswith("MSLEQKKGADIIS")
    # contents should be a data URI with base64-encoded CIF data
    assert contents.startswith("data:chemical/x-cif;base64,")
    assert filename == "A0A009IHW8-chai.cif"
    # The two A0A009IHW8 examples differ only by the sequence/structure suffix.
    assert task_name == "A0A009IHW8-structure"


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


def test_submit_job_rejects_database_the_dropdown_does_not_offer():
    """A database name the dropdown is not offering must be rejected before the scheduler.

    "valid-db" is offered, so the rejection can only come from the traversal
    attempt beside it — one bad name in the list fails the whole submission.
    """
    with (
        patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.get_foldseek_database_options",
            return_value=offered_databases("valid-db"),
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_structure_similarity_job(
            submit_clicks=1,
            launch_clicks=0,
            task_name="Bad DB test",
            sequence="MKTAYIAK",
            # one offered name and one malicious one
            databases=["valid-db", "../etc/passwd"],
            structure_contents=None,
            structure_filename=None,
            captcha_payload=None,
        )

    # Must return an error message naming the malicious database name.
    assert "Unknown database" in result
    assert "../etc/passwd" in result


def test_submit_job_rejects_unsupported_structure_extension():
    """An uploaded structure file with a disallowed extension must be rejected."""
    with (
        patch("enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.get_foldseek_database_options",
            return_value=offered_databases("pdb"),
        ),
    ):
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
            captcha_payload=None,
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
            # the dropdown offers "pdb", so the name below passes validation
            patch(
                "enzyme_tk_app.app.tools.sequence_structure_similarity.callbacks.get_foldseek_database_options",
                return_value=offered_databases("pdb"),
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
                captcha_payload=None,
            )
    # Verify that the scheduler's submit_job method was called once with the expected parameters.
    mock_scheduler.submit_job.assert_called_once()
    assert submitted_job_id(result) == "job-seq-99"
    assert "sequence" in get_text(result)


# ── run() — mocked FoldSeek (no binary required) ─────────────────────────────

# Patch target for the lazy import inside compute.run().
_FOLDSEEK_MODULE = "enzymetk.similarity_sequence_and_structure_step"


def _seq_mode_params(**overrides):
    """Return valid ``run()`` params for sequence-only mode."""
    defaults = {
        "task_name": "mock-seq-run",
        "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVK",
        "databases": ["mock_db"],
        "structure_content": None,
        "structure_filename": None,
    }
    defaults.update(overrides)
    return defaults


def _structure_mode_params(**overrides):
    """Return valid ``run()`` params for structure mode (CIF upload)."""
    cif_bytes = b"data_1AKI\n_entry.id 1AKI\n"
    b64 = base64.b64encode(cif_bytes).decode()
    defaults = {
        "task_name": "mock-struct-run",
        "sequence": "MKTAYIAK",
        "databases": ["mock_db"],
        "structure_content": f"data:chemical/x-cif;base64,{b64}",
        "structure_filename": "1AKI.cif",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture()
def _mock_foldseek(monkeypatch):
    """Patch FoldSeek so run() never shells out to the foldseek binary.

    The patched ``FoldSeek.execute`` returns a 3-row DataFrame by default.
    Tests can override via ``monkeypatch`` on ``mock_step.execute``.
    """
    mock_step = MagicMock()
    n_hits = 3
    # The exact content of the DataFrame doesn't matter for most tests, as long as
    # it has the expected columns and a few rows to trigger the "hits found" stat card.
    # We can use a simple pattern to generate mock data.
    mock_step.execute.return_value = pd.DataFrame(
        {
            "query": [f"Q{i}" for i in range(n_hits)],
            "target": [f"T{i}" for i in range(n_hits)],
            "database": ["mock_db"] * n_hits,
            "fident": [round(0.95 - i * 0.1, 2) for i in range(n_hits)],
            "bits": [120.0 - i * 10 for i in range(n_hits)],
            "evalue": [1e-10 * (10**i) for i in range(n_hits)],
            "alnlen": [100 + i for i in range(n_hits)],
        }
    )

    # The FoldSeek class itself is mocked to return our mock_step instance when instantiated.
    mock_cls = MagicMock(return_value=mock_step)

    # FoldSeekDatabase enum stub — __members__ is empty so every name
    # stays a plain string (no download attempt).
    mock_db_enum = MagicMock()
    mock_db_enum.__members__ = {}

    # Patch the FoldSeek class and FoldSeekDatabase enum in the compute module where they are imported.
    monkeypatch.setattr(f"{_FOLDSEEK_MODULE}.FoldSeek", mock_cls)
    monkeypatch.setattr(f"{_FOLDSEEK_MODULE}.FoldSeekDatabase", mock_db_enum)

    return mock_step


def test_run_sequence_mode_stat_cards(_mock_foldseek):
    """Sequence-mode run returns stat cards with Mode='Sequence'."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    result = run(_seq_mode_params())

    stat_map = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_map["Mode"] == "Sequence"
    assert int(stat_map["Hits Found"]) == 3


def test_run_dataframe_has_columns_and_data(_mock_foldseek):
    """The dataframe payload must include 'columns' and 'data' lists."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    result = run(_seq_mode_params())
    df_payload = result["dataframe"]

    assert "columns" in df_payload
    assert "data" in df_payload
    assert isinstance(df_payload["columns"], list)
    assert isinstance(df_payload["data"], list)
    assert len(df_payload["data"]) == 3


def test_run_result_is_json_serializable(_mock_foldseek):
    """The entire result dict must be JSON-serializable (backend requirement)."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    result = run(_seq_mode_params())
    serialized = json.dumps(result)
    assert isinstance(serialized, str)


def test_run_params_exclude_hides_structure_content(_mock_foldseek):
    """'structure_content' must always be in _params_exclude to avoid cluttering the UI."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    result = run(_seq_mode_params())
    assert "structure_content" in result["_params_exclude"]


def test_run_empty_results_returns_no_results_message(_mock_foldseek):
    """When FoldSeek returns zero hits, the result must include a no_results_message."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    _mock_foldseek.execute.return_value = pd.DataFrame()

    result = run(_seq_mode_params())

    assert result["dataframe"]["data"] == []
    assert result["dataframe"]["columns"] == []
    assert "no_results_message" in result
    stat_map = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_map["Hits Found"] == "0"


def test_run_structure_mode_stat_cards(_mock_foldseek):
    """Structure-mode run returns stat cards with Mode='Structure'."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    result = run(_structure_mode_params())

    stat_map = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_map["Mode"] == "Structure"


def test_run_raises_on_empty_sequence(_mock_foldseek):
    """run() must raise ValueError when the query sequence is empty."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    with pytest.raises(ValueError, match="sequence"):
        run(_seq_mode_params(sequence=""))


def test_run_raises_on_no_databases(_mock_foldseek):
    """run() must raise ValueError when no databases are provided."""
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    with pytest.raises(ValueError, match="database"):
        run(_seq_mode_params(databases=[]))


# ── FoldSeek integration (requires foldseek binary) ──────────────────────────


@pytest.fixture()
def foldseek_test_db(tmp_path, monkeypatch):
    """Build a tiny FoldSeek database from 1AKI.cif and patch path constants.

    The database is built in **structure mode** (from a CIF file) so
    ProstT5 weights are not required — neither for DB creation nor for
    the subsequent ``easy-search``.

    A dummy ``prostt5-f16.gguf`` file is created to satisfy the
    weight-existence check in ``_ensure_prostt5_weights()`` without
    triggering a network download.

    Returns:
        The database folder name (``"test_lysozyme"``) as a plain string.
        Using a plain string (not a ``FoldSeekDatabase`` enum) ensures
        ``_manage_all_databases`` will **not** attempt to download a
        built-in database — it simply checks that the files exist.
    """
    # 1) Copy the bundled CIF into a temp input directory.
    cif_input = tmp_path / "cif_input"
    cif_input.mkdir()
    shutil.copy2(_CIF_1AKI, cif_input / "1AKI.cif")

    # 2) Build the foldseek database from the CIF file.
    db_dir = tmp_path / "test_lysozyme"
    db_dir.mkdir()
    db_prefix = str(db_dir / "test_lysozyme")
    subprocess.run(
        ["foldseek", "createdb", str(cif_input) + "/", db_prefix],
        check=True,
        capture_output=True,
    )

    # 3) Create dummy ProstT5 weights so _ensure_prostt5_weights() is a no-op.
    fake_weights = tmp_path / "fake_weights"
    fake_weights.mkdir()
    (fake_weights / "prostt5-f16.gguf").touch()

    # 4) Patch the path constants used by compute.run().
    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.sequence_structure_similarity.compute.FOLDSEEK_DB_DIR",
        tmp_path,
    )
    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.sequence_structure_similarity.compute.FOLDSEEK_WEIGHTS_DIR",
        fake_weights,
    )

    return "test_lysozyme"


@_skip_no_foldseek
def test_run_returns_expected_contract(foldseek_test_db):
    """run() with real FoldSeek must return the expected result contract.

    Uses structure mode (CIF query against a CIF-built database) so
    no ProstT5 weights are downloaded.  The query is 1AKI.cif searched
    against a database built from the same file, so at least one
    self-hit is expected.
    """
    from enzyme_tk_app.app.tools.sequence_structure_similarity.compute import run  # noqa: PLC0415

    cif_bytes = _CIF_1AKI.read_bytes()
    b64 = base64.b64encode(cif_bytes).decode()
    data_uri = f"data:chemical/x-cif;base64,{b64}"

    result = run(
        {
            "task_name": "test-foldseek-run",
            "sequence": _SEQ_1AKI,
            "databases": [foldseek_test_db],
            "structure_content": data_uri,
            "structure_filename": "1AKI.cif",
        }
    )

    # ── Top-level keys ────────────────────────────────────────────────
    assert "_stat_cards" in result
    assert "_params_exclude" in result
    assert "dataframe" in result

    # ── Stat cards shape ──────────────────────────────────────────────
    stat_cards = result["_stat_cards"]
    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 3
    for card in stat_cards:
        assert "label" in card
        assert "value" in card

    # Mode must be "Structure" since we supplied a CIF file.
    stat_map = {c["label"]: c["value"] for c in stat_cards}
    assert stat_map["Mode"] == "Structure"

    # ── DataFrame payload ─────────────────────────────────────────────
    df_payload = result["dataframe"]
    assert "columns" in df_payload
    assert "data" in df_payload
    assert isinstance(df_payload["columns"], list)
    assert isinstance(df_payload["data"], list)
    assert len(df_payload["data"]) > 0, "Expected at least one FoldSeek hit (self-match)"

    # ── JSON-serializable (backend requirement) ───────────────────────
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
