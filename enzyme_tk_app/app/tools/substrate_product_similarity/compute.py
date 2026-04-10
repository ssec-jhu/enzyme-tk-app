"""Compute function for the Substrate/Product Similarity tool.

Loads selected reaction databases, extracts individual substrate or
product molecules from each reaction, runs
``enzymetk.SubstrateDist`` (Morgan circular fingerprints) against
the query molecule, and returns the top-N most similar molecules
with all original reaction metadata preserved.

Each reaction row is expanded into one row per molecule on the
chosen side (substrate or product).  For example, a reaction
``A.B>>C`` with role ``"substrate"`` produces two rows — one for
molecule A and one for molecule B — each carrying the full metadata
of the parent reaction.
"""

import time

import pandas as pd

from enzyme_tk_app.app.tools.substrate_product_similarity import get_similarity_algorithms
from enzyme_tk_app.app.utils.data_loading import (
    _COL_MOL_INDEX,
    _COL_MOL_SMILES,
    _COL_MOL_SVG,
    _COL_UNMAPPED_SMILES,
    DATA_DIR,
    get_top_n_sorted_results,
    load_and_clean_data,
)
from enzyme_tk_app.app.utils.formatting import round_column_values

# Temporary column name used as the join key for SubstrateDist.
_ROW_ID = "_row_id"


def _expand_reactions(db_df: pd.DataFrame, role: str) -> pd.DataFrame:
    """Expand reaction rows into individual molecule rows.

    Splits the ``unmapped`` column on ``>>`` to separate substrates
    from products, then splits the chosen side on ``.`` to yield one
    row per individual molecule.  All original columns are preserved.

    Args:
        db_df: DataFrame with an ``unmapped`` column containing
            reaction SMILES in ``substrates>>products`` format.
        role: ``"substrate"`` (take the left side of ``>>``) or
            ``"product"`` (take the right side).

    Returns:
        DataFrame with added columns:
        - ``molecule_smiles``: individual molecule SMILES.
        - ``molecule_index``: 0-based position within the
          substrate/product list.
    """
    # Determine which side of the reaction to extract based on the role.
    side_index = 0 if role == "substrate" else 1

    def _extract_molecules(reaction_smiles: str) -> list[str]:
        """Split a reaction SMILES into individual molecules for the chosen side."""
        if not isinstance(reaction_smiles, str) or ">>" not in reaction_smiles:
            return []
        parts = reaction_smiles.split(">>")
        # If the expected side is missing (e.g., no products for a substrate role), return an empty list.
        if side_index >= len(parts):
            return []
        # Split the chosen side on "." to get individual molecules, and strip whitespace.
        side = parts[side_index].strip()
        if not side:
            return []

        # Return a list of non-empty, stripped molecule SMILES.
        return [m.strip() for m in side.split(".") if m.strip()]

    # Build a list column of individual molecule SMILES
    db_df = db_df.copy()
    # The "_col_unmapped_smiles" column contains the original reaction SMILES string,
    # which we parse to extract the individual molecule SMILES for the chosen role.
    db_df[_COL_MOL_SMILES] = db_df[_COL_UNMAPPED_SMILES].apply(_extract_molecules)

    # Drop rows where no molecules could be extracted
    db_df = db_df[db_df[_COL_MOL_SMILES].apply(len) > 0]

    # Explode so each molecule gets its own row
    db_df = db_df.explode(_COL_MOL_SMILES, ignore_index=True)

    # Molecule index: 0-based position within the substrate/product list.
    # This is useful for tracking which molecule is which after the explosion.
    db_df[_COL_MOL_INDEX] = db_df.groupby(["id", _COL_UNMAPPED_SMILES]).cumcount()

    return db_df


