"""Compute function for the Sequence Similarity tool.

Loads the selected protein sequence database, applies EC number and
cofactor pre-filters, then runs ``enzymetk.sequence_search_blast.BLAST``
to find the most similar sequences.

**The two pre-filters read their columns differently, and must.**  An
``EC number`` cell holds atomic tokens separated by ``;`` (``"3.2.2.-; 3.2.2.6"``),
so splitting on ``;`` is the whole parse.  A ``Cofactor`` cell is a UniProt
annotation blob where ``;`` also separates ``Xref=``, ``Evidence=`` and ``Note=``
sub-fields *and* successive ``COFACTOR:`` blocks — only its ``Name=`` values are
cofactors, and ``extract_cofactor_names()`` is the one parser for them, shared with
the dropdown that offers those names.  Each filter keeps a row that carries *any*
selected value; a row whose cell is blank — or whose database has no ``Cofactor``
column at all, since ``Cofactor`` is optional metadata — lists nothing and so
survives no filter.

.. note::

   The BLAST function requires the **diamond** binary to be available
   in ``$PATH``.  In the Docker-based deployment this is installed in
   the worker image (see ``Dockerfile``).  Running locally without
   diamond will raise an error at execution time.
"""

import time
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.paths import SEQUENCES_DIR
from enzyme_tk_app.app.utils.columns import (
    COL_BITSCORE,
    COL_COFACTOR,
    COL_DATABASE,
    COL_EC_NUMBER,
    COL_ENTRY,
    COL_QUERY,
    COL_SEQUENCE,
    COL_TARGET,
)
from enzyme_tk_app.app.utils.data_loading import (
    extract_cofactor_names,
    load_sequence_data,
    scan_sequence_databases,
)


def _database_cards(searched: int, total_sequences: int, skipped: list[str]) -> list[dict]:
    """Return the database-related stat cards, shared by every return path.

    A skipped database gets its own card naming the files, so a partial
    search is never mistaken for a complete one.
    """
    cards = [
        {"label": "Databases Searched", "value": str(searched)},
        {"label": "Total Sequences", "value": f"{total_sequences:,}"},
    ]
    if skipped:
        cards.append({"label": "Databases Skipped", "value": ", ".join(skipped)})
    return cards


def run(params: dict) -> dict:
    """Run the sequence similarity BLAST search.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"databases"`` (list[str]): database filenames to search.  All
              selections are merged into one reference set and ranked
              together; unreadable ones are skipped and reported.
            - ``"sequence"`` (str): query protein sequence.
            - ``"ec_filter"`` (list[str]): EC numbers to pre-filter
              the database (empty list means no filter).
            - ``"cofactor_filter"`` (list[str]): cofactor names to
              pre-filter the database (empty list means no filter).
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
        ValueError: When none of the selected databases can be read.
        ImportError: When ``enzymetk.sequence_search_blast`` or the
            diamond binary is not available.
    """
    # Lazy import — enzymetk + diamond are heavy; only load in the worker.
    from enzymetk.sequence_search_blast import BLAST  # noqa: PLC0415

    databases: list[str] = params["databases"]
    query_sequence: str = params["sequence"]
    ec_filter: list[str] = params.get("ec_filter", [])
    cofactor_filter: list[str] = params.get("cofactor_filter", [])
    top_n: int = max(1, min(500, int(params["top_n"])))
    predict_catalytic: bool = params.get("predict_catalytic", False)

    if not databases:
        raise ValueError("At least one database must be selected.")

    run_time_start = time.monotonic()

    # ------------------------------------------------------------------
    # Load and merge the selected databases
    # ------------------------------------------------------------------
    # Every selection is loaded and tagged with its source, then concatenated
    # into one reference set.  BLAST then builds a single index over the union
    # rather than one per database, and the bitscore ranking below is global.
    # An unreadable database is skipped (and reported) rather than failing the
    # whole run — but if none survive, that is an error, not "no hits".
    # The worker reads params straight out of Redis, so it re-derives the set of
    # usable databases itself rather than trusting the submit callback's check.
    usable, _problems = scan_sequence_databases()
    usable_names = set(usable)

    frames = []
    databases_skipped: list[str] = []
    for name in databases:
        # Sanitise client-supplied filename: strip directory components so a
        # name can never escape data/sequences/.
        safe_name = Path(name).name
        # Skipped names carry the same spelling as every other surface: the
        # filename exactly as it appears in data/sequences/, extension included.
        # A name that is not currently a compliant database — deleted since
        # submission, or never one — is skipped rather than failing the run.
        if safe_name not in usable_names:
            databases_skipped.append(safe_name)
            continue
        db_path = SEQUENCES_DIR / safe_name
        frame = load_sequence_data(db_path)
        # Named exactly as the file is named in data/sequences/ — see the
        # data_loading module docstring.
        frame[COL_DATABASE] = db_path.name
        frames.append(frame)

    if not frames:
        raise ValueError(f"None of the selected databases could be read: {', '.join(databases_skipped)}")

    db_df = pd.concat(frames, ignore_index=True)
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

    # Reduce each raw UniProt annotation blob to its "Name=" values once — the
    # filter matches on them and the grid shows them.  A database with no Cofactor
    # column lists no cofactors, so none of its rows match once a filter is active:
    # the same rule as a blank cell, and the reason this cannot use .isin().
    has_cofactors = COL_COFACTOR in db_df.columns
    cofactor_names = (
        db_df[COL_COFACTOR].map(extract_cofactor_names)
        if has_cofactors
        else pd.Series([set()] * len(db_df), index=db_df.index)
    )
    if has_cofactors:
        # "; " is the source file's own separator and no cofactor name contains one —
        # unlike ", ", which is ambiguous inside "6,7-dimethyl-8-(1-D-ribityl)lumazine".
        db_df[COL_COFACTOR] = cofactor_names.map(lambda names: "; ".join(sorted(names)))

    # Pre-filter by cofactor if the user selected any — a row survives when it lists
    # *any* of them, matching how the EC filter above treats a multi-selection.
    if cofactor_filter:
        wanted = set(cofactor_filter)
        db_df = db_df[cofactor_names.map(lambda names: bool(wanted & names))]

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
            f"No sequences in the selected database(s) matched the filter(s) "
            f"({'; '.join(active_filters)}). Try broadening or removing the filter."
        )
        return {
            "_stat_cards": [
                *_database_cards(len(frames), total_db_size, databases_skipped),
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
                *_database_cards(len(frames), total_db_size, databases_skipped),
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
        # One row per (entry, source database): a repeated Entry inside a
        # single CSV would otherwise multiply every hit row on merge.
        meta_df = meta_df.drop_duplicates(subset=[COL_ENTRY, COL_DATABASE])
        result_df = result_df.merge(meta_df, left_on=COL_TARGET, right_on=COL_ENTRY, how="left")

    # Drop the join artifacts, and only those — every remaining column is
    # database metadata and reaches the results grid:
    # - query: always the literal string "query" in every row.
    # - Entry: duplicate of "target" (the merge join key).
    # - _LABEL_COL: internal label that may have leaked through.
    result_df = result_df.drop(columns=[COL_QUERY, COL_ENTRY, _LABEL_COL], errors="ignore")

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
            *_database_cards(len(frames), total_db_size, databases_skipped),
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
