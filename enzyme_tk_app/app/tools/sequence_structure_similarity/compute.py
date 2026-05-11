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
import tempfile
import time
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.paths import FOLDSEEK_DB_DIR, FOLDSEEK_WEIGHTS_DIR


def _decode_structure_file(structure_content: str, structure_filename: str, tmpdir: str) -> str:
    """Decode a base64-encoded structure file into *tmpdir*.

    The ``dcc.Upload`` component sends file contents as a
    ``data:<mimetype>;base64,<payload>`` string.  This function strips
    the prefix, decodes the payload, and writes it into the given
    temporary directory.  Cleanup is the caller's responsibility
    (via the ``TemporaryDirectory`` context manager).

    Args:
        structure_content: The full data-URI string from dcc.Upload.
        structure_filename: The original filename (used for the suffix).
        tmpdir: Path to a temporary directory that the caller manages.

    Returns:
        Absolute path to the file written inside *tmpdir*.
    """
    # Strip the data-URI prefix (e.g. "data:application/octet-stream;base64,").
    if "," in structure_content:
        payload = structure_content.split(",", 1)[1]
    else:
        payload = structure_content

    try:
        raw_bytes = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise ValueError("Uploaded structure file contains invalid base64 data.") from exc

    # Use the original filename's suffix for the temp file, so FoldSeek can detect the format.
    suffix = Path(structure_filename).suffix.lower()
    dest = Path(tmpdir) / f"query_structure{suffix}"
    dest.write_bytes(raw_bytes)
    return str(dest)


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
    from enzymetk.similarity_sequence_and_structure_step import FoldSeek, FoldSeekDatabase  # noqa: PLC0415

    # extract the parameters sent from the UI
    query_sequence: str = params["sequence"]
    database_names: list[str] = params.get("databases", [])
    structure_content: str | None = params.get("structure_content")
    structure_filename: str | None = params.get("structure_filename")

    if not query_sequence:
        raise ValueError("A query sequence must be provided.")

    if not database_names:
        raise ValueError("At least one database must be selected.")

    run_time_start = time.monotonic()

    # TemporaryDirectory guarantees cleanup even on partial failures;
    # the temp file for the uploaded structure lives inside it.
    with tempfile.TemporaryDirectory() as tmpdir:
        # ------------------------------------------------------------------
        # Determine mode & prepare structure file
        # ------------------------------------------------------------------
        is_structure_mode = structure_content is not None and structure_filename is not None
        tmp_structure_path: str | None = None
        if is_structure_mode:
            # Decode the uploaded structure file into the managed temp dir.
            tmp_structure_path = _decode_structure_file(structure_content, structure_filename, tmpdir)

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

        # FoldSeek expects a DataFrame input, even for a single query.
        # Build a one-row DataFrame.
        df = pd.DataFrame([row])

        # ------------------------------------------------------------------
        # Map database names to enums / strings
        # ------------------------------------------------------------------
        # FoldSeek accepts a list of database names as strings, or as members of the FoldSeekDatabase enum.
        # Here we convert any names that match enum members to the enum values, while leaving any custom names as-is.
        databases = [FoldSeekDatabase[n] if n in FoldSeekDatabase.__members__ else n for n in database_names]

        # ------------------------------------------------------------------
        # Initialize and execute FoldSeek
        # ------------------------------------------------------------------
        foldseek_kwargs: dict = {
            "id_column_name": "Entry",
            "sequence_column_name": "Sequence",
            "prostt5_weights_path": str(FOLDSEEK_WEIGHTS_DIR),
            "databases": databases,
            "database_root_path": str(FOLDSEEK_DB_DIR),
            "label_column_name": "label",
        }
        if is_structure_mode:
            foldseek_kwargs["structure_column_name"] = "structure"

        # make the enzymetk FoldSeek step and execute it on the query DataFrame
        step = FoldSeek(**foldseek_kwargs)
        result_df = step.execute(df)

        # Record the run time after FoldSeek execution completes.
        run_time = round(time.monotonic() - run_time_start, 3)

        # ------------------------------------------------------------------
        # Handle empty results
        # ------------------------------------------------------------------
        if result_df.empty:
            mode_label = "Structure" if is_structure_mode else "Sequence"
            return {
                # additional stat card showing the databases searched and the mode
                # (sequence vs structure) even when there are no hits, for better user feedback
                "_stat_cards": [
                    {"label": "Mode", "value": mode_label},
                    {"label": "Databases", "value": ", ".join(database_names)},
                    {"label": "Hits Found", "value": "0"},
                    {"label": "Run Time", "value": f"{run_time}s"},
                ],
                # don't show the structure content in the params table,
                # to avoid cluttering it with a large base64 string, even when there are no results
                "_params_exclude": ["structure_content"],
                # user-friendly message when no hits are found, including the mode
                # and databases searched for better feedback
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

        # count unique databases in the results if the 'database' column is present;
        # otherwise, use the number of databases searched
        db_count = result_df["database"].nunique() if "database" in result_df.columns else len(database_names)

        return {
            # additional stat card showing the databases searched and the mode (sequence vs structure)
            "_stat_cards": [
                {"label": "Mode", "value": mode_label},
                {"label": "Databases Searched", "value": str(db_count)},
                {"label": "Hits Found", "value": str(len(result_df))},
                {"label": "Run Time", "value": f"{run_time}s"},
            ],
            # exclude the structure content from the params table, to avoid cluttering it with a large base64 string
            "_params_exclude": ["structure_content"],
            # main result payload: the DataFrame of hits, converted to a dict with 'columns' and 'data' for the UI table
            "dataframe": {
                "columns": result_df.columns.tolist(),
                "data": result_df.to_dict(orient="records"),
            },
        }
