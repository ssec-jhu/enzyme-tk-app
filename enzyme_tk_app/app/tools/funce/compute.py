"""Compute function for the Func-E Activity Prediction tool.

Runs ``enzymetk.predict_Funce_step.Funce`` to score every protein in a
pre-encoded database against a query reaction, then ranks them by predicted
activity.

.. note::

   ``Funce`` is *prediction-only*.  It needs a DataFrame that already carries
   the protein embedding (``esm3_mean``) and the three reaction embeddings
   (``rxnfp``, ``substrate_unimol_repr``, ``product_unimol_repr``).  The
   database pickles under ``data/funce_db/`` supply the protein side; the
   reaction side comes from :func:`_encode_reaction`.
"""

import pickle
import time

import pandas as pd

from enzyme_tk_app.app.paths import FUNCE_DB_DIR, FUNCE_MODELS_DIR
from enzyme_tk_app.app.tools.funce import DEHP_MEHP_SMILES

# Reaction-side embedding columns the Funce step consumes.
RXN_COLS = ["rxnfp", "substrate_unimol_repr", "product_unimol_repr"]

# Protein-side embedding column, supplied by the database pickle.
PROTEIN_EMB_COL = "esm3_mean"

# Every embedding column — dropped before the result is serialised to JSON.
EMBED_COLS = [PROTEIN_EMB_COL, *RXN_COLS]

# Columns every database pickle must carry to be scorable.
REQUIRED_DB_COLS = ("Entry", "Sequence", PROTEIN_EMB_COL)

# Prefix for the columns Funce appends.  Fixed (rather than derived from the
# task name) so the results grid can declare its columns up front.
PREDICTION_NAME = "Funce"
PRED_COL = f"{PREDICTION_NAME}_prediction"


def _resolve_database(database: str):
    """Return the validated path to a database pickle inside ``FUNCE_DB_DIR``.

    Args:
        database: The filename chosen in the modal.

    Returns:
        The resolved ``Path`` to the pickle.

    Raises:
        ValueError: If the name escapes ``FUNCE_DB_DIR`` or does not exist.
    """
    db_root = FUNCE_DB_DIR.resolve()
    db_path = (FUNCE_DB_DIR / database).resolve()
    if db_path.parent != db_root or not db_path.is_file():
        raise ValueError(f"Unknown protein database: {database}")
    return db_path


