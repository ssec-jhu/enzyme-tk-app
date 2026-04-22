"""Compute function for the Sequence Similarity tool.

Loads the selected protein sequence database, applies EC number and
cofactor pre-filters, then runs ``enzymetk.sequence_search_blast.BLAST``
to find the most similar sequences.

.. note::

   The BLAST function requires the **diamond** binary to be available
   in ``$PATH``.  In the Docker-based deployment this is installed in
   the worker image (see ``Dockerfile``).  Running locally without
   diamond will raise an error at execution time.
"""

import time
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.utils.columns import (
    COL_BITSCORE,
    COL_COFACTOR,
    COL_EC_NUMBER,
    COL_ENTRY,
    COL_QUERY,
    COL_RESIDUE_0INDEX,
    COL_SEQUENCE,
    COL_TARGET,
)
from enzyme_tk_app.app.utils.data_loading import (
    DATA_DIR,
    load_sequence_data,
)


def run(params: dict) -> dict:
    """Run the sequence similarity BLAST search.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"database"`` (str): CSV filename to search.
            - ``"sequence"`` (str): query protein sequence.
            - ``"ec_filter"`` (list[str]): EC numbers to pre-filter
              the database (empty list means no filter).
            - ``"cofactor_filter"`` (list[str]): cofactor values to
              pre-filter (empty list means no filter).  The column
              does not exist yet — this is a placeholder.
            - ``"top_n"`` (int): max number of results to return.
            - ``"predict_catalytic"`` (bool): whether to run catalytic
              residue prediction on the results.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``catalytic_prediction``: prediction string or ``None``.
        - ``no_results_message`` (optional): human-readable explanation
          when no results are found (filters eliminated all rows or
          BLAST found no alignments).
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When the database file is missing.
        ImportError: When ``enzymetk.sequence_search_blast`` or the
            diamond binary is not available.
    """
    # Lazy import — enzymetk + diamond are heavy; only load in the worker.
    from enzymetk.sequence_search_blast import BLAST  # noqa: PLC0415

    database_filename: str = params["database"]
    query_sequence: str = params["sequence"]
    ec_filter: list[str] = params.get("ec_filter", [])
    cofactor_filter: list[str] = params.get("cofactor_filter", [])
    top_n: int = int(params["top_n"])
    predict_catalytic: bool = params.get("predict_catalytic", False)

    run_time_start = time.monotonic()

    # ------------------------------------------------------------------
    # Load and pre-filter the database
    # ------------------------------------------------------------------
    # Sanitise client-supplied filename: strip directory components
    # to prevent path-traversal and enforce a .csv suffix.
    safe_name = Path(database_filename).name
    if not safe_name.endswith(".csv"):
        raise ValueError(f"Invalid database filename (must be .csv): {database_filename}")
    csv_path = DATA_DIR / "sequences" / safe_name
    if not csv_path.exists():
        raise ValueError(f"Database file not found: {safe_name}")

    db_df = load_sequence_data(csv_path)
    total_db_size = len(db_df)

    # Pre-filter by EC number if the user selected any.
    # Cells may contain semicolon-separated EC numbers (e.g. "3.2.2.-; 3.2.2.6"),
    # so we split each cell and check for overlap with the selected filter set.
    if ec_filter:
        ec_set = set(ec_filter)
        mask = (
            db_df[COL_EC_NUMBER]
            .fillna("")
            .apply(lambda cell: bool(ec_set & {part.strip() for part in str(cell).split(";")}))
        )
        db_df = db_df[mask]

    # Pre-filter by cofactor if the column exists and filters are given.
    # The "cofactor" column does not exist in the current CSV but will
    # be added in a future data update.
    if cofactor_filter and COL_COFACTOR in db_df.columns:
        db_df = db_df[db_df[COL_COFACTOR].isin(cofactor_filter)]

    filtered_size = len(db_df)

    if filtered_size == 0:
        run_time = round(time.monotonic() - run_time_start, 3)
        # Build a human-readable explanation of which filters eliminated all rows.
        active_filters: list[str] = []
        if ec_filter:
            active_filters.append(f"EC number(s): {', '.join(ec_filter)}")
        if cofactor_filter:
            active_filters.append(f"Cofactor(s): {', '.join(cofactor_filter)}")
        no_results_message = (
            f"No sequences in the database matched the selected filter(s) "
            f"({'; '.join(active_filters)}). Try broadening or removing the filter."
            if active_filters
            else "No sequences remained after filtering."
        )
        return {
            "_stat_cards": [
                {"label": "Database", "value": database_filename},
                {"label": "Total Sequences", "value": f"{total_db_size:,}"},
                {"label": "After Filtering", "value": "0"},
                {"label": "Results Returned", "value": "0"},
                {"label": "Run Time", "value": f"{run_time}s"},
            ],
            "catalytic_prediction": None,
            "no_results_message": no_results_message,
            "dataframe": {"columns": [], "data": []},
        }

    # ------------------------------------------------------------------
    # Run BLAST via enzymetk
    # ------------------------------------------------------------------
    # BLAST uses a label column to distinguish "query" vs "reference"
    # rows in a single DataFrame.  We build a combined frame with the
    # user's query sequence on top and the database rows below.
    _LABEL_COL = "_blast_role"
    query_row = pd.DataFrame([{COL_ENTRY: "query", COL_SEQUENCE: query_sequence, _LABEL_COL: "query"}])
    ref_df = db_df.copy()
    ref_df[_LABEL_COL] = "reference"
    combined_df = pd.concat([query_row, ref_df], ignore_index=True)

    blast = BLAST(
        id_col=COL_ENTRY,
        sequence_col=COL_SEQUENCE,
        label_col=_LABEL_COL,
    )

    # BLAST may find zero alignments (e.g. when the query sequence is
    # unrelated to all entries in the filtered database).  enzymetk
    # raises EmptyDataError in that case — handle it gracefully.
    try:
        result_df = blast.execute(combined_df)
    except pd.errors.EmptyDataError:
        run_time = round(time.monotonic() - run_time_start, 3)
        return {
            "_stat_cards": [
                {"label": "Database", "value": database_filename},
                {"label": "Total Sequences", "value": f"{total_db_size:,}"},
                {"label": "After Filtering", "value": f"{filtered_size:,}"},
                {"label": "Results Returned", "value": "0"},
                {"label": "Run Time", "value": f"{run_time}s"},
            ],
            "catalytic_prediction": None,
            "no_results_message": (
                "BLAST found no alignments between the query sequence and "
                f"the {filtered_size:,} sequence(s) in the filtered database. "
                "Try broadening the filter or using a different query sequence."
            ),
            "dataframe": {"columns": [], "data": []},
        }

    # Sort by bitscore descending (best hits first) and take top-N.
    if COL_BITSCORE in result_df.columns:
        result_df = result_df.sort_values(by=COL_BITSCORE, ascending=False)
    result_df = result_df.head(min(top_n, len(result_df)))

    # Merge database metadata back onto the BLAST hits via the target ID.
    # The BLAST output has a "target" column containing the Entry IDs.
    if COL_TARGET in result_df.columns:
        meta_df = db_df.drop(columns=[_LABEL_COL], errors="ignore")
        result_df = result_df.merge(meta_df, left_on=COL_TARGET, right_on=COL_ENTRY, how="left")

    # Drop columns that add no value to the consumer:
    # - query: always the literal string "query" in every row.
    # - Entry: duplicate of "target" (the merge join key).
    # - Residue_0index: redundant with Residue_1index.
    # - _LABEL_COL: internal label that may have leaked through.
    result_df = result_df.drop(
        columns=[COL_QUERY, COL_ENTRY, COL_RESIDUE_0INDEX, _LABEL_COL],
        errors="ignore",
    )

    # ------------------------------------------------------------------
    # Catalytic residue prediction (placeholder)
    # ------------------------------------------------------------------
    catalytic_prediction = None
    if predict_catalytic:
        # TODO: Replace with actual catalytic residue prediction call
        # once the function is available in enzymetk.
        catalytic_prediction = "Catalytic predictions here"

    run_time = round(time.monotonic() - run_time_start, 3)

    return {
        "_stat_cards": [
            {"label": "Database", "value": database_filename},
            {"label": "Total Sequences", "value": f"{total_db_size:,}"},
            {"label": "After Filtering", "value": f"{filtered_size:,}"},
            {"label": "Results Returned", "value": str(len(result_df))},
            {"label": "Run Time", "value": f"{run_time}s"},
        ],
        "catalytic_prediction": catalytic_prediction,
        "dataframe": {
            "columns": result_df.columns.tolist(),
            "data": result_df.to_dict(orient="records"),
        },
    }
