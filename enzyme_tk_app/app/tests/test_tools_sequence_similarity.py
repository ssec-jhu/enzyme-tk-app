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
from dash import dcc, html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server
from enzyme_tk_app.app.paths import SEQUENCES_DIR
from enzyme_tk_app.app.tests.conftest import (
    TEST_SEQUENCES_CSV,
    find_components,
    get_text,
    make_job,
    submission_error_text,
    submitted_job_id,
)
from enzyme_tk_app.app.tools.sequence_similarity import TOOL_DEF
from enzyme_tk_app.app.tools.sequence_similarity.callbacks import (
    populate_cofactor_options,
    populate_ec_options,
    populate_example_sequence,
    submit_sequence_similarity_job,
    toggle_sequence_similarity_modal,
    validate_sequence_form,
)
from enzyme_tk_app.app.tools.sequence_similarity.modal import _get_example_sequences
from enzyme_tk_app.app.utils.columns import (
    COL_BITSCORE,
    COL_COFACTOR,
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
# _patch_seq_data_dir fixture, which monkeypatches SEQUENCES_DIR everywhere.
@pytest.fixture(autouse=True)
def _patch_seq_data_dir(sequences_dir, monkeypatch):
    """Patch ``SEQUENCES_DIR`` in compute, callbacks, and data_loading.

    Autouse ensures every test in this module reads from the 20-row test
    sequence fixture rather than production data.  ``data_loading`` needs its
    own copy patched because that is where database discovery and the
    compliance check now live — ``scan_sequence_databases`` reads it, and the
    dropdown options that ``validate_db_names`` checks against come from there.
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
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", patched_dir)


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
        "databases": ["test_sequences_20.csv"],
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

    with pytest.raises(ValueError, match="None of the selected databases"):
        run(_default_params(databases=["nonexistent.csv"]))


def test_run_non_compliant_database_raises(tmp_path):
    """A file missing a required column is not a database, so it cannot be searched."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # Real file, real .csv suffix, but no EC number column.
    (tmp_path / SEQUENCES_DIR.name / "not_a_db.csv").write_text("Entry,Sequence\nE1,MKTAY\n")

    with pytest.raises(ValueError, match="None of the selected databases"):
        run(_default_params(databases=["not_a_db.csv"]))


def test_run_skips_the_bad_database_and_searches_the_good_one(tmp_path, mock_blast):
    """One unusable selection among several is skipped and named, not fatal.

    Two databases are needed for this to mean anything: with one, a partial
    search is indistinguishable from a complete one.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    (tmp_path / SEQUENCES_DIR.name / "not_a_db.csv").write_text("Entry,Sequence\nE1,MKTAY\n")
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    result = run(_default_params(databases=["test_sequences_20.csv", "not_a_db.csv"]))

    cards = {card["label"]: card["value"] for card in result["_stat_cards"]}
    assert cards["Databases Searched"] == "1"
    # Named exactly as it is on disk, extension included.
    assert cards["Databases Skipped"] == "not_a_db.csv"


def test_run_reads_a_tsv_database(tmp_path, mock_blast):
    """A TSV database must be parsed with tabs and searched like any other.

    Without the separator following the extension a TSV parses as one giant
    column and the merge below finds nothing.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    # Same three rows as a CSV would hold, tab-separated, plus a metadata
    # column that only exists in this file.
    (tmp_path / SEQUENCES_DIR.name / "enzymes.tsv").write_text(
        "Entry\tSequence\tEC number\tOrganism\nA0A009IHW8\tMKTAY\t3.2.2.-\tAcinetobacter\n"
    )
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    result = run(_default_params(databases=["enzymes.tsv"]))

    assert "Organism" in result["dataframe"]["columns"]
    row = result["dataframe"]["data"][0]
    assert row["Organism"] == "Acinetobacter"
    assert row["database"] == "enzymes.tsv"


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

    with pytest.raises(ValueError, match="None of the selected databases"):
        run(_default_params(databases=[filename]))


def test_run_path_traversal_sanitized():
    """Directory components are stripped to prevent path-traversal attacks.

    ``../../etc/secrets.csv`` becomes ``secrets.csv`` (via ``Path.name``),
    which will not exist in the data directory.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    with pytest.raises(ValueError, match="None of the selected databases"):
        run(_default_params(databases=["../../etc/secrets.csv"]))


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


def test_run_mocked_blast_strips_join_artifacts(mock_blast):
    """The join artifacts (query, Entry) must not appear in consumer output.

    Only these two are dropped: "query" is the literal string "query" in every
    row, and "Entry" is an exact duplicate of "target", the merge key.  Anything
    else in the database is metadata — see the companion test below.
    """
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    for col in [COL_QUERY, COL_ENTRY]:
        assert col not in output_columns, f"Join artifact '{col}' leaked into output"


def test_run_mocked_blast_keeps_all_database_metadata(mock_blast):
    """Every non-required column of the database must survive into the output.

    A sequence database only has to provide Entry, Sequence and EC number; the
    rest is metadata the app does not enumerate, so it must all come through.
    Residue_0index is the regression case — it used to be dropped by name.
    """
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    # Read the database's own header rather than hard-coding the list, so a
    # change to the fixture CSV cannot quietly narrow what this test checks.
    database_columns = pd.read_csv(TEST_SEQUENCES_CSV, nrows=0).columns
    metadata = [c for c in database_columns if c not in {COL_ENTRY, "Unnamed: 0"}]

    assert COL_RESIDUE_0INDEX in metadata, "fixture no longer covers the regression case"
    for column in metadata:
        assert column in output_columns, f"Database metadata '{column}' was dropped"


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
    expected = {"Databases Searched", "Total Sequences", "After Filtering", "Results Returned", "Run Time"}

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


def _write_cofactor_db(tmp_path, filename="cofactor_db.tsv"):
    """Write a sequence database whose Cofactor column holds real UniProt blobs.

    TSV, not CSV: a cofactor name may itself contain commas
    (``6,7-dimethyl-8-(1-D-ribityl)lumazine``).
    """
    (tmp_path / SEQUENCES_DIR.name / filename).write_text(
        "Entry\tSequence\tEC number\tCofactor\n"
        "P001\tMKTAYIAKQR\t1.1.1.1\tCOFACTOR: Name=NAD(+); Xref=ChEBI:CHEBI:57540; Evidence={ECO:1};\n"
        "P002\tMKTAYIAKQRLL\t1.1.1.1\tCOFACTOR: Name=FAD; Xref=ChEBI:CHEBI:57692;\n"
        "P003\tMKTAYIAKQRLLS\t2.2.2.2\tCOFACTOR: Name=Mg(2+); Evidence={ECO:1}; Name=NAD(+); Note=Both.;\n"
        "P004\tMKTAYIAKQRLLST\t2.2.2.2\t\n"
    )
    return filename


def _cofactor_params(**overrides):
    """Params for a run over the ``_write_cofactor_db`` database."""
    params = {
        "task_name": "cofactor-test",
        "databases": ["cofactor_db.tsv"],
        "sequence": "MKTAYIAKQR",
        "ec_filter": [],
        "cofactor_filter": [],
        "top_n": 10,
        "predict_catalytic": False,
    }
    params.update(overrides)
    return params


def test_run_cofactor_filter_matches_names_inside_the_blob(mock_blast, tmp_path):
    """A cofactor is matched by its ``Name=`` value, not by the whole cell.

    P001 lists NAD(+) in a single block and P003 lists it as the second name of a
    two-name block — both must survive.  P002 (FAD) and P004 (blank) must not.
    """
    _write_cofactor_db(tmp_path)
    mock_blast.execute.return_value = _make_blast_result_df(["P001"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_cofactor_params(cofactor_filter=["NAD(+)"]))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["Total Sequences"] == "4"
    assert stat_cards["After Filtering"] == "2"

    # BLAST should receive 2 reference rows + 1 query row = 3 total.
    combined_df = mock_blast.execute.call_args[0][0]
    assert len(combined_df) == 3


def test_run_cofactor_filter_keeps_rows_matching_any_selection(mock_blast, tmp_path):
    """Several selected cofactors are OR-ed, exactly as the EC filter treats a multi-selection."""
    _write_cofactor_db(tmp_path)
    mock_blast.execute.return_value = _make_blast_result_df(["P001"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_cofactor_params(cofactor_filter=["FAD", "Mg(2+)"]))

    # FAD matches P002, Mg(2+) matches P003 — neither row lists both.
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "2"


def test_run_cofactor_filter_excludes_rows_with_no_cofactor(mock_blast, tmp_path):
    """A blank cell lists no cofactor, so a filtered run never returns that row."""
    _write_cofactor_db(tmp_path)
    mock_blast.execute.return_value = _make_blast_result_df(["P001"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_cofactor_params(cofactor_filter=["NAD(+)", "FAD", "Mg(2+)"]))

    # Every cofactor in the file is selected, so only the blank P004 is dropped.
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "3"


def test_run_cofactor_filter_drops_a_database_without_the_column(mock_blast, tmp_path):
    """A database with no Cofactor column lists no cofactors, so it contributes no rows.

    ``test_sequences_20.csv`` is filtered on a cofactor it does carry; the
    column-less database beside it must not slip through unfiltered.
    """
    (tmp_path / SEQUENCES_DIR.name / "no_cofactor.csv").write_text(
        "Entry,Sequence,EC number\nP900,MKTAYIAKQR,1.1.1.1\nP901,MKTAYIAKQRLL,1.1.1.1\n"
    )
    mock_blast.execute.return_value = _make_blast_result_df(["A0A009IHW8"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(databases=["test_sequences_20.csv", "no_cofactor.csv"], cofactor_filter=["heme b"]))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    # 20 usable rows in the fixture plus the 2 written above.
    assert stat_cards["Total Sequences"] == "22", "both databases must be loaded before filtering"
    assert stat_cards["After Filtering"] == "1", "only the one heme b row survives"


def test_run_reduces_the_cofactor_column_to_its_names(mock_blast, tmp_path):
    """The grid gets the extracted names, not the raw UniProt blob."""
    _write_cofactor_db(tmp_path)
    mock_blast.execute.return_value = _make_blast_result_df(["P003"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_cofactor_params())

    row = result["dataframe"]["data"][0]
    assert row[COL_COFACTOR] == "Mg(2+); NAD(+)"


def test_run_cofactor_result_is_json_serializable(mock_blast, tmp_path):
    """The reduced column must survive the worker's ``json.dumps`` with no ``default=``."""
    _write_cofactor_db(tmp_path)
    mock_blast.execute.return_value = _make_blast_result_df(["P001"])

    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    json.dumps(run(_cofactor_params(cofactor_filter=["NAD(+)"])))


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
    [COL_QUERY, COL_ENTRY],
    ids=["query", "entry"],
)
def test_run_internal_column_stripped(column):
    """Only the join artifacts are stripped — everything else is database metadata.

    ``Residue_0index`` is deliberately absent from this list.  It was dropped by
    name until the database refactor, which made every non-required column ride
    through into the grid (``AGENTS.md`` → "Adding a New Tool"); it now has its own
    column def in ``results.py``, and
    ``test_run_mocked_blast_keeps_all_database_metadata`` asserts it survives.
    """
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
    """The 'Databases Searched' stat card must count the databases loaded."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    assert stat_cards["Databases Searched"] == "1"


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


def test_results_layout_shows_metadata_columns_it_has_no_def_for():
    """Every column in the payload must reach the grid, named or not.

    A sequence database only has to provide Entry, Sequence and EC number, so
    the curated def list cannot know what metadata a given database carries.
    ``build_ag_grid`` renders only fields that have a def, so an unnamed column
    would silently vanish — these four come from ``enzymes.tsv``.
    """
    import dash_ag_grid as dag

    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    unnamed_columns = ["Organism", "Protein names", "Catalytic activity", "Subunit structure"]
    job = make_job(
        result={
            "dataframe": {
                # One curated column and four the def list has never heard of.
                "columns": ["target", *unnamed_columns],
                "data": [dict.fromkeys(["target", *unnamed_columns], "x")],
            },
        },
    )

    grid = find_components(results_layout(job), dag.AgGrid)[0]
    rendered_fields = [d["field"] for d in grid.columnDefs]

    for column in unnamed_columns:
        assert column in rendered_fields, f"Metadata column '{column}' was dropped from the grid"


def test_results_layout_does_not_duplicate_a_curated_column():
    """A column that already has a curated def must not also get a bare one appended."""
    import dash_ag_grid as dag

    from enzyme_tk_app.app.tools.sequence_similarity.results import results_layout

    job = make_job(
        result={
            "dataframe": {
                "columns": ["target", "bitscore", "Organism"],
                "data": [{"target": "P12345", "bitscore": 200.0, "Organism": "E. coli"}],
            },
        },
    )

    grid = find_components(results_layout(job), dag.AgGrid)[0]
    rendered_fields = [d["field"] for d in grid.columnDefs]

    assert sorted(rendered_fields) == sorted(set(rendered_fields))
    # The curated def is the one that survives, keeping its numeric filter.
    bitscore_def = next(d for d in grid.columnDefs if d["field"] == "bitscore")
    assert bitscore_def.get("filter") == "agNumberColumnFilter"


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
    """Selecting a shipped example populates the sequence textarea and the Task Name."""
    example = _get_example_sequences()[0]

    sequence, _ec, _cofactors, task_name = populate_example_sequence(example["value"])

    assert sequence == example["value"]
    assert task_name == "A0A009IHW8"


def test_populate_example_sequence_leaves_task_name_for_unknown_sequence():
    """A pasted sequence fills the textarea and leaves the user's own fields alone."""
    sequence, ec, cofactors, task_name = populate_example_sequence("MKTAYIAKQR")

    assert sequence == "MKTAYIAKQR"
    assert task_name is no_update
    # Filters the user set by hand must survive a paste, so no_update — not [].
    assert ec is no_update
    assert cofactors is no_update