def _load_databases(databases: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Load and concatenate the selected database pickles.

    Each pickle contributes its proteins, tagged with a ``database`` column so
    a hit can be traced back to its source.  Entries are not de-duplicated
    across databases — the same protein in two databases is scored twice and
    shown twice, which is the honest reading of "search both".

    An unreadable or malformed database is skipped and reported rather than
    failing the whole run; only a total wipeout is an error, since an empty
    result would otherwise look like "no hits".

    Args:
        databases: Filenames chosen in the modal.

    Returns:
        ``(concatenated protein table, names of skipped databases)``.

    Raises:
        ValueError: If no databases were given, or none could be read.
    """
    if not databases:
        raise ValueError("At least one protein database must be selected.")

    frames = []
    skipped: list[str] = []
    for name in databases:
        try:
            db_path = _resolve_database(name)
            # nosec B301 — operator-supplied file: _resolve_database confines the path to
            # FUNCE_DB_DIR (a read-only mount), so this never deserialises user input.
            frame = pd.read_pickle(db_path)  # nosec B301
        except (ValueError, OSError, pickle.UnpicklingError, EOFError):
            skipped.append(name)
            continue

        if any(c not in frame.columns for c in REQUIRED_DB_COLS) or frame.empty:
            skipped.append(name)
            continue

        frame["database"] = db_path.stem
        frames.append(frame)

    if not frames:
        raise ValueError(f"None of the selected databases could be read: {', '.join(databases)}")

    return pd.concat(frames, ignore_index=True), skipped


def _encode_reaction(smiles: str, db_df: pd.DataFrame) -> dict:
    """Return the three reaction embedding vectors for *smiles*.

    Ceiling: only the pre-encoded DEHP->MEHP reaction resolves today — its
    vectors are read out of the first database row that carries them, since
    the shipped pickles have the reaction broadcast across every protein row.
    Upgrade path: replace this body with ``RxnFP(smiles)`` plus ``UniMol`` on
    the substrate and product, and drop the *db_df* argument — the vectors
    then come from the query and no database needs to carry them.  The exact
    string match is deliberate; canonicalise with RDKit once that lands.

    Args:
        smiles: The query reaction SMILES.
        db_df: The concatenated databases, used as the vector source for now.

    Returns:
        Mapping of embedding column name to its vector.

    Raises:
        ValueError: If *smiles* is anything but the pre-encoded reaction, or
            no selected database carries the reaction embeddings.
    """

    # TODO:
    # the reaction encoding logic should be updated once RxnFP and UniMol are integrated.
    # For now, only the pre-encoded DEHP->MEHP reaction is supported.

    if smiles.strip() != DEHP_MEHP_SMILES:
        raise ValueError(
            "Only the pre-encoded example reaction can be scored right now. "
            "Reaction-to-fingerprint encoding is not yet available — pick "
            "'DEHP → MEHP' from the examples dropdown."
        )

    # Check if the reaction is the pre-encoded DEHP->MEHP reaction.
    missing = [c for c in RXN_COLS if c not in db_df.columns]
    if missing:
        raise ValueError(
            "No selected database carries the pre-encoded reaction "
            f"(missing {', '.join(missing)}). Include a database that does, "
            "such as Funce_pairs."
        )

    # Take the first row that actually has the reaction vectors — a database
    # without them contributes NaN once the frames are concatenated.
    encoded = db_df.dropna(subset=list(RXN_COLS))
    if encoded.empty:
        raise ValueError("No selected database carries the pre-encoded reaction embeddings.")
    return {col: encoded[col].iloc[0] for col in RXN_COLS}


def run(params: dict) -> dict:
    """Score a pre-encoded protein database against a query reaction.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"smiles"`` (str): query reaction SMILES.
            - ``"databases"`` (list[str]): pickle filenames in ``funce_db/``.
              All selected databases are merged and ranked together.
            - ``"top_n"`` (int): maximum number of ranked hits to return.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When the database or reaction cannot be resolved.
        ImportError: When ``enzymetk`` (or torch) is not available.
    """
    # Lazy import — enzymetk pulls in torch, which is heavy; worker only.
    import torch  # noqa: PLC0415
    from enzymetk import Funce  # noqa: PLC0415

    smiles: str = params["smiles"]
    databases: list[str] = params["databases"]
    top_n: int = int(params["top_n"])

    run_time_start = time.monotonic()

    db_df, databases_skipped = _load_databases(databases)
    candidate_count = len(db_df)

    # Broadcast the single query reaction across every protein row — the step
    # scores pairs and does no broadcasting of its own.
    for col, vector in _encode_reaction(smiles, db_df).items():
        db_df[col] = [vector] * candidate_count

    # Initialize the Funce step for scoring the reaction against the protein database.
    step = Funce("Entry", name=PREDICTION_NAME, model_dir=str(FUNCE_MODELS_DIR))
    scored = step.execute(db_df)

    # The step leaves ranking to the caller.
    ranked = scored.sort_values(PRED_COL, ascending=False).head(top_n).reset_index(drop=True)

    # Drop the embeddings and the per-model intermediates that
    # ``retransform_scaled_predictions`` leaves on the frame — they hold raw
    # ndarrays/tensors that would bloat and break the JSON result payload.
    drop_cols = [c for c in EMBED_COLS if c in ranked.columns]
    drop_cols += [c for c in ranked.columns if c.startswith(("pred_", "inverse_transformed_"))]
    ranked = ranked.drop(columns=drop_cols)

    run_time = round(time.monotonic() - run_time_start, 3)

    # this is just for the stat cards, not used in the computation itself
    # Determine the device used for computation (CPU or GPU). It helps
    # provide context in the stat cards for performance analysis.
    device = "cuda" if torch.cuda.is_available() else "cpu"

    return {
        "_stat_cards": [
            {"label": "Databases Searched", "value": str(len(databases) - len(databases_skipped))},
            *([{"label": "Databases Skipped", "value": ", ".join(databases_skipped)}] if databases_skipped else []),
            {"label": "Candidates Scored", "value": str(candidate_count)},
            {"label": "Top Score", "value": f"{ranked[PRED_COL].iloc[0]:.4f}"},
            {"label": "Device", "value": device},
            {"label": "Run Time", "value": f"{run_time}s"},
        ],
        "dataframe": {
            "columns": ranked.columns.tolist(),
            "data": ranked.to_dict(orient="records"),
        },
    }
