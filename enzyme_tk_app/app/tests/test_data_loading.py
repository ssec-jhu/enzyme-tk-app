"""Tests for data loading utilities."""

from enzyme_tk_app.app.utils.data_loading import get_foldseek_database_options, load_sequence_data


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
