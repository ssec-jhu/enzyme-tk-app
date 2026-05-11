"""Compute function for the Sequence & Structure-Based Similarity tool.

Runs ``enzymetk.similarity_sequence_and_structure_step.FoldSeek`` to
perform similarity searches using either protein sequences (ProstT5)
or structures (CIF/PDB files) against one or more FoldSeek databases.

.. note::

   The FoldSeek binary must be available in ``$PATH``.  In the
   Docker-based deployment this is installed in the worker image
   (see ``Dockerfile``).  ProstT5 weights must be present at the
   configured weights path.
"""

import base64
import os
import tempfile
import time

import pandas as pd

from enzyme_tk_app.app.paths import DATA_DIR, FOLDSEEK_DB_DIR

# Paths derived from the shared data directory.
_WEIGHTS_DIR = str(DATA_DIR / "foldseek_models" / "weights")
_DB_ROOT = str(FOLDSEEK_DB_DIR)


def _map_databases(database_names: list[str]) -> list:
    """Map database folder names to FoldSeekDatabase enums or plain strings.

    Known enum names (PDB, AFDB_SWISSPROT, CUSTOM) are converted to
    their ``FoldSeekDatabase`` enum values.  All other names are passed
    as plain strings, which FoldSeek resolves as named pre-built custom
    databases under ``database_root_path``.

    Args:
        database_names: List of folder names from the UI dropdown.

    Returns:
        List of ``FoldSeekDatabase`` enum values and/or plain strings.
    """
    # Lazy import — only needed in the worker.
    from enzymetk.similarity_sequence_and_structure_step import FoldSeekDatabase  # noqa: PLC0415

    enum_map = {
        "PDB": FoldSeekDatabase.PDB,
        "AFDB_SWISSPROT": FoldSeekDatabase.AFDB_SWISSPROT,
        "CUSTOM": FoldSeekDatabase.CUSTOM,
    }
    mapped: list = []
    for name in database_names:
        if name in enum_map:
            mapped.append(enum_map[name])
        else:
            mapped.append(name)
    return mapped


def _decode_structure_file(structure_content: str, structure_filename: str) -> str:
    """Decode a base64-encoded structure file and write to a temp file.

    The ``dcc.Upload`` component sends file contents as a
    ``data:<mimetype>;base64,<payload>`` string.  This function strips
    the prefix, decodes the payload, and writes it to a named temporary
    file that persists until the caller deletes it.

    Args:
        structure_content: The full data-URI string from dcc.Upload.
        structure_filename: The original filename (used for the suffix).

    Returns:
        Absolute path to the temporary file containing the structure.
    """
    # Strip the data-URI prefix (e.g. "data:application/octet-stream;base64,").
    if "," in structure_content:
        payload = structure_content.split(",", 1)[1]
    else:
        payload = structure_content

    raw_bytes = base64.b64decode(payload)

    # Determine file extension from the original filename.
    ext = ""
    if "." in structure_filename:
        ext = "." + structure_filename.rsplit(".", 1)[-1].lower()

    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        os.write(fd, raw_bytes)
    finally:
        os.close(fd)
    return tmp_path


def run(params: dict) -> dict:
    """Run the FoldSeek similarity search.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"sequence"`` (str): query protein sequence.
            - ``"databases"`` (list[str]): folder names of databases.
            - ``"structure_content"`` (str | None): base64-encoded
              CIF/PDB file from ``dcc.Upload``, or ``None`` for
              sequence-only mode.
            - ``"structure_filename"`` (str | None): original filename
              of the uploaded structure file.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``_params_exclude``: list of param keys to hide in the
          results input-params table.
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When no databases are specified.
        ImportError: When ``enzymetk`` or the foldseek binary is
            not available.
    """
    # Lazy import — FoldSeek + foldseek binary are heavy; only load in the worker.
    from enzymetk.similarity_sequence_and_structure_step import FoldSeek  # noqa: PLC0415

    query_sequence: str = params["sequence"]
    database_names: list[str] = params.get("databases", [])
    structure_content: str | None = params.get("structure_content")
    structure_filename: str | None = params.get("structure_filename")

    if not database_names:
        raise ValueError("At least one database must be selected.")

    run_time_start = time.monotonic()
    tmp_structure_path: str | None = None

    try:
        # ------------------------------------------------------------------
        # Determine mode & prepare structure file
        # ------------------------------------------------------------------
        is_structure_mode = structure_content is not None and structure_filename is not None
        if is_structure_mode:
            tmp_structure_path = _decode_structure_file(structure_content, structure_filename)

        # ------------------------------------------------------------------
        # Build single-row query DataFrame
        # ------------------------------------------------------------------
        row: dict = {
            "Entry": "query",
            "Sequence": query_sequence,
            "label": "query",
        }
        if is_structure_mode and tmp_structure_path:
            row["structure"] = tmp_structure_path

        df = pd.DataFrame([row])

        # ------------------------------------------------------------------
        # Map database names to enums / strings
        # ------------------------------------------------------------------
        databases = _map_databases(database_names)

        # ------------------------------------------------------------------
        # Initialize and execute FoldSeek
        # ------------------------------------------------------------------
        foldseek_kwargs: dict = {
            "id_column_name": "Entry",
            "sequence_column_name": "Sequence",
            "prostt5_weights_path": _WEIGHTS_DIR,
            "databases": databases,
            "database_root_path": _DB_ROOT,
            "label_column_name": "label",
        }
        if is_structure_mode:
            foldseek_kwargs["structure_column_name"] = "structure"

        step = FoldSeek(**foldseek_kwargs)
        result_df = step.execute(df)

        run_time = round(time.monotonic() - run_time_start, 3)

        # ------------------------------------------------------------------
        # Handle empty results
        # ------------------------------------------------------------------
        if result_df.empty:
            mode_label = "Structure" if is_structure_mode else "Sequence"
            return {
                "_stat_cards": [
                    {"label": "Mode", "value": mode_label},
                    {"label": "Databases", "value": ", ".join(database_names)},
                    {"label": "Hits Found", "value": "0"},
                    {"label": "Run Time", "value": f"{run_time}s"},
                ],
                "_params_exclude": ["structure_content"],
                "no_results_message": (
                    f"FoldSeek found no hits in {mode_label.lower()} mode "
                    f"against {', '.join(database_names)}. "
                    "Try different databases or a different query sequence."
                ),
                "dataframe": {"columns": [], "data": []},
            }

        # ------------------------------------------------------------------
        # Build result payload
        # ------------------------------------------------------------------
        mode_label = "Structure" if is_structure_mode else "Sequence"
        db_count = result_df["database"].nunique() if "database" in result_df.columns else len(database_names)

        return {
            "_stat_cards": [
                {"label": "Mode", "value": mode_label},
                {"label": "Databases Searched", "value": str(db_count)},
                {"label": "Hits Found", "value": str(len(result_df))},
                {"label": "Run Time", "value": f"{run_time}s"},
            ],
            "_params_exclude": ["structure_content"],
            "dataframe": {
                "columns": result_df.columns.tolist(),
                "data": result_df.to_dict(orient="records"),
            },
        }

    finally:
        # Clean up the temporary structure file.
        if tmp_structure_path and os.path.exists(tmp_structure_path):
            os.unlink(tmp_structure_path)