@pytest.mark.parametrize(
    ("task_name", "expected_ec", "expected_cofactors"),
    [
        ("O04846-carbonic-anhydrase", ["4.2.1.1"], []),
        ("O13289-catalase-heme", [], ["heme"]),
        ("J9VWW9-SOD-Mn", ["1.15.1.1"], ["Mn(2+)"]),
    ],
    ids=["ec-only", "cofactor-only", "both"],
)
def test_populate_example_sequence_prefills_its_filters(task_name, expected_ec, expected_cofactors):
    """An example that declares a filter must write it into the matching dropdown.

    Without this the filter examples are ordinary sequence examples — the whole
    point is that one click shows a pre-filter narrowing the search.
    """
    example = next(ex for ex in _get_example_sequences() if ex["task_name"] == task_name)

    _sequence, ec, cofactors, name = populate_example_sequence(example["value"])

    assert ec == expected_ec
    assert cofactors == expected_cofactors
    assert name == task_name


def test_populate_example_sequence_clears_filters_for_an_unfiltered_example():
    """An example declaring no filters clears both dropdowns rather than leaving them.

    Picking a filtered example and then an unfiltered one must not carry the first
    one's filter into a search the user believes is unfiltered.
    """
    plain = next(ex for ex in _get_example_sequences() if "ec" not in ex and "cofactors" not in ex)

    _sequence, ec, cofactors, _name = populate_example_sequence(plain["value"])

    assert ec == []
    assert cofactors == []


