"""Tests for data loading utilities."""

from enzyme_tk_app.app.utils.data_loading import load_sequence_data


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
