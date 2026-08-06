"""Tests for data loading utilities."""

import gzip

import pytest

from enzyme_tk_app.app.tests.conftest import offered_databases
from enzyme_tk_app.app.utils.data_loading import (
    get_ec_numbers,
    get_foldseek_database_options,
    get_reaction_database_options,
    get_sequence_database_options,
    get_sequence_embedding_database_options,
    load_sequence_data,
    scan_sequence_databases,
    sequence_db_separator,
    validate_db_names,
)


def test_load_sequence_data_filters_correctly(sequence_csv):
    """Test that load_sequence_data drops internal index columns and empty sequences.

    The sequence_csv fixture contains:
    - 20 valid sequences from protein.csv
    - 1 Missing sequence (None)
    - 1 Whitespace sequence ("   ")
    """
    df = load_sequence_data(sequence_csv)

    # Check that 'Unnamed: 0' was dropped if it existed
    assert "Unnamed: 0" not in df.columns

    # Check that only valid sequences are retained (20 rows out of 22)
    assert len(df) == 20

    # Ensure remaining sequences are the valid ones
    sequences = df["Sequence"].tolist()

    # Ensure NaN/whitespace were dropped
    assert None not in sequences
    assert "   " not in sequences
    assert "" not in sequences


# ── get_foldseek_database_options ─────────────────────────────────────────────


def test_get_foldseek_database_options_returns_valid_entries(tmp_path, monkeypatch):
    """Subdirectories are returned as label/value dicts, hidden and tmp dirs excluded."""
    db_dir = tmp_path / "foldseek_db"
    db_dir.mkdir()
    (db_dir / "alpha_fold").mkdir()
    (db_dir / "pdb_100").mkdir()
    (db_dir / ".hidden").mkdir()
    (db_dir / "tmp").mkdir()
    # Regular file should be ignored
    (db_dir / "readme.txt").write_text("ignore me")

    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.FOLDSEEK_DB_DIR", db_dir)

    options = get_foldseek_database_options()

    # The folder name is shown exactly as it is on disk — no prettifying, so a
    # scientist can match the dropdown against data/foldseek_db/.
    assert options == [
        {"label": "alpha_fold", "value": "alpha_fold"},
        {"label": "pdb_100", "value": "pdb_100"},
    ]


def test_get_foldseek_database_options_empty_when_dir_missing(tmp_path, monkeypatch):
    """Returns an empty list when the foldseek_db directory does not exist."""
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.FOLDSEEK_DB_DIR", tmp_path / "nonexistent")

    # The function should handle the missing directory gracefully and return an empty list,
    # not raise an error. Function will trigger downloads  in the code
    assert get_foldseek_database_options() == []


# ── File-based database dropdowns ─────────────────────────────────────────────
# The three dropdowns whose options come from files rather than folders.  Each
# entry pairs a builder with the module constant naming its data directory, a
# fixture filename that any prettifying would visibly mangle, and the contents
# that make the file count as a database (only the sequence builder inspects
# them).  Kept in one list so both tests below stay in step when a fourth
# database dropdown appears.
_FILE_DATABASE_BUILDERS = [
    (get_reaction_database_options, "REACTIONS_DIR", "MetaCyc_reactions_v2.csv", "stub contents"),
    (get_sequence_database_options, "SEQUENCES_DIR", "protein_20_slice_1.csv", "Entry,Sequence,EC number\n"),
    (get_sequence_embedding_database_options, "SEQUENCE_EMBEDDINGS_DIR", "Funce_pairs.pkl", "stub contents"),
]
_FILE_DATABASE_IDS = ["reactions", "sequences", "embeddings"]


@pytest.mark.parametrize(
    ("build_options", "data_dir_constant", "database_filename", "file_contents"),
    _FILE_DATABASE_BUILDERS,
    ids=_FILE_DATABASE_IDS,
)
def test_file_database_options_label_is_the_whole_filename(
    build_options, data_dir_constant, database_filename, file_contents, tmp_path, monkeypatch
):
    """A database is labelled exactly as it is named on disk, extension included.

    The filenames above deliberately mix underscores with upper- and lower-case
    letters and keep their suffix, so both ways of losing the spelling fail here:
    a reintroduced ``.replace("_", " ").title()`` would render "Metacyc Reactions
    V2", and a ``.stem`` would drop the ``.csv``.
    """
    db_dir = tmp_path / "databases"
    db_dir.mkdir()
    (db_dir / database_filename).write_text(file_contents)

    monkeypatch.setattr(f"enzyme_tk_app.app.utils.data_loading.{data_dir_constant}", db_dir)

    assert build_options() == [{"label": database_filename, "value": database_filename}]


