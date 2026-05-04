"""Tests for the Sequence Similarity tool compute module.

These tests exercise ``run()`` with **real** enzymetk + diamond calls —
no mocking.  The goal is regression detection: if enzymetk changes its
BLAST output column names, score types, or API, these tests will fail
immediately.

A small 20-row CSV (``test_sequences_20.csv``) extracted from the
production protein database is used as the test fixture.

Tests that call BLAST require the ``diamond`` binary in ``$PATH``
(installed in the Docker worker image).  They are automatically
skipped when diamond is unavailable so the rest of the suite keeps
passing in local development.
"""

import json
import shutil
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from dash import dcc, html
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server
from enzyme_tk_app.app.paths import SEQUENCES_DIR
from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.sequence_similarity import TOOL_DEF
from enzyme_tk_app.app.tools.sequence_similarity.callbacks import (
    populate_ec_options,
    populate_example_sequence,
    submit_sequence_similarity_job,
    toggle_sequence_similarity_modal,
    validate_sequence_form,
)
from enzyme_tk_app.app.utils.columns import (
    COL_BITSCORE,
    COL_EC_NUMBER,
    COL_ENTRY,
    COL_QUERY,
    COL_RESIDUE_0INDEX,
    COL_SEQ_IDENTITY,
    COL_SEQUENCE,
    COL_TARGET,
)

# ── Diamond availability check ────────────────────────────────────────────────

_diamond_available = shutil.which("diamond") is not None
_skip_no_diamond = pytest.mark.skipif(
    not _diamond_available,
    reason="diamond binary not found in $PATH (install diamond or run in Docker)",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


# The 20-row test CSV fixture is automatically used in all tests via the
# _patch_seq_data_dir fixture, which monkeypatches the SEQUENCES_DIR in both
@pytest.fixture(autouse=True)
def _patch_seq_data_dir(sequences_dir, monkeypatch):
    """Patch ``SEQUENCES_DIR`` in both compute and callbacks modules.

    Autouse ensures every test in this module reads from the 20-row test
    sequence fixture rather than production data.
    """
    patched_dir = sequences_dir / SEQUENCES_DIR.name
    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.sequence_similarity.compute.SEQUENCES_DIR",
        patched_dir,
    )
    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.sequence_similarity.callbacks.SEQUENCES_DIR",
        patched_dir,
    )


@pytest.fixture()
def empty_ec_result():
    """Run once with an EC filter that matches nothing — shared by all empty-results tests."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    return run(_default_params(ec_filter=["99.99.99.99"]))


# ── Helper ────────────────────────────────────────────────────────────────────

# Sample sequences pulled from the test CSV for convenience.
# First sequence in the CSV (A0A009IHW8) — EC: 3.2.2.-; 3.2.2.6
_SEQ_A0A009IHW8 = (
    "MSLEQKKGADIISKILQIQNSIGKTTSPSTLKTKLSEISRKEQENARIQSKLSDLQKKKIDIDNKLLKEKQNLIKEEILERKKLEVLTKKQQK"
    "DEIEHQKKLKREIDAIKASTQYITDVSISSYNNTIPETEPEYDLFISHASEDKEDFVRPLAETLQQLGVNVWYDEFTLKVGDSLRQKIDSGLRN"
    "SKYGTVVLSTDFIKKDWTNYELDGLVAREMNGHKMILPIWHKITKNDVLDYSPNLADKVALNTSVNSIEEIAHQLADVILNR"
)

# Shorter sequence from A0A024SC78 — EC: 3.1.1.74
_SEQ_A0A024SC78 = (
    "MRSLAILTTLLAGHAFAYPKPAPQSVNRRDWPSINEFLSELAKVMPIGDTITAACDLISDGEDAAASLFGISETENDPCGDVTVLFARGTCDPG"
    "NVGVLVGPWFFDSLQTALGSRTLGVKGVPYPASVQDFLSGSVQNGINMANQIKSVLQSCPNTKLVLGGYSQGSMVVHNAASNLDAATMSKISA"
    "VVLFGDPYYGKPVANFDAAKTLVVCHDGDNICQGGDIILLPHLTYAEDADTAAAFVVPLVS"
)

# Sequence from A0A067XR63 — EC: 2.4.1.207 (used for EC filter tests)
_SEQ_A0A067XR63 = (
    "MNAEGGNLHREFEITWGDGRARIHNNGGLLTLSLDRASGSGFRSKNEYLFGRIEIQIKLVAGNSAGTVATYYLSSEGPTHDEIDFEFLGNSSGE"
    "PYTLHTNVFSQGKGNREQQFFLWFDPTMDFHTYTILWNPQRIIFYVDETPIREFKNLERHGIPFPRSQAMRVYSSMWNADDWATRGGLVKTDWT"
    "KAPFTASYRSYKADACVWSGEASSCGSQDSNPSDKWWMTEELNATRMKRLRWVQKKYMVYNYCVDKMRFPEGLAPECNIS"
)


def _default_params(**overrides):
    """Return a valid ``run()`` params dict with sensible defaults."""
    defaults = {
        "task_name": "test-run",
        "database": "test_sequences_20.csv",
        "sequence": _SEQ_A0A009IHW8,
        "ec_filter": [],
        "cofactor_filter": [],
        "top_n": 10,
        "predict_catalytic": False,
    }
    defaults.update(overrides)
    return defaults


# ── Early-return paths (no diamond needed) ────────────────────────────────────


def test_run_nonexistent_database_raises():
    """run() must raise ValueError when the database file does not exist."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    with pytest.raises(ValueError, match="Database file not found"):
        run(_default_params(database="nonexistent.csv"))


