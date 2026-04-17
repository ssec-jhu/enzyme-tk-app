"""Compute function for the Reaction Similarity tool.

Loads selected reaction databases, runs ``enzymetk.ReactionDist`` to
compute structural reaction fingerprint similarities, and returns the
top-N most similar reactions sorted by the user's primary algorithm.
"""

import time
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.tools.reaction_similarity import SimilarityAlgorithm
from enzyme_tk_app.app.utils.columns import COL_DATABASE, COL_RXN_SVG, COL_UNMAPPED_SMILES
from enzyme_tk_app.app.utils.data_loading import (
    DATA_DIR,
    get_top_n_sorted_results,
    load_and_clean_data,
)
from enzyme_tk_app.app.utils.formatting import round_column_values


def run(params: dict) -> dict:
    """Run the reaction similarity search.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"databases"`` (list[str]): CSV filenames to search.
            - ``"smiles"`` (str): query reaction SMILES string.
            - ``"algorithms"`` (list[str]): selected algorithm value keys
              (e.g. ``["tanimoto", "cosine"]``).  Currently enzymetk
              computes all three metrics in one pass; this field records
              the user's selection and controls which columns appear in
              the output.  When the enzymetk API supports per-algorithm
              execution, this will be used to select the metric(s).
            - ``"top_n"`` (int): max number of results to return.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``algorithms``: the selected algorithm keys.
        - ``top_n``: requested result count.
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When no valid databases are provided or the query
            SMILES cannot be parsed.
    """
    # NOTE: Exceptions are not caught here — they propagate to
    # run_tool_task (tasks.py), which records the traceback and
    # marks the job as FAILURE.

    # Lazy import — enzymetk + rdkit are heavy; only load in the worker.
    from enzymetk.similarity_reaction_step import ReactionDist  # noqa: PLC0415

    from enzyme_tk_app.app.utils.smiles_rendering import (  # noqa: PLC0415
        generate_cached_svg_uris,
        reaction_to_svg_data_uri,
    )

    databases: list[str] = params["databases"]
    query_smiles_string: str = params["smiles"]
    similarity_algorithms = [SimilarityAlgorithm(a) for a in params["algorithms"]]
    top_n: int = int(params["top_n"])

    if not similarity_algorithms:
        raise ValueError("At least one similarity algorithm must be selected.")

    run_time_start = time.monotonic()

    all_results: list[pd.DataFrame] = []
    total_scanned_rows_in_dbs = 0
    databases_loaded = 0
    databases_skipped: list[str] = []

    for db_filename in databases:
        # Sanitise client-supplied filename: strip directory components
        # to prevent path-traversal and enforce a .csv suffix.
        safe_name = Path(db_filename).name
        if not safe_name.endswith(".csv"):
            databases_skipped.append(db_filename)
            continue
        csv_path = DATA_DIR / "reactions" / safe_name
        if not csv_path.exists():
            databases_skipped.append(db_filename)
            continue

        databases_loaded += 1
        db_df = load_and_clean_data(csv_path)
        total_scanned_rows_in_dbs += len(db_df)

        # Run ReactionDist — computes all three similarity metrics in one pass
        rd = ReactionDist(
            id_column_name="id",
            smiles_column_name=COL_UNMAPPED_SMILES,
            smiles_string=query_smiles_string,
        )
        result_df = rd.execute(db_df)

        # Tag each row with its source database (human-readable stem)
        result_df[COL_DATABASE] = csv_path.stem.replace("_", " ").title()
        all_results.append(result_df)

    if not all_results:
        run_time = round(time.monotonic() - run_time_start, 3)
        stat_cards = [
            {"label": "Databases Searched", "value": f"{databases_loaded}/{len(databases)}"},
            {"label": "Reactions Scanned", "value": "0"},
            {"label": "Results Returned", "value": "0"},
            {"label": "Run Time", "value": f"{run_time}s"},
        ]
        if databases_skipped:
            stat_cards.append({"label": "Databases Skipped", "value": ", ".join(databases_skipped)})
        return {
            "_stat_cards": stat_cards,
            "dataframe": {"columns": [], "data": []},
        }

    combined_results_across_all_db = pd.concat(all_results, ignore_index=True)

    # Resolve the primary algorithm's column name for sorting.
    sort_col = similarity_algorithms[0].column
    sorted_top_n_results = get_top_n_sorted_results(combined_results_across_all_db, sort_col, top_n)

    # Generate SVG data URIs for the top-N reactions (not all — only results)
    sorted_top_n_results[COL_RXN_SVG] = generate_cached_svg_uris(
        sorted_top_n_results[COL_UNMAPPED_SMILES], reaction_to_svg_data_uri, height=200
    )

    # Round similarity scores to 4 decimal places for display
    selected_sim_cols = [algo.column for algo in similarity_algorithms]
    output_df = round_column_values(list_of_columns=selected_sim_cols, df=sorted_top_n_results)

    run_time = round(time.monotonic() - run_time_start, 3)

    stat_cards = [
        {"label": "Databases Searched", "value": f"{databases_loaded}/{len(databases)}"},
        {"label": "Reactions Scanned", "value": f"{total_scanned_rows_in_dbs:,}"},
        {"label": "Results Returned", "value": str(len(output_df))},
        {"label": "Run Time", "value": f"{run_time}s"},
    ]
    if databases_skipped:
        stat_cards.append({"label": "Databases Skipped", "value": ", ".join(databases_skipped)})

    return {
        "_stat_cards": stat_cards,
        "dataframe": {
            "columns": output_df.columns.tolist(),
            "data": output_df.to_dict(orient="records"),
        },
    }
