"""Data file discovery and dropdown-option builders.

These helpers scan the ``data/`` directories and return option lists
suitable for Dash dropdown components.
"""

from pathlib import Path

import pandas as pd

# Base data directory (relative to this file).
DATA_DIR = Path(__file__).parent.parent / "data"

# Column in the CSV that contains the un-mapped reaction SMILES.
_COL_UNMAPPED_SMILES = "unmapped"
# Column name for the individual molecule SMILES extracted from a reaction.
_COL_MOL_SMILES = "molecule_smiles"
# Column name for the molecule's position index within the substrate/product list.
_COL_MOL_INDEX = "molecule_index"
# Column name for the rendered SVG of the molecule.
_COL_MOL_SVG = "molecule_svg"
# Columns to exclude from the final output (internal CSV index).
_EXCLUDE_COLS = {"Unnamed: 0"}

# Column in the sequence CSV that contains the EC classification.
_COL_EC_NUMBER = "EC number"
# Column in the sequence CSV that contains the protein sequence.
_COL_SEQUENCE = "Sequence"
# Column in the sequence CSV that contains the protein entry ID.
_COL_ENTRY = "Entry"


def get_reaction_database_options():
    """Scan the data/reactions directory and return dropdown options.

    Returns:
        List of dicts with label/value for each CSV file found.
        Each dict has 'label' (human-readable) and 'value' (filename).
    """
    reactions_dir = DATA_DIR / "reactions"
    options = []
    if reactions_dir.exists():
        for f in sorted(reactions_dir.glob("*.csv")):
            # Use filename without extension as label, full filename as value
            label = f.stem.replace("_", " ").title()
            options.append({"label": label, "value": f.name})
    return options


def get_sequence_database_options():
    """Scan the data/sequences directory and return dropdown options.

    Looks for CSV files containing protein sequence data.

    Returns:
        List of dicts with label/value for each CSV file found.
        Each dict has 'label' (human-readable) and 'value' (filename).
    """
    sequences_dir = DATA_DIR / "sequences"
    options = []
    if sequences_dir.exists():
        for f in sorted(sequences_dir.glob("*.csv")):
            label = f.stem.replace("_", " ").title()
            options.append({"label": label, "value": f.name})
    return options


def load_sequence_data(csv_path):
    """Read a sequence CSV and drop unusable rows.

    Removes internal index columns (``Unnamed: 0``) and rows where the
    ``Sequence`` column is missing or blank.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Cleaned ``DataFrame`` ready for sequence similarity computation.
    """
    db_df = pd.read_csv(csv_path)
    # Remove internal index column if present.
    db_df = db_df.drop(columns=[c for c in _EXCLUDE_COLS if c in db_df.columns])

    # Drop rows with missing sequences.
    db_df = db_df.dropna(subset=[_COL_SEQUENCE])
    db_df = db_df[db_df[_COL_SEQUENCE].str.strip().astype(bool)]

    return db_df


def get_ec_numbers(csv_path):
    """Extract sorted unique EC numbers from a sequence database CSV.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Sorted list of unique EC number strings found in the file.
    """
    db_df = pd.read_csv(csv_path, usecols=[_COL_EC_NUMBER])
    ec_values = db_df[_COL_EC_NUMBER].dropna().unique()
    return sorted(str(ec) for ec in ec_values if str(ec).strip())


def load_and_clean_data(csv_path):
    """Read a reaction CSV and drop unusable rows.

    Removes internal index columns (``Unnamed: 0``) and rows where the
    ``unmapped`` SMILES column is missing or blank.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Cleaned ``DataFrame`` ready for similarity computation.
    """
    db_df = pd.read_csv(csv_path)
    # Remove internal index column if present
    db_df = db_df.drop(columns=[c for c in _EXCLUDE_COLS if c in db_df.columns])

    # Drop rows with missing SMILES
    db_df = db_df.dropna(subset=[_COL_UNMAPPED_SMILES])
    db_df = db_df[db_df[_COL_UNMAPPED_SMILES].str.strip().astype(bool)]

    return db_df


def get_top_n_sorted_results(df, sort_column, top_n):
    """Sort a DataFrame by a similarity column and return the top-N rows.

    Args:
        df: Combined results DataFrame.
        sort_column: Column name to sort by (descending).
        top_n: Maximum number of rows to return.

    Returns:
        DataFrame with up to *top_n* rows, sorted by *sort_column*
        in descending order.
    """
    sorted_df = df.sort_values(by=sort_column, ascending=False)
    return sorted_df.head(min(top_n, len(sorted_df)))