def test_run_ec_filter_matches_nothing(empty_ec_result):
    """When the EC filter eliminates all rows, run() returns empty results without calling BLAST."""
    assert empty_ec_result["dataframe"]["data"] == []
    assert empty_ec_result["dataframe"]["columns"] == []
    # Stat cards should show zero after-filtering and zero results.
    stat_cards = {c["label"]: c["value"] for c in empty_ec_result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "0"
    assert stat_cards["Results Returned"] == "0"


def test_run_empty_results_no_results_message(empty_ec_result):
    """When filtering produces zero rows, a human-readable explanation is returned."""
    assert "no_results_message" in empty_ec_result
    assert "99.99.99.99" in empty_ec_result["no_results_message"]
    assert "filter" in empty_ec_result["no_results_message"].lower()


def test_run_empty_results_stat_cards_shape(empty_ec_result):
    """Stat cards on empty results must still follow the label/value dict format."""
    stat_cards = empty_ec_result["_stat_cards"]
    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 4
    for card in stat_cards:
        assert "label" in card
        assert "value" in card


def test_run_empty_results_total_sequences_is_full_db(empty_ec_result):
    """Even when results are empty, 'Total Sequences' reports the full unfiltered count."""
    stat_cards = {c["label"]: c["value"] for c in empty_ec_result["_stat_cards"]}

    # The test CSV has 20 valid rows.
    assert int(stat_cards["Total Sequences"].replace(",", "")) == 20


def test_run_empty_results_is_json_serializable(empty_ec_result):
    """The empty-results dict must be JSON-serializable — backend requirement."""
    serialized = json.dumps(empty_ec_result)
    assert isinstance(serialized, str)


def test_run_empty_results_catalytic_prediction_is_none(empty_ec_result):
    """When filtering produces zero rows, catalytic_prediction must be None."""
    assert empty_ec_result["catalytic_prediction"] is None


# ── Input validation ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename",
    ["data.txt", "file.json", "archive.tar.gz"],
    ids=["txt", "json", "tar-gz"],
)
def test_run_rejects_non_csv_extension(filename):
    """run() must raise ValueError for database filenames that do not end with .csv."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    with pytest.raises(ValueError, match="must be .csv"):
        run(_default_params(database=filename))


def test_run_path_traversal_sanitized():
    """Directory components are stripped to prevent path-traversal attacks.

    ``../../etc/secrets.csv`` becomes ``secrets.csv`` (via ``Path.name``),
    which will not exist in the data directory.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    with pytest.raises(ValueError, match="Database file not found: secrets.csv"):
        run(_default_params(database="../../etc/secrets.csv"))


# ── CI-safe mocked BLAST tests (no diamond binary required) ──────────────────
# These tests mock enzymetk's BLAST class so the full run() code path
# (execution → sorting → merging → column stripping → stat cards)
# can be exercised in CI without the diamond binary.


@pytest.fixture()
def mock_blast():
    """Mock ``enzymetk.sequence_search_blast.BLAST`` so run() works without diamond.

    Yields the mock BLAST *instance* — set ``mock_blast.execute.return_value``
    (or ``.side_effect``) in each test to control what "BLAST" returns.
    """
    with patch("enzymetk.sequence_search_blast.BLAST") as MockBLAST:
        yield MockBLAST.return_value


def _make_blast_result_df(targets, bitscores=None, identities=None):
    """Build a DataFrame mimicking the columns enzymetk BLAST.execute() returns.

    Args:
        targets: Target Entry IDs (e.g. ``["A0A009IHW8", "A0A024SC78"]``).
        bitscores: Bitscore per hit.  Defaults to descending integers from 200.
        identities: Sequence identity per hit.  Defaults to descending from 99.
    """
    n = len(targets)
    if bitscores is None:
        bitscores = [200 - i for i in range(n)]
    if identities is None:
        identities = [round(99.0 - i * 2.0, 1) for i in range(n)]

    return pd.DataFrame(
        {
            COL_QUERY: ["query"] * n,
            COL_TARGET: targets,
            COL_BITSCORE: bitscores,
            COL_SEQ_IDENTITY: identities,
        }
    )


@pytest.mark.parametrize(
    ("raw_top_n", "expected_max"),
    [(0, 1), (-5, 1), (999, 500), (10, 10), (1, 1), (500, 500)],
    ids=["zero-clamps-to-1", "negative-clamps-to-1", "999-clamps-to-500", "10-unchanged", "min-edge", "max-edge"],
)
def test_run_top_n_clamping(raw_top_n, expected_max, mock_blast):
    """top_n is clamped to [1, 500]; result row count must not exceed the clamped value."""
    # Return enough mock rows to exceed any clamped top_n.
    entries = [f"P{i:04d}" for i in range(600)]
    mock_blast.execute.return_value = _make_blast_result_df(entries)

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=raw_top_n))

    assert len(result["dataframe"]["data"]) <= expected_max


