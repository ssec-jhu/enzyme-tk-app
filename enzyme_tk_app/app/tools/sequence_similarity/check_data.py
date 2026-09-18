"""Data availability check for the sequence-similarity tool.

Two channels, per the contract in ``tools/__init__.py``: ``check_data()`` names
what the tool cannot run without, ``check_data_warnings()`` names what is present
but unusable while the tool still works.  This is the only tool that needs both —
one malformed file beside a good one leaves the tool perfectly runnable.
"""

from enzyme_tk_app.app.utils.data_loading import scan_sequence_databases


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = the tool can run).

    The tool needs at least one file under ``data/sequences/`` that meets the
    sequence-database contract — a CSV or TSV (plain or gzipped) with ``Entry``,
    ``Sequence`` and ``EC number``.  One usable file is enough, so a directory
    holding a good database beside a malformed one is not missing anything; the
    malformed file is reported by :func:`check_data_warnings` instead.

    Returns:
        A single label when no file in the directory is a usable database;
        otherwise an empty list.
    """
    names, _problems = scan_sequence_databases()
    if names:
        return []
    return ["Sequence databases (data/sequences/*.csv, *.tsv) with columns Entry, Sequence, EC number"]


def check_data_warnings() -> list[str]:
    """Return one line per file in ``data/sequences/`` that is not a database.

    A non-compliant file is not offered in the dropdown, so it is named here:
    without this the scientist who dropped it in would see it silently missing
    with no explanation.  It never gates the tool — the other databases still
    search fine.

    Returns:
        Lines such as ``"badfile.csv — missing columns: EC number"``; empty when
        every file in the directory is a usable database.
    """
    # Second scan of the directory this render — ``_read_header`` is cached on
    # (path, mtime, size), so this costs one iterdir() and a stat() per file.
    # Merge the two calls only if a sequences/ directory ever grows large enough
    # to show up in a page load.
    _names, problems = scan_sequence_databases()
    return problems