def test_every_example_filter_value_is_a_usable_string():
    """A declared filter value must be a non-blank string.

    ``dcc.Dropdown`` renders nothing for a value with no matching option, so a
    typo'd or ``None`` entry here reads as a filter that silently did not apply.
    Membership in the database itself is not checkable here — that is an 812 MB
    scan — so this pins the shape and ``verify-ui`` proves the values are real.
    """
    for example in _get_example_sequences():
        for key in ("ec", "cofactors"):
            values = example.get(key, [])
            assert isinstance(values, list), f"{example['task_name']}: {key} must be a list"
            for value in values:
                assert isinstance(value, str), f"{example['task_name']}: {key} holds a non-string"
                assert value.strip(), f"{example['task_name']}: {key} holds a blank value"


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
    assert validate_sequence_form("My Task", "MKTAYIAKQR", "test_sequences_20.csv") is False


def test_validate_form_disabled_when_sequence_missing():
    """Submit must be disabled when the sequence is empty."""
    assert validate_sequence_form("My Task", "", "test_sequences_20.csv") is True


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
        result = submit_sequence_similarity_job(0, 1, "t", ["db.csv"], "MKTAY", None, None, 10, False, None)

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
            result = submit_sequence_similarity_job(
                1, 0, "My Task", ["test_sequences_20.csv"], "MKTAYIAKQR", None, None, 10, False, None
            )

    assert submitted_job_id(result) == "job-abc-123"


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
        result = submit_sequence_similarity_job(
            1, 0, "My Task", ["test_sequences_20.csv"], "MKTAYIAKQR", None, None, None, False, None
        )

    # validate_top_n returns an error string for None — no job should be submitted.
    assert "Invalid" in submission_error_text(result)
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
                1, 0, "EC Task", ["test_sequences_20.csv"], "MKTAYIAKQR", ec_filter, None, 10, False, None
            )

    # Must mention both the job ID and the filter summary.
    assert submitted_job_id(result) == "job-ec-456"
    assert "3 EC filter(s)" in get_text(result)


