"""Data availability check for the sequence-structure-similarity tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.paths import FOLDSEEK_DB_DIR, FOLDSEEK_WEIGHTS_DIR


def _has_subdirectory(path) -> bool:
    """Return True if ``path`` exists and contains at least one non-hidden subdir."""
    if not path.exists():
        return False
    for entry in path.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            return True
    return False


def _has_any_file(path) -> bool:
    """Return True if ``path`` exists and contains at least one non-hidden entry."""
    if not path.exists():
        return False
    for entry in path.iterdir():
        if not entry.name.startswith("."):
            return True
    return False


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = OK).

    The sequence-structure-similarity tool requires both a populated
    FoldSeek database directory and a populated ProstT5 model weights
    directory.

    Returns:
        A list of 0–2 labels naming the missing items.
    """
    missing: list[str] = []
    # make sure required data directories/files exist
    if not _has_subdirectory(FOLDSEEK_DB_DIR):
        missing.append("FoldSeek databases (data/foldseek_db/)")

    # make sure prostT5 model weights exist
    if not _has_any_file(FOLDSEEK_WEIGHTS_DIR):
        missing.append("ProstT5 model weights (data/foldseek_models/weights/)")
    return missing
