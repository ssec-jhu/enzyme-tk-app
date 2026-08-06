"""Data file discovery, dropdown-option builders, and name validation.

These helpers scan the ``data/`` directories and return option lists
suitable for Dash dropdown components, plus the shared validator every
tool uses on the database names that come back from those dropdowns.

**A database is named on screen exactly as it is named in ``data/``** —
extension included: ``Funce_pairs.pkl`` shows as ``Funce_pairs.pkl``, and the
FoldSeek folder ``AFDB_SWISSPROT`` as ``AFDB_SWISSPROT`` (a directory, so it has
no extension to show).  Every option ``label`` here, every ``database`` column
value, every "Databases Skipped" card, and the Input Parameters row use that one
spelling, so a scientist can match what the app shows against what is on disk.
Do not prettify it and do not strip the suffix.

**What makes a file a sequence database.**  A file in ``data/sequences/`` is a
sequence database when it is a delimited table — CSV or TSV, plain or gzipped
(:data:`SEQUENCE_DB_SUFFIXES`) — carrying all of
:data:`REQUIRED_SEQUENCE_COLUMNS`: ``Entry``, ``Sequence`` and ``EC number``.
Every other column is metadata: the app never enumerates it, and it rides
through the search into the results grid untouched.  The contract is the
extension *and* the header, never the extension alone — a file that does not
meet it is not offered in any dropdown, and
:func:`scan_sequence_databases` says why so the home-page card can show it.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.paths import FOLDSEEK_DB_DIR, REACTIONS_DIR, SEQUENCE_EMBEDDINGS_DIR, SEQUENCES_DIR
from enzyme_tk_app.app.utils.columns import (
    COL_EC_NUMBER,
    COL_ENTRY,
    COL_MOL_INDEX,
    COL_MOL_SMILES,
    COL_MOL_SVG,
    COL_SEQUENCE,
    COL_UNMAPPED_SMILES,
    EXCLUDE_COLS,
)

# Re-export column constants under their original private names so that
# existing import sites (``from data_loading import _COL_…``) keep working
# until they are migrated.  New code should import from ``columns.py``.
_COL_UNMAPPED_SMILES = COL_UNMAPPED_SMILES
_COL_MOL_SMILES = COL_MOL_SMILES
_COL_MOL_INDEX = COL_MOL_INDEX
_COL_MOL_SVG = COL_MOL_SVG
_EXCLUDE_COLS = EXCLUDE_COLS
_COL_EC_NUMBER = COL_EC_NUMBER
_COL_SEQUENCE = COL_SEQUENCE
_COL_ENTRY = COL_ENTRY


SEQUENCE_DB_SUFFIXES = (".csv", ".tsv", ".csv.gz", ".tsv.gz")
"""File extensions a ``data/sequences/`` database may carry — see the module docstring."""

REQUIRED_SEQUENCE_COLUMNS = (COL_ENTRY, COL_SEQUENCE, COL_EC_NUMBER)
"""Columns a sequence database must have.  Everything else in the file is metadata."""


def validate_db_names(names: list[str] | None, options: list[dict]) -> str | None:
    """Validate database names selected in a tool modal.

    Every tool calls this in its submit callback on the values coming back
    from a database dropdown.  Those values originate in the browser and are
    used to build a filesystem path, so they are checked at this trust
    boundary even though the UI only ever offers legitimate options.

    The check is membership in *options* — the same list the tool's
    ``get_*_database_options()`` builder just produced.  An exact allowlist is
    stronger than a pattern: there is no traversal to match and no second
    extension to smuggle, and a database the builder filtered out (a
    non-compliant sequence file, say) is rejected here for free.

    Mirrors :func:`enzyme_tk_app.app.utils.formatting.validate_top_n` — the
    caller returns the message straight into the modal's results div.  Nothing
    is modified: an invalid name is rejected, never repaired.

    Args:
        names: Selected database names, as sent by the dropdown.
        options: The tool's dropdown options, as ``{"label": …, "value": …}``
            dicts.  Only ``value`` is read.

    Returns:
        An error message string if validation fails, or ``None`` when every
        name is one the tool currently offers.
    """
    # A bare string is iterable, so without this it would be validated one
    # character at a time and silently pass.  A single-select dropdown returns
    # a string, so this is a live foot-gun, not a theoretical one — but the
    # value comes from the browser, so it is reported like any other bad input.
    # Raising here would surface as an HTTP 500 on /_dash-update-component,
    # since the app installs no Dash ``on_error`` handler.
    if isinstance(names, str):
        return f"Expected a list of database names, got a single name: {names}"

    if not names:
        return "At least one database must be selected."

    allowed = {opt["value"] for opt in options}
    for name in names:
        # A crafted request can put anything in the list, so the isinstance
        # check comes first — an unhashable item would otherwise raise on the
        # set lookup and surface as a 500 instead of a validation message.
        if not isinstance(name, str) or name not in allowed:
            return f"Unknown database: {name!r}"

    return None


def sequence_db_separator(path: Path) -> str:
    """Return the column separator for a sequence database file.

    The extension decides — no sniffing.  ``pandas`` infers gzip from the
    ``.gz`` suffix on its own, so a compressed file needs nothing extra.
    """
    name = path.name.removesuffix(".gz")
    return "\t" if name.endswith(".tsv") else ","


@lru_cache(maxsize=64)
def _read_header(path_str: str, mtime: float, size: int) -> tuple[str, ...]:
    """Read just the column names of a delimited file, cached on file identity.

    Reading a header is ``nrows=0``, so this touches only the first line even
    of the 812 MB ``enzymes.tsv``.  It is still cached because
    :func:`scan_sequence_databases` runs on every home-page render, once per
    file.  *mtime* and *size* are part of the key rather than the body: a
    re-dropped or edited database invalidates its own entry, so a new file is
    picked up without an app restart.
    """
    path = Path(path_str)
    frame = pd.read_csv(path, sep=sequence_db_separator(path), nrows=0)
    # Tuple, not list — a cached value must not be mutable by its callers.
    return tuple(frame.columns)


def scan_sequence_databases() -> tuple[list[str], list[str]]:
    """Split ``data/sequences/`` into usable databases and problems.

    A file qualifies when its extension is in :data:`SEQUENCE_DB_SUFFIXES` and
    its header carries every one of :data:`REQUIRED_SEQUENCE_COLUMNS`.  One
    scan serves both consumers — the dropdown builder takes the names, the
    tool's ``check_data()`` takes the problems.

    Returns:
        ``(names, problems)``.  *names* are compliant filenames, sorted, spelled
        exactly as they are on disk.  *problems* are human-readable lines such
        as ``"badfile.csv — missing columns: Sequence, EC number"``, ready to
        list in the home-page data-warning tooltip.
    """
    names: list[str] = []
    problems: list[str] = []
    if not SEQUENCES_DIR.exists():
        return names, problems

    for path in sorted(SEQUENCES_DIR.iterdir()):
        if not path.is_file() or not path.name.endswith(SEQUENCE_DB_SUFFIXES):
            continue
        try:
            # mtime and size are the cache key, so they are read here rather
            # than inside _read_header — see its docstring.
            stat = path.stat()
            columns = _read_header(str(path), stat.st_mtime, stat.st_size)
        # A database is user-supplied data, so anything from a truncated gzip
        # to a binary file lands here.  It is a problem to report, not a crash.
        except (OSError, UnicodeDecodeError, ValueError, pd.errors.ParserError):
            problems.append(f"{path.name} — could not be read")
            continue

        missing = [c for c in REQUIRED_SEQUENCE_COLUMNS if c not in columns]
        if missing:
            problems.append(f"{path.name} — missing columns: {', '.join(missing)}")
            continue

        # Named exactly as it is on disk — see the module docstring.
        names.append(path.name)

    return names, problems


def get_foldseek_database_options():
    """Scan the data/foldseek_db directory and return dropdown options.

    Each subdirectory under ``foldseek_db/`` represents a pre-built
    FoldSeek database.  Hidden directories, ``.DS_Store``, and ``tmp/``
    are excluded.

    Returns:
        List of dicts whose ``label`` and ``value`` are both the exact folder
        name (the value is also what maps to the FoldSeekDatabase enum).
    """
    db_dir = FOLDSEEK_DB_DIR
    options = []
    if db_dir.exists():
        # Sort entries alphabetically for consistent dropdown order.
        for entry in sorted(db_dir.iterdir()):
            if not entry.is_dir():
                continue

            # Use the folder name as the value
            name = entry.name

            # Skip hidden directories and common temp files.
            if name.startswith(".") or name == "tmp":
                continue

            # The folder name is shown as-is — see the module docstring.
            options.append({"label": name, "value": name})
    return options


def get_reaction_database_options():
    """Scan the data/reactions directory and return dropdown options.

    Returns:
        List of dicts whose 'label' and 'value' are both the full filename.
    """
    reactions_dir = REACTIONS_DIR
    options = []
    if reactions_dir.exists():
        for f in sorted(reactions_dir.glob("*.csv")):
            options.append({"label": f.name, "value": f.name})
    return options


def get_sequence_database_options():
    """Scan the data/sequences directory and return dropdown options.

    Offers only files that meet the sequence-database contract — see the
    module docstring.  A file that does not is not a database, so it is not
    offered; ``check_data()`` reports it on the tool's home-page card instead.

    Returns:
        List of dicts whose 'label' and 'value' are both the full filename.
    """
    names, _problems = scan_sequence_databases()
    return [{"label": name, "value": name} for name in names]


def get_sequence_embedding_database_options():
    """Scan the data/sequence_embeddings directory and return dropdown options.

    Each pickle is a pre-encoded protein table (``Entry``, ``Sequence`` and the
    embedding columns a scoring step needs).

    Unlike :func:`scan_sequence_databases`, this does **not** check the columns.
    A pickle has no header-only read, so validating here would deserialise every
    embedding table on every page render — cheap for a 68 KB file, seconds and
    gigabytes for a real ESM3 table.  A malformed pickle is skipped and named at
    run time instead (``create-tool`` §3b.5).

    Returns:
        List of dicts whose 'label' and 'value' are both the full filename.
    """
    options = []
    if SEQUENCE_EMBEDDINGS_DIR.exists():
        for f in sorted(SEQUENCE_EMBEDDINGS_DIR.glob("*.pkl")):
            options.append({"label": f.name, "value": f.name})
    return options


def load_sequence_data(path):
    """Read a sequence database and drop unusable rows.

    Removes internal index columns (``Unnamed: 0``) and rows where the
    ``Sequence`` column is missing or blank.  Every other column is kept —
    it is metadata, and it rides through to the results grid.

    Args:
        path: Path to the database file (CSV or TSV, plain or gzipped).

    Returns:
        Cleaned ``DataFrame`` ready for sequence similarity computation.
    """
    db_df = pd.read_csv(path, sep=sequence_db_separator(path))
    # Remove internal index column if present.
    db_df = db_df.drop(columns=[c for c in _EXCLUDE_COLS if c in db_df.columns])

    # Drop rows with missing sequences.
    db_df = db_df.dropna(subset=[_COL_SEQUENCE])
    db_df = db_df[db_df[_COL_SEQUENCE].str.strip().astype(bool)]

    return db_df


@lru_cache(maxsize=64)
def _scan_ec_numbers(path_str: str, mtime: float, size: int) -> tuple[str, ...]:
    """Read the EC column of one database, cached on file identity.

    Cached because ``populate_ec_options`` has no ``prevent_initial_call`` and
    its dropdown defaults to every database selected — so this runs in the
    *web* process on every page load, once per selected file, and a full-column
    read of ``enzymes.tsv`` is ~1.7 s.  Keyed like :func:`_read_header`, so a
    re-dropped database is rescanned without an app restart.
    """
    path = Path(path_str)
    db_df = pd.read_csv(path, sep=sequence_db_separator(path), usecols=[_COL_EC_NUMBER])
    ec_series = db_df[_COL_EC_NUMBER].dropna()
    unique_ecs = set()
    for cell in ec_series:
        # A cell may hold several EC numbers (e.g. "3.2.2.-; 3.2.2.6").
        for part in str(cell).split(";"):
            part = part.strip()
            if part:
                unique_ecs.add(part)
    # Tuple, not list — a cached value must not be mutable by its callers.
    return tuple(sorted(unique_ecs))


def get_ec_numbers(path):
    """Extract sorted unique EC numbers from a sequence database.

    Cells may contain multiple EC numbers separated by semicolons
    (e.g. ``"3.2.2.-; 3.2.2.6"``).  Each individual EC number is
    extracted and returned as a separate entry.

    Args:
        path: Path to the database file (CSV or TSV, plain or gzipped).

    Returns:
        Sorted list of unique EC number strings found in the file.
    """
    stat = path.stat()
    return list(_scan_ec_numbers(str(path), stat.st_mtime, stat.st_size))


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