def test_submit_message_includes_cofactor_filter_count():
    """A cofactor filter must be named in the submit message, like the EC filter."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-cof-789"

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-cof"
        with (
            patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_sequence_similarity_job(
                1, 0, "Cofactor Task", ["test_sequences_20.csv"], "MKTAYIAKQR", None, ["FAD", "heme b"], 10, False, None
            )

    assert submitted_job_id(result) == "job-cof-789"
    assert "2 cofactor(s)" in get_text(result)
    # The params reach the worker as a list, the shape ``run()`` expects.
    assert mock_scheduler.submit_job.call_args.kwargs["params"]["cofactor_filter"] == ["FAD", "heme b"]


def test_submit_message_without_filters_names_no_filters():
    """Without EC or cofactor filters, the detail fragment must name neither."""
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
            result = submit_sequence_similarity_job(
                1, 0, "Task", ["test_sequences_20.csv"], "MKTAY", None, None, 10, False, None
            )

    assert submitted_job_id(result) == "job-no-filter"
    assert "EC filter" not in get_text(result)
    assert "cofactor" not in get_text(result)


def test_submit_raises_prevent_update_when_fields_empty():
    """Server-side guard must raise PreventUpdate when required fields are missing."""
    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        with pytest.raises(PreventUpdate):
            submit_sequence_similarity_job(1, 0, "", ["test_sequences_20.csv"], "MKTAY", None, None, 10, False, None)


@pytest.mark.parametrize(
    "database",
    ["malicious.txt", "../../etc/passwd", "protein.csv", "not_a_db.csv"],
    ids=["wrong-extension", "path-traversal", "not-in-this-directory", "non-compliant"],
)
def test_submit_rejects_database_that_is_not_offered(tmp_path, database):
    """Any name the dropdown does not currently offer must be refused, job unscheduled.

    The submit callback validates by membership in the tool's own option list,
    so a traversal attempt, a real-but-absent filename, and a file that exists
    yet fails the column contract all fail the same way.
    """
    # Exists on disk, but has no Sequence column — so it is not a database.
    (tmp_path / SEQUENCES_DIR.name / "not_a_db.csv").write_text("Entry,EC number\nE1,1.1.1.1\n")
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.sequence_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.sequence_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_sequence_similarity_job(1, 0, "Task", [database], "MKTAY", None, None, 10, False, None)

    assert "Unknown database" in submission_error_text(result)
    mock_scheduler.submit_job.assert_not_called()


# ── populate_ec_options ──────────────────────────────────────────────────────


def _write_sequence_db(tmp_path, filename, ec_cells):
    """Write a minimal compliant sequence database and return its filename.

    The EC dropdown only reads the EC column, but a file is only a database at
    all once it has all three required columns — so the other two are filled in
    with throwaway values rather than omitted.
    """
    rows = "\n".join(f"E{i},MKTAY,{cell}" for i, cell in enumerate(ec_cells))
    (tmp_path / SEQUENCES_DIR.name / filename).write_text(f"Entry,Sequence,EC number\n{rows}\n")
    return filename


def test_populate_ec_options_returns_options_for_valid_database(tmp_path):
    """A valid database must produce dropdown options for each unique EC number."""
    name = _write_sequence_db(tmp_path, "test_db.csv", ["3.2.2.-", "1.1.1.1", "3.2.2.-"])

    options, cleared = populate_ec_options([name])

    # Should have two unique EC numbers, sorted.
    assert len(options) == 2
    labels = [o["label"] for o in options]
    assert labels == ["1.1.1.1", "3.2.2.-"]
    assert cleared == []


def test_populate_ec_options_value_matches_label(tmp_path):
    """Each option's value must equal its label (used as the filter key)."""
    name = _write_sequence_db(tmp_path, "db.csv", ["1.2.3.4", "5.6.7.8"])

    options, _ = populate_ec_options([name])

    assert options, "no options produced — the rest of this test would vacuously pass"
    for opt in options:
        assert opt["label"] == opt["value"]


