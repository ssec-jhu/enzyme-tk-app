"""Tests for data loading utilities."""

import pytest

from enzyme_tk_app.app.utils.data_loading import (
    get_foldseek_database_options,
    get_funce_database_options,
    get_reaction_database_options,
    get_sequence_database_options,
    load_sequence_data,
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
# entry pairs a builder with the module constant naming its data directory and a
# fixture filename that any prettifying would visibly mangle.  Kept in one list
# so both tests below stay in step when a fourth database dropdown appears.
_FILE_DATABASE_BUILDERS = [
    (get_reaction_database_options, "REACTIONS_DIR", "MetaCyc_reactions_v2.csv"),
    (get_sequence_database_options, "SEQUENCES_DIR", "protein_20_slice_1.csv"),
    (get_funce_database_options, "FUNCE_DB_DIR", "Funce_pairs.pkl"),
]
_FILE_DATABASE_IDS = ["reactions", "sequences", "funce"]


@pytest.mark.parametrize(
    ("build_options", "data_dir_constant", "database_filename"),
    _FILE_DATABASE_BUILDERS,
    ids=_FILE_DATABASE_IDS,
)
def test_file_database_options_label_is_the_whole_filename(
    build_options, data_dir_constant, database_filename, tmp_path, monkeypatch
):
    """A database is labelled exactly as it is named on disk, extension included.

    The filenames above deliberately mix underscores with upper- and lower-case
    letters and keep their suffix, so both ways of losing the spelling fail here:
    a reintroduced ``.replace("_", " ").title()`` would render "Metacyc Reactions
    V2", and a ``.stem`` would drop the ``.csv``.
    """
    db_dir = tmp_path / "databases"
    db_dir.mkdir()
    (db_dir / database_filename).write_text("stub contents")

    monkeypatch.setattr(f"enzyme_tk_app.app.utils.data_loading.{data_dir_constant}", db_dir)

    assert build_options() == [{"label": database_filename, "value": database_filename}]


@pytest.mark.parametrize(
    ("build_options", "data_dir_constant", "database_filename"),
    _FILE_DATABASE_BUILDERS,
    ids=_FILE_DATABASE_IDS,
)
def test_file_database_options_empty_when_dir_missing(
    build_options, data_dir_constant, database_filename, tmp_path, monkeypatch
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
# filesystem paths, so every rejection below is load-bearing.


@pytest.mark.parametrize(
    ("names", "suffix"),
    [
        (["protein.csv"], ".csv"),
        (["Funce_pairs.pkl"], ".pkl"),
        (["AFDB_SWISSPROT", "PDB"], None),  # FoldSeek databases are directories
        (["a-b_C9.csv"], ".csv"),
    ],
    ids=["csv", "pkl", "foldseek-dirs", "punctuation-in-allowlist"],
)
def test_validate_db_names_accepts_valid(names, suffix):
    """A bare identifier plus the expected suffix passes."""
    assert validate_db_names(names, suffix) is None


@pytest.mark.parametrize(
    ("names", "suffix"),
    [
        ([], ".csv"),
        (None, ".csv"),
        (["../reactions/x.csv"], ".csv"),
        (["a/b.csv"], ".csv"),
        (["..csv"], ".csv"),
        (["x.pkl.csv"], ".csv"),
        (["bad;.csv"], ".csv"),
        (["ok.csv", "bad;.csv"], ".csv"),
        (["x.csv"], ".pkl"),
    ],
    ids=[
        "empty",
        "none",
        "traversal",
        "subdir",
        "dot-dot",
        "double-ext",
        "shell-char",
        "one-bad-in-list",
        "wrong-suffix",
    ],
)
def test_validate_db_names_rejects_invalid(names, suffix):
    """Invalid selections return a message rather than raising."""
    assert isinstance(validate_db_names(names, suffix), str)


@pytest.mark.parametrize(
    "name",
    [123, None, True, 3.14, {"a": 1}, ["nested"]],
    ids=["int", "none-item", "bool", "float", "dict", "list"],
)
def test_validate_db_names_rejects_non_string_items(name):
    """A crafted request can put anything in the list.

    Without an ``isinstance`` check these blow up on ``.endswith()`` or the
    regex and surface as a 500 instead of a validation message.  Checked with
    and without a suffix, since the two take different code paths.
    """
    assert isinstance(validate_db_names([name], ".csv"), str)
    assert isinstance(validate_db_names([name], None), str)


def test_validate_db_names_rejects_bare_string():
    """A string instead of a list is reported, never raised.

    A ``multi=False`` dropdown returns a string, and iterating it would validate
    one character at a time and silently pass — so it must be caught.  But the
    value comes from the browser, so raising would turn a crafted request into
    an HTTP 500; it is reported like any other bad input instead.
    """
    assert isinstance(validate_db_names("protein.csv", ".csv"), str)


def test_validate_db_names_does_not_modify_input():
    """It verifies without repairing — nothing is stripped, cased, or coerced."""
    names = ["  padded.csv  "]
    assert isinstance(validate_db_names(names, ".csv"), str)
    assert names == ["  padded.csv  "]
