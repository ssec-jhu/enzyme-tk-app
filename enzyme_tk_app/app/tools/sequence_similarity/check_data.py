"""Data availability check for the sequence-similarity tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.utils.data_loading import scan_sequence_databases


def check_data() -> list[str]:
    """Return labels of missing or unusable data items (empty list = OK).

    The tool needs at least one file under ``data/sequences/`` that meets the
    sequence-database contract — a CSV or TSV (plain or gzipped) with ``Entry``,
    ``Sequence`` and ``EC number``.  A file that does not meet it is not offered
    in the dropdown, so it is named here instead: without this the scientist
    who dropped it in would see it silently missing with no explanation.

    Returns:
        A label for the missing databases when none are usable, followed by one
        line per non-compliant file naming what it is missing; empty when every
        file in the directory is a usable database.
    """
    names, problems = scan_sequence_databases()
    if names:
        return problems
    return ["Sequence databases (data/sequences/*.csv, *.tsv) with columns Entry, Sequence, EC number", *problems]