def test_populate_ec_options_returns_empty_for_missing_file():
    """A non-existent database file must return an empty list (no crash)."""
    options, cleared = populate_ec_options(["no_such_file.csv"])

    assert options == []
    assert cleared == []


def test_populate_ec_options_splits_semicolon_ec_numbers(tmp_path):
    """EC numbers separated by semicolons in a single cell must be split into separate options."""
    name = _write_sequence_db(tmp_path, "multi_ec.csv", ["3.2.2.-; 1.1.1.1", "2.7.1.1"])

    options, _ = populate_ec_options([name])

    labels = [o["label"] for o in options]
    assert labels == ["1.1.1.1", "2.7.1.1", "3.2.2.-"]


def test_populate_ec_options_skips_non_compliant_database(tmp_path):
    """A file missing a required column is not a database, so it contributes no EC numbers."""
    # Has the EC column the dropdown reads, but no Entry and no Sequence.
    (tmp_path / SEQUENCES_DIR.name / "not_a_db.csv").write_text("EC number\n1.1.1.1\n")

    assert populate_ec_options(["not_a_db.csv"]) == ([], [])


def test_populate_ec_options_returns_empty_for_non_csv_extension():
    """A filename that is not an offered database must return an empty list."""
    assert populate_ec_options(["malicious.txt"]) == ([], [])


