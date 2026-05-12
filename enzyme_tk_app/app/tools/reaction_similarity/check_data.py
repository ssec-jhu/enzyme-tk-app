"""Data availability check for the reaction-similarity tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.paths import REACTIONS_DIR


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = OK).

    The reaction-similarity tool requires at least one reaction database
    CSV under ``data/reactions/``.

    Returns:
        List with a single descriptive label when the directory is missing
        or contains no ``*.csv`` files; otherwise an empty list.
    """
    if not REACTIONS_DIR.exists() or not any(REACTIONS_DIR.glob("*.csv")):
        return ["Reaction database CSVs (data/reactions/*.csv)"]
    return []