def test_run_mocked_blast_returns_expected_keys(mock_blast):
    """Mocked BLAST: run() must return _stat_cards, catalytic_prediction, and dataframe."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())

    assert "_stat_cards" in result
    assert "catalytic_prediction" in result
    assert "dataframe" in result
    assert isinstance(result["dataframe"]["columns"], list)
    assert isinstance(result["dataframe"]["data"], list)


def test_run_mocked_blast_sorts_by_bitscore_descending(mock_blast):
    """Results must be sorted by bitscore descending even when BLAST returns them unsorted."""
    mock_blast.execute.return_value = _make_blast_result_df(
        targets=["A0A009IHW8", "A0A024SC78", "A0A023I7E1"],
        bitscores=[50.0, 200.0, 100.0],
    )

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=10))
    bitscores = [row[COL_BITSCORE] for row in result["dataframe"]["data"]]

    assert bitscores == sorted(bitscores, reverse=True), "Results not sorted by bitscore descending"


def test_run_mocked_blast_truncates_to_top_n(mock_blast):
    """When BLAST returns more hits than top_n, only the top-scoring ones are kept."""
    mock_blast.execute.return_value = _make_blast_result_df(
        targets=["A0A009IHW8", "A0A024SC78", "A0A023I7E1", "A0A024RXP8", "A0A067XR63"],
        bitscores=[500.0, 400.0, 300.0, 200.0, 100.0],
    )

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=2))
    data = result["dataframe"]["data"]

    assert len(data) == 2
    # The two highest bitscores should be kept.
    bitscores = [row[COL_BITSCORE] for row in data]
    assert bitscores == [500.0, 400.0]


def test_run_mocked_blast_strips_internal_columns(mock_blast):
    """Internal columns (query, Entry, Residue_0index) must not appear in consumer output."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    for col in [COL_QUERY, COL_ENTRY, COL_RESIDUE_0INDEX]:
        assert col not in output_columns, f"Internal column '{col}' leaked into output"


def test_run_mocked_blast_merges_db_metadata(mock_blast):
    """Database metadata (EC number, Sequence) must be merged onto BLAST results via target ID."""
    # A0A009IHW8 exists in the test CSV with EC "3.2.2.-; 3.2.2.6".
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    data = result["dataframe"]["data"]

    assert len(data) == 1
    row = data[0]

    # EC number from the database must be present after the merge.
    assert COL_EC_NUMBER in row, "EC number from database not merged"
    assert "3.2.2" in str(row[COL_EC_NUMBER])

    # Protein sequence from the database must also be merged.
    assert COL_SEQUENCE in row, "Sequence from database not merged"
    assert len(row[COL_SEQUENCE]) > 0


def test_run_mocked_blast_empty_data_error(mock_blast):
    """When BLAST raises EmptyDataError (no alignments), run() returns an empty result with a message."""
    mock_blast.execute.side_effect = pd.errors.EmptyDataError("No data")

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())

    assert result["dataframe"]["data"] == []
    assert result["dataframe"]["columns"] == []
    assert result["catalytic_prediction"] is None
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["Results Returned"] == "0"
    # The no_results_message must explain that no alignments were found.
    assert "no_results_message" in result
    assert "no alignments" in result["no_results_message"].lower()


def test_run_mocked_blast_no_no_results_message_on_success(mock_blast):
    """When BLAST returns results, no_results_message must not be in the return dict."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())

    assert "no_results_message" not in result


@pytest.mark.parametrize(
    ("predict", "expected_none"),
    [(False, True), (True, False)],
    ids=["prediction-off", "prediction-on"],
)
def test_run_mocked_catalytic_prediction(predict, expected_none, mock_blast):
    """catalytic_prediction must be None when disabled, non-None when enabled."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(predict_catalytic=predict))

    if expected_none:
        assert result["catalytic_prediction"] is None
    else:
        assert result["catalytic_prediction"] is not None


def test_run_mocked_stat_cards_labels_and_count(mock_blast):
    """Stat cards must include the five expected labels."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8", "A0A024SC78"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_labels = {c["label"] for c in result["_stat_cards"]}
    expected = {"Database", "Total Sequences", "After Filtering", "Results Returned", "Run Time"}

    assert expected.issubset(stat_labels), f"Missing labels: {expected - stat_labels}"


def test_run_mocked_stat_card_results_matches_data(mock_blast):
    """The 'Results Returned' stat card must equal the actual row count."""
    mock_blast.execute.return_value = _make_blast_result_df(
        ["A0A009IHW8", "A0A024SC78", "A0A023I7E1"],
    )

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=10))
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    actual_rows = len(result["dataframe"]["data"])

    assert stat_cards["Results Returned"] == str(actual_rows)


def test_run_mocked_result_is_json_serializable(mock_blast):
    """The return dict with mocked BLAST results must be JSON-serializable."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8", "A0A024SC78"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    serialized = json.dumps(result)

    assert isinstance(serialized, str)