@pytest.mark.parametrize(
    ("build_options", "data_dir_constant", "database_filename", "file_contents"),
    _FILE_DATABASE_BUILDERS,
    ids=_FILE_DATABASE_IDS,
)
def test_file_database_options_empty_when_dir_missing(
    build_options, data_dir_constant, database_filename, file_contents, tmp_path, monkeypatch
):
    """A missing data directory yields no options instead of raising.

    On a fresh checkout the ``data/`` subdirectories may not exist yet, and the
    modal is built at import time — so the builders must degrade to an empty
    dropdown rather than break the page.
    """
    monkeypatch.setattr(f"enzyme_tk_app.app.utils.data_loading.{data_dir_constant}", tmp_path / "nonexistent")

    assert build_options() == []


# ── validate_db_names ─────────────────────────────────────────────────────────
# Database names cross a trust boundary: they arrive from the browser and become
# filesystem paths, so every rejection below is load-bearing.  The check is
# membership in the tool's own dropdown options — an exact allowlist, so a name
# that is not offered is refused whatever it looks like.

# What the dropdowns are offering in these tests: a sequence CSV, an embeddings
# pickle, and the two FoldSeek directories (which have no extension at all).
_OFFERED = offered_databases("protein.csv", "Funce_pairs.pkl", "AFDB_SWISSPROT", "PDB")


@pytest.mark.parametrize(
    "names",
    [
        ["protein.csv"],
        ["Funce_pairs.pkl"],
        ["AFDB_SWISSPROT", "PDB"],
        ["protein.csv", "Funce_pairs.pkl", "AFDB_SWISSPROT", "PDB"],
    ],
    ids=["csv", "pkl", "foldseek-dirs", "all-of-them"],
)
def test_validate_db_names_accepts_offered_names(names):
    """A name the dropdown is currently offering passes."""
    assert validate_db_names(names, _OFFERED) is None


@pytest.mark.parametrize(
    "names",
    [
        [],
        None,
        ["../reactions/protein.csv"],
        ["a/protein.csv"],
        ["protein.csv.csv"],
        ["bad;.csv"],
        ["protein"],
        ["PROTEIN.CSV"],
        ["absent.csv"],
        ["protein.csv", "absent.csv"],
    ],
    ids=[
        "empty",
        "none",
        "traversal",
        "subdir",
        "double-ext",
        "shell-char",
        "suffix-stripped",
        "wrong-case",
        "not-offered",
        "one-bad-in-list",
    ],
)
def test_validate_db_names_rejects_names_not_offered(names):
    """Invalid selections return a message rather than raising.

    Traversal, a stripped suffix and a case change all fail for the same
    reason — they are not the string the dropdown offered.
    """
    assert isinstance(validate_db_names(names, _OFFERED), str)


@pytest.mark.parametrize(
    "name",
    [123, None, True, 3.14, {"a": 1}, ["nested"]],
    ids=["int", "none-item", "bool", "float", "dict", "list"],
)
def test_validate_db_names_rejects_non_string_items(name):
    """A crafted request can put anything in the list.

    The unhashable ones would raise on the set lookup without the
    ``isinstance`` check, surfacing as a 500 instead of a validation message.
    """
    assert isinstance(validate_db_names([name], _OFFERED), str)


def test_validate_db_names_rejects_bare_string():
    """A string instead of a list is reported, never raised.

    A ``multi=False`` dropdown returns a string, and iterating it would validate
    one character at a time and silently pass — so it must be caught.  But the
    value comes from the browser, so raising would turn a crafted request into
    an HTTP 500; it is reported like any other bad input instead.
    """
    assert isinstance(validate_db_names("protein.csv", _OFFERED), str)


def test_validate_db_names_rejects_everything_when_nothing_is_offered():
    """With no databases on disk the dropdown is empty, so no name can be valid."""
    assert isinstance(validate_db_names(["protein.csv"], []), str)


def test_validate_db_names_does_not_modify_input():
    """It verifies without repairing — nothing is stripped, cased, or coerced."""
    names = ["  protein.csv  "]
    assert isinstance(validate_db_names(names, _OFFERED), str)
    assert names == ["  protein.csv  "]


# ── The sequence-database contract ────────────────────────────────────────────
# A file in data/sequences/ is a database when its extension is one of
# SEQUENCE_DB_SUFFIXES and its header has all of REQUIRED_SEQUENCE_COLUMNS.
# Anything else is reported by check_data() instead of being offered.

_COMPLIANT_ROWS = "Entry,Sequence,EC number\nE1,MKTAY,1.1.1.1\nE2,MSLEQ,3.2.2.-\n"


def _write_database(directory, filename, text=_COMPLIANT_ROWS):
    """Write *text* as a sequence database, converting to TSV and/or gzip by extension."""
    path = directory / filename
    body = text.replace(",", "\t") if ".tsv" in filename else text
    if filename.endswith(".gz"):
        path.write_bytes(gzip.compress(body.encode()))
    else:
        path.write_text(body)
    return path


@pytest.fixture()
def sequences_db_dir(tmp_path, monkeypatch):
    """Point ``SEQUENCES_DIR`` at an empty tmp directory and return it."""
    db_dir = tmp_path / "sequences"
    db_dir.mkdir()
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", db_dir)
    return db_dir


