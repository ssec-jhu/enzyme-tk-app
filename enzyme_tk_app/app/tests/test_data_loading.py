"""Tests for data loading utilities."""

import pytest

from enzyme_tk_app.app.utils.data_loading import (
    get_foldseek_database_options,
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

    assert options == [
        {"label": "Alpha Fold", "value": "alpha_fold"},
        {"label": "Pdb 100", "value": "pdb_100"},
    ]


def test_get_foldseek_database_options_empty_when_dir_missing(tmp_path, monkeypatch):
    """Returns an empty list when the foldseek_db directory does not exist."""
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.FOLDSEEK_DB_DIR", tmp_path / "nonexistent")

    # The function should handle the missing directory gracefully and return an empty list,
    # not raise an error. Function will trigger downloads  in the code
    assert get_foldseek_database_options() == []


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


def test_validate_db_names_raises_on_bare_string():
    """A string instead of a list is a programming error, not bad user input.

    A ``multi=False`` dropdown returns a string; iterating it would validate one
    character at a time and silently pass, so this must surface loudly rather
    than become a user-facing message.
    """
    with pytest.raises(TypeError):
        validate_db_names("protein.csv", ".csv")


def test_validate_db_names_does_not_modify_input():
    """It verifies without repairing — nothing is stripped, cased, or coerced."""
    names = ["  padded.csv  "]
    assert isinstance(validate_db_names(names, ".csv"), str)
    assert names == ["  padded.csv  "]
