"""Utility functions for data file discovery and loading.

These helpers scan the data/ directories and return options for UI components.
"""

from pathlib import Path

# Base data directory (relative to this file)
DATA_DIR = Path(__file__).parent.parent / "data"


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

    Returns:
        List of dicts with label/value for each FASTA file found.
        Each dict has 'label' (human-readable) and 'value' (filename).
    """
    sequences_dir = DATA_DIR / "sequences"
    options = []
    if sequences_dir.exists():
        for f in sorted(sequences_dir.glob("*.fasta")):
            label = f.stem.replace("_", " ").title()
            options.append({"label": label, "value": f.name})
    return options