@pytest.mark.parametrize(
    "filename",
    ["plain.csv", "tabbed.tsv", "zipped.csv.gz", "zipped.tsv.gz"],
    ids=["csv", "tsv", "csv-gz", "tsv-gz"],
)
def test_scan_accepts_every_supported_suffix(sequences_db_dir, filename):
    """All four suffixes are read with the right separator and offered by name."""
    _write_database(sequences_db_dir, filename)

    names, problems = scan_sequence_databases()

    assert names == [filename]
    assert problems == []


@pytest.mark.parametrize(
    ("header", "expected_missing"),
    [
        ("Sequence,EC number", "Entry"),
        ("Entry,EC number", "Sequence"),
        ("Entry,Sequence", "EC number"),
    ],
    ids=["no-entry", "no-sequence", "no-ec-number"],
)
def test_scan_rejects_database_missing_a_required_column(sequences_db_dir, header, expected_missing):
    """A file short of any required column is not a database, and is named as a problem."""
    _write_database(sequences_db_dir, "incomplete.csv", f"{header}\nx,y\n")

    names, problems = scan_sequence_databases()

    assert names == []
    assert len(problems) == 1
    # The filename and the specific missing column both have to be in the
    # message — that is what the home-page tooltip shows the scientist.
    assert "incomplete.csv" in problems[0]
    assert expected_missing in problems[0]


def test_scan_reports_the_bad_file_and_still_offers_the_good_one(sequences_db_dir):
    """One malformed file must not hide the databases beside it."""
    _write_database(sequences_db_dir, "good.csv")
    _write_database(sequences_db_dir, "bad.csv", "Entry,Sequence\nE1,MKTAY\n")

    names, problems = scan_sequence_databases()

    assert names == ["good.csv"]
    assert len(problems) == 1
    assert "bad.csv" in problems[0]


def test_scan_reports_an_unreadable_file_instead_of_raising(sequences_db_dir):
    """A corrupt gzip is user-supplied data — it is a problem to report, not a crash."""
    (sequences_db_dir / "truncated.csv.gz").write_bytes(b"not actually gzip")

    names, problems = scan_sequence_databases()

    assert names == []
    assert len(problems) == 1
    assert "truncated.csv.gz" in problems[0]


def test_scan_ignores_files_that_are_not_databases(sequences_db_dir):
    """An unrelated extension is skipped silently — it was never claiming to be a database."""
    _write_database(sequences_db_dir, "real.csv")
    (sequences_db_dir / "notes.txt").write_text("just a note")
    (sequences_db_dir / "archive.zip").write_bytes(b"PK\x03\x04")

    assert scan_sequence_databases() == (["real.csv"], [])


def test_scan_returns_nothing_when_the_directory_is_missing(tmp_path, monkeypatch):
    """A fresh checkout has no data/sequences/ yet — that is empty, not an error."""
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", tmp_path / "nonexistent")

    assert scan_sequence_databases() == ([], [])


def test_sequence_options_exclude_non_compliant_files(sequences_db_dir):
    """The dropdown offers compliant databases only — a bad file cannot be selected."""
    _write_database(sequences_db_dir, "good.tsv")
    _write_database(sequences_db_dir, "bad.csv", "Entry,Sequence\nE1,MKTAY\n")

    assert get_sequence_database_options() == [{"label": "good.tsv", "value": "good.tsv"}]


def test_scan_picks_up_an_edited_file(sequences_db_dir):
    """The header cache keys on mtime and size, so an edited database is rescanned.

    Without this a scientist would have to restart the app after fixing a
    database's columns.
    """
    path = _write_database(sequences_db_dir, "fixable.csv", "Entry,Sequence\nE1,MKTAY\n")
    assert scan_sequence_databases()[0] == []

    _write_database(sequences_db_dir, "fixable.csv")

    assert scan_sequence_databases() == (["fixable.csv"], [])
    assert path.exists()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("protein.csv", ","),
        ("enzymes.tsv", "\t"),
        ("protein.csv.gz", ","),
        ("enzymes.tsv.gz", "\t"),
    ],
    ids=["csv", "tsv", "csv-gz", "tsv-gz"],
)
def test_sequence_db_separator_follows_the_extension(tmp_path, filename, expected):
    """The extension decides the separator — a .gz is unwrapped before the check."""
    assert sequence_db_separator(tmp_path / filename) == expected


def test_load_sequence_data_reads_a_tsv(sequences_db_dir):
    """A TSV must parse into real columns, not one giant column."""
    path = _write_database(sequences_db_dir, "tabbed.tsv")

    df = load_sequence_data(path)

    assert list(df.columns) == ["Entry", "Sequence", "EC number"]
    assert len(df) == 2


def test_get_ec_numbers_reads_a_tsv(sequences_db_dir):
    """EC numbers must be extracted from a TSV the same as from a CSV."""
    path = _write_database(sequences_db_dir, "tabbed.tsv")

    assert get_ec_numbers(path) == ["1.1.1.1", "3.2.2.-"]