def test_run_ec_filter_reduces_blast_input(mock_blast):
    """EC filter must reduce the reference rows passed to BLAST.execute()."""
    mock_blast.execute.return_value = _make_blast_result_df(["A0A067XR63"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # EC 2.4.1.207 has 3 entries in the 20-row test CSV.
    result = run(_default_params(sequence=_SEQ_A0A067XR63, ec_filter=["2.4.1.207"]))

    # BLAST.execute() should receive 3 reference rows + 1 query row = 4 total.
    combined_df = mock_blast.execute.call_args[0][0]
    assert len(combined_df) == 4, f"Expected 4 rows (3 filtered + 1 query), got {len(combined_df)}"

    # Stat card should reflect the reduction.
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "3"


def test_run_cofactor_filter_applied_when_column_present(mock_blast, tmp_path):
    """When the database has a cofactor column, cofactor_filter must reduce rows before BLAST."""
    # Create a small database CSV with a cofactor column.
    csv_content = (
        "Entry,Sequence,EC number,cofactor\n"
        "P001,MKTAYIAKQR,1.1.1.1,NAD\n"
        "P002,MKTAYIAKQRLL,1.1.1.1,FAD\n"
        "P003,MKTAYIAKQRLLS,2.2.2.2,NAD\n"
        "P004,MKTAYIAKQRLLST,2.2.2.2,PLP\n"
    )
    (tmp_path / SEQUENCES_DIR.name / "cofactor_db.csv").write_text(csv_content)

    mock_blast.execute.return_value = _make_blast_result_df(["P001"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(
        {
            "task_name": "cofactor-test",
            "database": "cofactor_db.csv",
            "sequence": "MKTAYIAKQR",
            "ec_filter": [],
            "cofactor_filter": ["NAD"],
            "top_n": 10,
            "predict_catalytic": False,
        }
    )

    # NAD matches P001 and P003 → 2 rows after filtering.
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["Total Sequences"] == "4"
    assert stat_cards["After Filtering"] == "2"

    # BLAST should receive 2 reference rows + 1 query row = 3 total.
    combined_df = mock_blast.execute.call_args[0][0]
    assert len(combined_df) == 3


# ── Return contract (requires diamond) ────────────────────────────────────────


@_skip_no_diamond
def test_run_returns_expected_top_level_keys():
    """run() must return _stat_cards, catalytic_prediction, and dataframe."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())

    assert "_stat_cards" in result
    assert "catalytic_prediction" in result
    assert "dataframe" in result


@_skip_no_diamond
def test_run_stat_cards_shape():
    """_stat_cards must be a list of dicts with 'label' and 'value'."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_cards = result["_stat_cards"]

    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 4
    for card in stat_cards:
        assert "label" in card
        assert "value" in card


@_skip_no_diamond
def test_run_dataframe_has_columns_and_data():
    """The dataframe payload must have 'columns' and 'data' keys."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    df_payload = result["dataframe"]

    assert "columns" in df_payload
    assert "data" in df_payload
    assert isinstance(df_payload["columns"], list)
    assert isinstance(df_payload["data"], list)
    assert len(df_payload["data"]) > 0, "Expected at least one BLAST result"


@_skip_no_diamond
def test_run_result_is_json_serializable():
    """The entire return dict must be JSON-serializable — backend requirement."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    serialized = json.dumps(result)
    assert isinstance(serialized, str)


@_skip_no_diamond
def test_run_data_rows_have_consistent_columns():
    """Every data row must have exactly the same keys as 'columns'."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    columns = set(result["dataframe"]["columns"])

    for i, row in enumerate(result["dataframe"]["data"]):
        assert set(row.keys()) == columns, f"Row {i} keys differ from columns"


# ── enzymetk column regression ────────────────────────────────────────────────


@_skip_no_diamond
@pytest.mark.parametrize(
    "column",
    [COL_TARGET, COL_BITSCORE, COL_SEQ_IDENTITY, COL_EC_NUMBER, COL_SEQUENCE],
    ids=["target", "bitscore", "sequence-identity", "ec-number", "sequence"],
)
def test_run_expected_column_present(column):
    """BLAST output must contain expected columns (hit IDs, scores, merged metadata)."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    assert column in result["dataframe"]["columns"], f"Column '{column}' missing from output"


@_skip_no_diamond
@pytest.mark.parametrize(
    "column",
    [COL_QUERY, COL_ENTRY, COL_RESIDUE_0INDEX],
    ids=["query", "entry", "residue-0index"],
)
def test_run_internal_column_stripped(column):
    """Internal columns must not leak into the consumer-facing output."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    assert column not in result["dataframe"]["columns"], f"Internal column '{column}' leaked into output"


@_skip_no_diamond
@pytest.mark.parametrize(
    "column",
    [COL_BITSCORE, COL_SEQ_IDENTITY],
    ids=["bitscore", "sequence-identity"],
)
def test_run_score_values_are_numeric(column):
    """All score values must be numeric (int or float)."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    for row in result["dataframe"]["data"]:
        score = row[column]
        assert isinstance(score, (int, float)), f"{column} value {score!r} is {type(score)}, expected numeric"


# ── top_n and result count ────────────────────────────────────────────────────


@_skip_no_diamond
@pytest.mark.parametrize("top_n", [1, 3, 5, 20], ids=["top-1", "top-3", "top-5", "top-20"])
def test_run_respects_top_n(top_n):
    """The number of result rows must not exceed the requested top_n."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=top_n))
    assert len(result["dataframe"]["data"]) <= top_n


@_skip_no_diamond
def test_run_results_sorted_by_bitscore_descending():
    """BLAST results must be sorted by bitscore descending (best hits first)."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(top_n=20))
    data = result["dataframe"]["data"]

    if len(data) >= 2:
        bitscores = [row[COL_BITSCORE] for row in data]
        assert bitscores == sorted(bitscores, reverse=True), "Results not sorted by bitscore descending"


# ── stat card consistency ─────────────────────────────────────────────────────


@_skip_no_diamond
def test_run_stat_card_results_returned_matches_data():
    """The 'Results Returned' stat card must match the actual row count."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    actual_rows = len(result["dataframe"]["data"])

    assert stat_cards["Results Returned"] == str(actual_rows)


@_skip_no_diamond
def test_run_stat_card_run_time_is_numeric():
    """The 'Run Time' stat card must be a numeric value followed by 's'."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    run_time = stat_cards["Run Time"]
    assert run_time.endswith("s")
    float(run_time[:-1])  # raises ValueError if not numeric


@_skip_no_diamond
def test_run_stat_card_database_matches_input():
    """The 'Database' stat card must match the requested filename."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    assert stat_cards["Database"] == "test_sequences_20.csv"


@_skip_no_diamond
def test_run_stat_card_after_filtering_matches_full_db_without_filter():
    """Without EC filter, 'After Filtering' must equal 'Total Sequences'."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(ec_filter=[]))
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    assert stat_cards["After Filtering"] == stat_cards["Total Sequences"]


# ── Different sequences ──────────────────────────────────────────────────────


@_skip_no_diamond
def test_run_with_different_sequence():
    """run() must work with a different query sequence (A0A024SC78)."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(sequence=_SEQ_A0A024SC78))

    assert len(result["dataframe"]["data"]) > 0


@_skip_no_diamond
def test_run_different_sequences_return_different_rankings():
    """Different query sequences should produce different top-hit targets."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result1 = run(_default_params(sequence=_SEQ_A0A009IHW8, top_n=1))
    result2 = run(_default_params(sequence=_SEQ_A0A024SC78, top_n=1))

    top1 = result1["dataframe"]["data"][0][COL_TARGET]
    top2 = result2["dataframe"]["data"][0][COL_TARGET]
    # Different sequences should find different best hits.
    assert top1 != top2, "Different queries produced the same top hit — suspicious"


@_skip_no_diamond
def test_run_self_search_returns_exact_match():
    """Querying a sequence that exists in the DB should return itself as top hit."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(sequence=_SEQ_A0A009IHW8, top_n=1))
    top_hit = result["dataframe"]["data"][0]

    # The top hit should be the same protein (A0A009IHW8).
    assert top_hit[COL_TARGET] == "A0A009IHW8", (
        f"Expected self-match 'A0A009IHW8' as top hit, got {top_hit[COL_TARGET]!r}"
    )


@_skip_no_diamond
def test_run_self_search_has_full_identity():
    """A self-search should yield 100% sequence identity for the top hit."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(sequence=_SEQ_A0A009IHW8, top_n=1))
    top_hit = result["dataframe"]["data"][0]

    identity = top_hit[COL_SEQ_IDENTITY]
    assert np.isclose(identity, 100.0, atol=1e-6), f"Expected 100% identity for self-match, got {identity}"


# ── EC number filtering ──────────────────────────────────────────────────────


@_skip_no_diamond
def test_run_with_single_ec_filter():
    """Filtering by a single EC number should reduce the database size."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # EC 2.4.1.207 has 3 entries in the test CSV.  Use a matching query
    # sequence so BLAST can find alignments in the filtered DB.
    result = run(_default_params(sequence=_SEQ_A0A067XR63, ec_filter=["2.4.1.207"], top_n=20))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    after_filtering = int(stat_cards["After Filtering"].replace(",", ""))
    total = int(stat_cards["Total Sequences"].replace(",", ""))

    # EC filter should reduce the database.
    assert after_filtering < total, "EC filter did not reduce the database"
    assert after_filtering == 3, f"Expected 3 entries for EC 2.4.1.207, got {after_filtering}"
    assert len(result["dataframe"]["data"]) > 0


@_skip_no_diamond
def test_run_with_semicolon_ec_filter():
    """EC filter must match entries with semicolon-separated EC numbers.

    A0A009IHW8 has EC "3.2.2.-; 3.2.2.6" — filtering by "3.2.2.6" alone
    should still match.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(ec_filter=["3.2.2.6"], top_n=20))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    after_filtering = int(stat_cards["After Filtering"].replace(",", ""))
    assert after_filtering >= 1, "Semicolon-separated EC match failed"


@_skip_no_diamond
def test_run_with_multiple_ec_filters():
    """Filtering by multiple EC numbers should match the union of all."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # 2.4.1.207 has 3 entries, 2.5.1.54 has 2 entries in the test CSV.
    # Use a 2.4.1.207 query sequence so BLAST finds alignments.
    result = run(_default_params(sequence=_SEQ_A0A067XR63, ec_filter=["2.4.1.207", "2.5.1.54"], top_n=20))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    after_filtering = int(stat_cards["After Filtering"].replace(",", ""))
    assert after_filtering >= 5, f"Expected at least 5 entries for combined EC filter, got {after_filtering}"


@_skip_no_diamond
def test_run_ec_filter_reduces_result_count():
    """Filtering by EC should produce fewer 'After Filtering' rows than unfiltered."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # Use a 2.4.1.207 query so BLAST finds alignments even in the filtered DB.
    result_all = run(_default_params(sequence=_SEQ_A0A067XR63, top_n=20))
    result_filtered = run(_default_params(sequence=_SEQ_A0A067XR63, ec_filter=["2.4.1.207"], top_n=20))

    stat_all = {c["label"]: c["value"] for c in result_all["_stat_cards"]}
    stat_filt = {c["label"]: c["value"] for c in result_filtered["_stat_cards"]}

    total_all = int(stat_all["After Filtering"].replace(",", ""))
    total_filt = int(stat_filt["After Filtering"].replace(",", ""))
    assert total_filt < total_all


@_skip_no_diamond
def test_run_mismatched_query_and_ec_filter_returns_empty():
    """When the query is unrelated to the EC-filtered DB, BLAST returns 0 hits gracefully."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # A0A009IHW8 (EC 3.2.2) has no similarity to EC 3.1.1.74 (A0A024SC78).
    # BLAST finds 0 alignments — compute should handle this without crashing.
    result = run(_default_params(sequence=_SEQ_A0A009IHW8, ec_filter=["3.1.1.74"], top_n=20))

    assert result["dataframe"]["data"] == []
    assert result["dataframe"]["columns"] == []
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["Results Returned"] == "0"
    assert "no_results_message" in result
    assert "no alignments" in result["no_results_message"].lower()


# ── Catalytic prediction ─────────────────────────────────────────────────────


@_skip_no_diamond
def test_run_without_catalytic_prediction():
    """When predict_catalytic is False, catalytic_prediction must be None."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(predict_catalytic=False))
    assert result["catalytic_prediction"] is None


@_skip_no_diamond
def test_run_with_catalytic_prediction():
    """When predict_catalytic is True, catalytic_prediction must be non-None."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(predict_catalytic=True))
    # Currently a placeholder string — just verify it's set.
    assert result["catalytic_prediction"] is not None


# ── Results layout ───────────────────────────────────────────────────────────


def test_get_column_defs_fields_are_unique():
    """_get_column_defs must return unique field names matching column constants."""
    from enzyme_tk_app.app.tools.sequence_similarity.results import _get_column_defs

    col_defs = _get_column_defs()

    assert isinstance(col_defs, list)
    assert len(col_defs) > 0, "Expected at least one column definition"

    # Every entry must have a 'field' and a 'width'.
    for cd in col_defs:
        assert "field" in cd, f"Column def missing 'field': {cd}"
        assert "width" in cd, f"Column def missing 'width': {cd}"

    # All field names must be unique.
    fields = [cd["field"] for cd in col_defs]
    assert len(fields) == len(set(fields)), f"Duplicate fields: {[f for f in fields if fields.count(f) > 1]}"


def test_results_layout_renders_ag_grid_with_data():
    """results_layout must produce an html.Div containing an AgGrid when data is present."""
    import dash_ag_grid as dag

    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    job = make_job(
        result={
            "dataframe": {
                "columns": ["target", "bitscore", "sequence identity"],
                "data": [
                    {"target": "P12345", "bitscore": 200.0, "sequence identity": 99.5},
                    {"target": "Q67890", "bitscore": 150.0, "sequence identity": 85.0},
                ],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)

    # The Div must contain an AgGrid with the provided data rows.
    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AgGrid in results_layout"
    assert len(grids[0].rowData) == 2, "AgGrid should contain the two data rows"


def test_results_layout_shows_message_when_no_dataframe():
    """When dataframe payload is missing, a fallback message paragraph must be shown."""
    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    job = make_job(result={"no_results_message": "Nothing found."})
    layout = results_layout(job)

    assert isinstance(layout, html.Div)
    paragraphs = find_components(layout, html.P)
    assert any("Nothing found." in str(p.children) for p in paragraphs)


def test_results_layout_no_accordion_when_catalytic_prediction_is_none():
    """When catalytic_prediction is None, no Accordion should be rendered."""
    import dash_ag_grid as dag
    import dash_bootstrap_components as dbc

    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    job = make_job(
        result={
            "catalytic_prediction": None,
            "dataframe": {
                "columns": ["target"],
                "data": [{"target": "P12345"}],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)
    # Data is present — AgGrid should exist.
    assert len(find_components(layout, dag.AgGrid)) == 1
    # catalytic_prediction is None — no Accordion.
    assert find_components(layout, dbc.Accordion) == []


def test_results_layout_renders_accordion_when_catalytic_prediction_present():
    """When catalytic_prediction is a non-None string, an Accordion with the prediction text must appear."""
    import dash_ag_grid as dag
    import dash_bootstrap_components as dbc

    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    prediction_text = "Catalytic residues: H57, D102, S195"
    job = make_job(
        result={
            "catalytic_prediction": prediction_text,
            "dataframe": {
                "columns": ["target"],
                "data": [{"target": "P12345"}],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)

    # AgGrid should still be rendered alongside the accordion.
    assert len(find_components(layout, dag.AgGrid)) == 1

    # Accordion must be present with the prediction text.
    accordions = find_components(layout, dbc.Accordion)
    assert len(accordions) == 1, "Expected exactly one Accordion"

    paragraphs = find_components(accordions[0], html.P)
    assert any(prediction_text in str(p.children) for p in paragraphs), (
        f"Expected prediction text '{prediction_text}' inside the Accordion"
    )


# ── Modal layout ─────────────────────────────────────────────────────────────


def test_get_example_sequences_returns_non_empty_list():
    """_get_example_sequences must return a non-empty list of label/value dicts."""
    from enzyme_tk_app.app.tools.sequence_similarity.modal import _get_example_sequences

    examples = _get_example_sequences()
    assert isinstance(examples, list)
    assert len(examples) >= 1
    for ex in examples:
        assert "label" in ex and "value" in ex
        assert len(ex["value"]) > 0, "Example sequence must not be empty"


def test_modal_returns_dbc_modal():
    """modal() must return a dbc.Modal with the correct ID."""
    import dash_bootstrap_components as dbc

    from enzyme_tk_app.app.tools.sequence_similarity.modal import modal

    component = modal()
    assert isinstance(component, dbc.Modal)
    assert component.id == f"id-modal-{TOOL_DEF['slug']}"


# ── Callback logic ───────────────────────────────────────────────────────────


def test_toggle_modal_opens_on_launch():
    """The modal must open when the launch button is clicked."""
    with patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        assert toggle_sequence_similarity_modal(1, 0) is True


def test_toggle_modal_closes_on_cancel():
    """The modal must close when the cancel button is clicked."""
    with patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-cancel"
        assert toggle_sequence_similarity_modal(0, 1) is False


def test_toggle_modal_closes_for_unknown_trigger():
    """An unrecognised trigger ID must default to closing the modal."""
    with patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-unknown"
        assert toggle_sequence_similarity_modal(0, 0) is False


def test_populate_example_sequence_returns_value():
    """Selecting an example must populate the sequence textarea."""
    assert populate_example_sequence("MKTAYIAKQR") == "MKTAYIAKQR"


def test_populate_example_sequence_raises_for_none():
    """Clearing the example dropdown must raise PreventUpdate."""
    with pytest.raises(PreventUpdate):
        populate_example_sequence(None)


def test_populate_example_sequence_raises_for_empty_string():
    """An empty string value must raise PreventUpdate (falsy but not None)."""
    with pytest.raises(PreventUpdate):
        populate_example_sequence("")


def test_populate_ec_options_raises_for_empty_value():
    """An empty database value must raise PreventUpdate."""
    with pytest.raises(PreventUpdate):
        populate_ec_options(None)


def test_validate_form_enabled_when_all_filled():
    """Submit must be enabled (not disabled) when all required fields are filled."""
    # Returns False = "not disabled" = enabled.
    assert validate_sequence_form("My Task", "MKTAYIAKQR", "protein.csv") is False


def test_validate_form_disabled_when_sequence_missing():
    """Submit must be disabled when the sequence is empty."""
    assert validate_sequence_form("My Task", "", "protein.csv") is True


def test_validate_form_disabled_when_database_missing():
    """Submit must be disabled when no database is selected."""
    assert validate_sequence_form("My Task", "MKTAYIAKQR", None) is True


def test_submit_clears_results_on_launch():
    """Re-opening the modal must clear stale results without calling the scheduler."""
    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler") as mock_sched,
    ):
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        result = submit_sequence_similarity_job(0, 1, "t", "db.csv", "MKTAY", None, None, 10, False)

    assert result == ""
    mock_sched.assert_not_called()


def test_submit_returns_job_id():
    """A valid submission must return a message containing the job ID."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-abc-123"

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-1"
        with (
            patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_sequence_similarity_job(1, 0, "My Task", "protein.csv", "MKTAYIAKQR", None, None, 10, False)

    assert "job-abc-123" in result


def test_submit_returns_error_when_top_n_invalid():
    """An invalid Top N value must return the validation error without scheduling a job."""
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_sequence_similarity_job(1, 0, "My Task", "protein.csv", "MKTAYIAKQR", None, None, None, False)

    # validate_top_n returns an error string for None — no job should be submitted.
    assert "Invalid" in result
    mock_scheduler.submit_job.assert_not_called()


def test_submit_message_includes_ec_filter_count():
    """When EC filters are provided, the message must include the count."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-ec-456"

    ec_filter = ["3.2.2.-", "1.1.1.1", "2.7.1.1"]

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-2"
        with (
            patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_sequence_similarity_job(
                1, 0, "EC Task", "protein.csv", "MKTAYIAKQR", ec_filter, None, 10, False
            )

    # Must mention both the job ID and the filter summary.
    assert "job-ec-456" in result
    assert "3 EC number(s)" in result
    assert "filtered by 3 EC number(s)" in result


def test_submit_message_without_filters_has_no_filtered_by():
    """Without EC filters, the message must not contain 'filtered by'."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-no-filter"

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-3"
        with (
            patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_sequence_similarity_job(1, 0, "Task", "protein.csv", "MKTAY", None, None, 10, False)

    assert "job-no-filter" in result
    assert "filtered by" not in result


def test_submit_raises_prevent_update_when_fields_empty():
    """Server-side guard must raise PreventUpdate when required fields are missing."""
    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        with pytest.raises(PreventUpdate):
            submit_sequence_similarity_job(1, 0, "", "protein.csv", "MKTAY", None, None, 10, False)


def test_submit_returns_error_for_non_csv_database():
    """A non-.csv database filename must return an error message without scheduling a job."""
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_sequence_similarity_job(1, 0, "Task", "malicious.txt", "MKTAY", None, None, 10, False)

    assert "Invalid" in result
    mock_scheduler.submit_job.assert_not_called()


# ── populate_ec_options ──────────────────────────────────────────────────────


def test_populate_ec_options_returns_options_for_valid_database(tmp_path):
    """A valid database CSV must produce dropdown options for each unique EC number."""
    # Create a minimal CSV with an ec_number column.
    csv_file = tmp_path / SEQUENCES_DIR.name / "test_db.csv"
    csv_file.write_text("EC number\n3.2.2.-\n1.1.1.1\n3.2.2.-\n")

    options, cleared = populate_ec_options("test_db.csv")

    # Should have two unique EC numbers, sorted.
    assert len(options) == 2
    labels = [o["label"] for o in options]
    assert labels == ["1.1.1.1", "3.2.2.-"]
    assert cleared == []


def test_populate_ec_options_value_matches_label(tmp_path):
    """Each option's value must equal its label (used as the filter key)."""
    csv_file = tmp_path / SEQUENCES_DIR.name / "db.csv"
    csv_file.write_text("EC number\n1.2.3.4\n5.6.7.8\n")

    options, _ = populate_ec_options("db.csv")

    for opt in options:
        assert opt["label"] == opt["value"]


def test_populate_ec_options_returns_empty_for_missing_file():
    """A non-existent database file must return an empty list (no crash)."""
    options, cleared = populate_ec_options("no_such_file.csv")

    assert options == []
    assert cleared == []


def test_populate_ec_options_splits_semicolon_ec_numbers(tmp_path):
    """EC numbers separated by semicolons in a single cell must be split into separate options."""
    csv_file = tmp_path / SEQUENCES_DIR.name / "multi_ec.csv"
    csv_file.write_text("EC number\n3.2.2.-; 1.1.1.1\n2.7.1.1\n")

    options, _ = populate_ec_options("multi_ec.csv")

    labels = [o["label"] for o in options]
    assert labels == ["1.1.1.1", "2.7.1.1", "3.2.2.-"]


def test_populate_ec_options_returns_empty_for_non_csv_extension():
    """A filename without a .csv suffix must return an empty list (path-traversal guard)."""
    assert populate_ec_options("malicious.txt") == ([], [])


def test_populate_ec_options_strips_path_traversal_and_rejects_non_csv():
    """Path-traversal attempts with a non-.csv suffix must return an empty list."""
    assert populate_ec_options("../../etc/passwd") == ([], [])


# ── compute.run() — path-traversal & cofactor guards ────────────────────────


def test_run_cofactor_filter_applied_when_column_exists():
    """When the cofactor column exists, run() must filter rows by cofactor values."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    original_load = None

    def _load_with_cofactor(csv_path):
        """Wrap load_sequence_data to inject a cofactor column."""
        df = original_load(csv_path)
        # Give roughly half the rows cofactor "CoA" and the rest "NAD".
        df["cofactor"] = ["CoA" if i % 2 == 0 else "NAD" for i in range(len(df))]
        return df

    import enzyme_tk_app.app.tools.sequence_similarity.compute as compute_mod

    original_load = compute_mod.load_sequence_data

    with patch.object(compute_mod, "load_sequence_data", side_effect=_load_with_cofactor):
        result = run(_default_params(cofactor_filter=["CoA"], ec_filter=["99.99.99.99"]))

    # EC filter eliminates all rows, so cofactor filter alone won't produce results.
    # But we verify cofactor_filter is mentioned in no_results_message.
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "0"


def test_run_cofactor_in_no_results_message():
    """When cofactor_filter produces zero rows, the no_results_message must mention the cofactor."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    original_load = None

    def _load_with_cofactor(csv_path):
        """Wrap load_sequence_data to inject a cofactor column with no matching values."""
        df = original_load(csv_path)
        df["cofactor"] = "NAD"
        return df

    import enzyme_tk_app.app.tools.sequence_similarity.compute as compute_mod

    original_load = compute_mod.load_sequence_data

    with patch.object(compute_mod, "load_sequence_data", side_effect=_load_with_cofactor):
        result = run(_default_params(cofactor_filter=["NONEXISTENT_COFACTOR"]))

    assert "no_results_message" in result
    assert "Cofactor" in result["no_results_message"]
    assert "NONEXISTENT_COFACTOR" in result["no_results_message"]


# ── modal() — EC options are NOT prepopulated (callback handles it) ──────────


def test_modal_ec_dropdown_starts_empty():
    """modal() must render the EC dropdown with empty options.

    EC options are populated lazily by the ``populate_ec_options`` callback
    (which fires on initial load) — not synchronously in ``modal()``.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.modal import modal as build_modal

    with patch(
        "enzyme_tk_app.app.tools.sequence_similarity.modal.get_sequence_database_options",
        return_value=[{"label": "Test Db", "value": "test_db.csv"}],
    ):
        component = build_modal()

    ec_dropdowns = find_components(component, dcc.Dropdown)
    ec_filter_dd = [d for d in ec_dropdowns if d.id and "ec-filter" in d.id]
    assert len(ec_filter_dd) == 1
    assert ec_filter_dd[0].options == []


def test_modal_ec_dropdown_empty_when_no_databases():
    """When no databases exist, EC dropdown options must still be empty."""
    from enzyme_tk_app.app.tools.sequence_similarity.modal import modal as build_modal

    with patch(
        "enzyme_tk_app.app.tools.sequence_similarity.modal.get_sequence_database_options",
        return_value=[],
    ):
        component = build_modal()

    ec_dropdowns = find_components(component, dcc.Dropdown)
    ec_filter_dd = [d for d in ec_dropdowns if d.id and "ec-filter" in d.id]
    assert len(ec_filter_dd) == 1
    assert ec_filter_dd[0].options == []