def test_populate_ec_options_strips_path_traversal_and_rejects_non_csv():
    """Path-traversal attempts with a non-.csv suffix must return an empty list."""
    assert populate_ec_options(["../../etc/passwd"]) == ([], [])


# ── populate_cofactor_options ────────────────────────────────────────────────


def _write_cofactor_options_db(tmp_path, filename, cofactor_cells):
    """Write a compliant sequence database whose Cofactor cells are UniProt blobs.

    TSV, not CSV: a cofactor name may itself contain commas
    (``6,7-dimethyl-8-(1-D-ribityl)lumazine``).
    """
    rows = "\n".join(f"E{i}\tMKTAY\t1.1.1.1\t{cell}" for i, cell in enumerate(cofactor_cells))
    (tmp_path / SEQUENCES_DIR.name / filename).write_text(f"Entry\tSequence\tEC number\tCofactor\n{rows}\n")
    return filename


def test_populate_cofactor_options_returns_options_for_valid_database(tmp_path):
    """A valid database must produce one option per unique cofactor name, sorted."""
    name = _write_cofactor_options_db(
        tmp_path,
        "cofactor_db.tsv",
        [
            "COFACTOR: Name=Zn(2+); Xref=ChEBI:CHEBI:29105;",
            "COFACTOR: Name=FAD; Xref=ChEBI:CHEBI:57692;",
            "COFACTOR: Name=Zn(2+); Xref=ChEBI:CHEBI:29105; Evidence={ECO:1};",
        ],
    )

    options, cleared = populate_cofactor_options([name])

    assert [o["label"] for o in options] == ["FAD", "Zn(2+)"]
    assert cleared == []


