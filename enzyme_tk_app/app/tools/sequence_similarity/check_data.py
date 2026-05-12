"""Data availability check for the sequence-similarity tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.paths import SEQUENCES_DIR


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = OK).

    The sequence-similarity tool requires at least one sequence database
    CSV under ``data/sequences/``.

    Returns:
        List with a single descriptive label when the directory is missing
        or contains no ``*.csv`` files; otherwise an empty list.
    """
    if not SEQUENCES_DIR.exists() or not any(SEQUENCES_DIR.glob("*.csv")):
        return ["Sequence database CSVs (data/sequences/*.csv)"]
    return []