def run(params: dict) -> dict:
    """Run the substrate/product similarity search.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"databases"`` (list[str]): CSV filenames to search.
            - ``"smiles"`` (str): query molecule SMILES string.
            - ``"algorithms"`` (list[str]): selected algorithm value
              keys (e.g. ``["tanimoto", "cosine"]``).
            - ``"top_n"`` (int): max number of results to return.
            - ``"role"`` (str): ``"substrate"`` or ``"product"``.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``algorithms``: the selected algorithm keys.
        - ``top_n``: requested result count.
        - ``role``: the molecule role searched.
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When no valid databases are provided or the query
            SMILES cannot be parsed.
    """
    # NOTE: Exceptions are not caught here — they propagate to
    # run_tool_task (tasks.py), which records the traceback and
    # marks the job as FAILURE.

    # Lazy import — enzymetk + rdkit are heavy; only load in the worker.
    from enzymetk.similarity_substrate_step import SubstrateDist  # noqa: PLC0415

    from enzyme_tk_app.app.utils.smiles_rendering import smiles_to_svg_data_uri  # noqa: PLC0415

    # Extract parameters with type hints for clarity.
    databases: list[str] = params["databases"]
    smiles: str = params["smiles"]
    similarity_algorithms: list[str] = params["algorithms"]
    top_n: int = int(params["top_n"])
    role: str = params.get("role", "substrate")

    # Map algorithm value keys to their corresponding column names in the SubstrateDist output.
    similarity_algorithm_columns = {a["value"]: a["column"] for a in get_similarity_algorithms()}

    # Start a timer to measure total run time of the function.
    run_time_start = time.monotonic()

    all_results: list[pd.DataFrame] = []
    total_scanned_rows_in_dbs = 0
    total_molecules = 0

    for db_filename in databases:
        csv_path = DATA_DIR / "reactions" / db_filename
        if not csv_path.exists():
            continue

        # for each selected database, load the CSV and clean it (e.g., drop unusable rows).
        db_df = load_and_clean_data(csv_path)
        total_scanned_rows_in_dbs += len(db_df)

        # Expand reactions into individual molecules
        # Each reaction with multiple substrates/products becomes multiple rows,
        # each with the same metadata but a different molecule SMILES.
        expanded_df = _expand_reactions(db_df, role)
        if expanded_df.empty:
            continue

        # Keep track of how many individual molecules we are comparing against.
        total_molecules += len(expanded_df)

        # Build a minimal DataFrame for SubstrateDist
        # We use _ROW_ID as the unique identifier for each molecule row,
        # which allows us to merge similarity scores back to the original metadata.
        expanded_df[_ROW_ID] = range(len(expanded_df))

        # The SubstrateDist algorithm only needs the _ROW_ID and molecule SMILES columns.
        sim_input = expanded_df[[_ROW_ID, _COL_MOL_SMILES]].copy()

        # Run SubstrateDist — computes all three similarity metrics
        # in one pass.  The output includes the _ROW_ID for merging,
        # the query SMILES, the molecule SMILES, and the similarity scores.
        sd = SubstrateDist(
            id_column_name=_ROW_ID,
            smiles_column_name=_COL_MOL_SMILES,
            smiles_string=smiles,
        )
        # This may raise an exception if the input SMILES is invalid or
        # if enzymetk encounters an error.
        result_df = sd.execute(sim_input)

        # TODO: remove later
        print("DEBUG:result_df.columns.tolist()", result_df.columns.tolist())

        # Join similarity scores back to expanded metadata
        # SubstrateDist output has _ROW_ID, QuerySmiles, _MOL_SMILES_COL, and sim cols
        sim_cols_to_join = [_ROW_ID] + list(similarity_algorithm_columns.values())
        sim_scores = result_df[sim_cols_to_join]
        merged = expanded_df.merge(sim_scores, on=_ROW_ID, how="inner")

        # Tag each row with its source database
        merged["database"] = csv_path.stem.replace("_", " ").title()
        all_results.append(merged)

    if not all_results:
        run_time = round(time.monotonic() - run_time_start, 3)
        # If no results were found across all databases, return an empty dataframe with stats.

        return {
            # stat cards for the UI to display summary information about the search.
            "_stat_cards": [
                {"label": "Databases Searched", "value": str(len(databases))},
                {"label": "Reactions Scanned", "value": "0"},
                {"label": "Molecules Compared", "value": "0"},
                {"label": "Results Returned", "value": "0"},
                {"label": "Run Time", "value": f"{run_time}s"},
            ],
            "dataframe": {"columns": [], "data": []},
        }

    combined_results_across_all_db = pd.concat(all_results, ignore_index=True)

    # Resolve the primary algorithm's column name for sorting.
    sort_col = similarity_algorithm_columns.get(similarity_algorithms[0], "TanimotoSimilarity")
    sorted_top_n_results = get_top_n_sorted_results(combined_results_across_all_db, sort_col, top_n)

    # Generate SVG data URIs for the top-N molecules (not all — only results)
    uri_cache: dict[str, str] = {}
    uris = []
    for mol_smi in sorted_top_n_results[_COL_MOL_SMILES]:
        if mol_smi not in uri_cache:
            # the width and height of the image can be adjusted as needed,
            # but should be large enough to show details of the molecule without
            # being too large for the UI. The table will show a thumbnail,
            # and users can click to see the full image in a tooltip or modal.
            uri_cache[mol_smi] = smiles_to_svg_data_uri(mol_smi, width=500, height=300)
        uris.append(uri_cache[mol_smi])
    sorted_top_n_results[_COL_MOL_SVG] = uris

    # Drop internal join key — not useful in the output
    sorted_top_n_results = sorted_top_n_results.drop(columns=[_ROW_ID], errors="ignore")

    # Round similarity scores for display
    selected_sim_cols = [
        similarity_algorithm_columns[a] for a in similarity_algorithms if a in similarity_algorithm_columns
    ]
    output_df = round_column_values(list_of_columns=selected_sim_cols, df=sorted_top_n_results)

    run_time = round(time.monotonic() - run_time_start, 3)

    # TODO: remove later
    print("DEBUG:output_df.columns.tolist())", print(output_df.columns.tolist()))

    return {
        "_stat_cards": [
            {"label": "Databases Searched", "value": str(len(databases))},
            {"label": "Reactions Scanned", "value": f"{total_scanned_rows_in_dbs:,}"},
            {"label": "Molecules Compared", "value": f"{total_molecules:,}"},
            {"label": "Results Returned", "value": str(len(output_df))},
            {"label": "Run Time", "value": f"{run_time}s"},
        ],
        # The "dataframe" key contains the results in a format suitable for AG Grid:
        # - "columns" is a list of column names.
        # - "data" is a list of dictionaries, each representing a row.
        "dataframe": {
            "columns": output_df.columns.tolist(),
            "data": output_df.to_dict(orient="records"),
        },
    }