def test_populate_cofactor_options_extracts_every_name_in_a_cell(tmp_path):
    """Both multi-name shapes contribute every name, and no Xref/Evidence leaks in."""
    name = _write_cofactor_options_db(
        tmp_path,
        "multi_cofactor.tsv",
        [
            "COFACTOR: Name=Mg(2+); Xref=ChEBI:CHEBI:18420; Name=Mn(2+); Note=Prefers Mn(2+).;",
            "COFACTOR: Name=NAD(+); Xref=ChEBI:CHEBI:57540; COFACTOR: Name=heme b; Evidence={ECO:1};",
        ],
    )

    options, _ = populate_cofactor_options([name])

    assert [o["label"] for o in options] == ["Mg(2+)", "Mn(2+)", "NAD(+)", "heme b"]


def test_populate_cofactor_options_value_matches_label(tmp_path):
    """Each option's value must equal its label (used as the filter key)."""
    name = _write_cofactor_options_db(tmp_path, "db.tsv", ["COFACTOR: Name=FAD; Xref=ChEBI:CHEBI:57692;"])

    options, _ = populate_cofactor_options([name])

    assert options, "no options produced — the rest of this test would vacuously pass"
    for opt in options:
        assert opt["label"] == opt["value"]


def test_populate_cofactor_options_empty_for_database_without_the_column(tmp_path):
    """A database with no Cofactor column contributes nothing rather than raising.

    ``Cofactor`` is not a required column and every database is selected by
    default, so a raise here would break the tool's modal on load.
    """
    (tmp_path / SEQUENCES_DIR.name / "no_cofactor.csv").write_text("Entry,Sequence,EC number\nE0,MKTAY,1.1.1.1\n")

    assert populate_cofactor_options(["no_cofactor.csv"]) == ([], [])


def test_populate_cofactor_options_returns_empty_for_missing_file():
    """A non-existent database file must return an empty list (no crash)."""
    assert populate_cofactor_options(["no_such_file.csv"]) == ([], [])


def test_populate_cofactor_options_skips_non_compliant_database(tmp_path):
    """A file missing a required column is not a database, so it contributes no cofactors."""
    # Has the Cofactor column the dropdown reads, but no Entry and no Sequence.
    (tmp_path / SEQUENCES_DIR.name / "not_a_db.csv").write_text("Cofactor\nCOFACTOR: Name=FAD;\n")

    assert populate_cofactor_options(["not_a_db.csv"]) == ([], [])


def test_populate_cofactor_options_returns_empty_for_non_csv_extension():
    """A filename that is not an offered database must return an empty list."""
    assert populate_cofactor_options(["malicious.txt"]) == ([], [])


def test_populate_cofactor_options_strips_path_traversal_and_rejects_non_csv():
    """Path-traversal attempts with a non-.csv suffix must return an empty list."""
    assert populate_cofactor_options(["../../etc/passwd"]) == ([], [])


def test_populate_cofactor_options_raises_for_empty_value():
    """No databases selected means nothing to offer — the dropdown is left alone."""
    with pytest.raises(PreventUpdate):
        populate_cofactor_options([])


# ── compute.run() — path-traversal & cofactor guards ────────────────────────


def test_run_cofactor_in_no_results_message():
    """When the cofactor filter empties the frame, the message must name the cofactor."""
    from enzyme_tk_app.app.tools.sequence_similarity.compute import run

    result = run(_default_params(cofactor_filter=["NONEXISTENT_COFACTOR"]))

    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["After Filtering"] == "0"
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


def test_modal_cofactor_dropdown_is_enabled_and_starts_empty():
    """The cofactor dropdown must be usable and, like EC, filled by its callback.

    It shipped ``disabled=True`` while no cofactor data was loaded; leaving that in
    would make the filter unreachable however well the rest of the path works.
    """
    from enzyme_tk_app.app.tools.sequence_similarity.modal import modal as build_modal

    with patch(
        "enzyme_tk_app.app.tools.sequence_similarity.modal.get_sequence_database_options",
        return_value=[{"label": "Test Db", "value": "test_db.csv"}],
    ):
        component = build_modal()

    cofactor_dd = [d for d in find_components(component, dcc.Dropdown) if d.id and "cofactor-filter" in d.id]
    assert len(cofactor_dd) == 1
    assert not getattr(cofactor_dd[0], "disabled", False)
    assert cofactor_dd[0].options == []


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
