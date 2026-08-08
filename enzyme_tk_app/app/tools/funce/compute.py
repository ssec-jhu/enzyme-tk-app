"""Compute function for the Func-E Activity Prediction tool.

Runs ``enzymetk.predict_Funce_step.Funce`` to score every protein in a
pre-encoded database against a query reaction, then ranks them by predicted
activity.

.. note::

   ``Funce`` is *prediction-only*.  It needs a DataFrame that already carries
   the protein embedding (``esm3_mean``) and the three reaction embeddings
   (``rxnfp``, ``substrate_unimol_repr``, ``product_unimol_repr``).  The
   database pickles under ``data/sequence_embeddings/`` supply the protein side; the
   reaction side is computed from the query SMILES by :func:`_encode_reaction`.
"""

import multiprocessing
import os
import pickle
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from enzyme_tk_app.app.paths import FUNCE_MODELS_DIR, SEQUENCE_EMBEDDINGS_DIR, UNIMOL_WEIGHTS_DIR
from enzyme_tk_app.app.utils.columns import COL_DATABASE, COL_ENTRY, COL_SEQUENCE

# Reaction-side embedding columns the Funce step reads — enzymetk's own
# defaults for ``rxn_col`` / ``sub_col`` / ``prod_col``.  ``_encode_reaction``
# returns exactly these keys and ``_load_databases`` strips them from the
# pickles; the protein side comes from the database pickle.
RXN_COLS = ["rxnfp", "substrate_unimol_repr", "product_unimol_repr"]

# The step's activity score.  enzymetk prefixes its output columns with its
# ``name`` argument, which defaults to "Funce" — we leave that default alone.
PRED_COL = "Funce_prediction"

# ── The only columns removed from the result ────────────────────────────────
# Everything else the Funce step returns reaches the results grid untouched.
# Delete a name from this list to keep that column; a name that the installed
# enzymetk no longer emits is ignored rather than an error.
DROPPED_COLS = [
    # Embeddings.  Every cell holds an ndarray, which ``json.dumps`` cannot
    # encode — keeping one of these breaks the result payload.
    "esm3_mean",
    "rxnfp",
    "substrate_unimol_repr",
    "product_unimol_repr",
    # enzymetk's per-model scratch columns.  ``retransform_scaled_predictions``
    # rewrites them once per ensemble model, so only the last model's values
    # survive — the ensemble answer is the ``Funce_*_mean`` / ``_std`` pair
    # instead.  These are plain floats, so keeping one is safe, just misleading.
    "pred_Activity",
    "pred_Length",
    "inverse_transformed_pred_Length",
    "pred_Mass",
    "inverse_transformed_pred_Mass",
    "pred_Polarity",
    "inverse_transformed_pred_Polarity",
    "pred_temperature",
    "inverse_transformed_pred_temperature",
    "pred_substrates_MolWt",
    "inverse_transformed_pred_substrates_MolWt",
    "pred_substrates_MolLogP",
    "inverse_transformed_pred_substrates_MolLogP",
    "pred_substrates_MaxPartialCharge",
    "inverse_transformed_pred_substrates_MaxPartialCharge",
    "pred_substrates_MinPartialCharge",
    "inverse_transformed_pred_substrates_MinPartialCharge",
    "pred_products_MolWt",
    "inverse_transformed_pred_products_MolWt",
    "pred_products_TPSA",
    "inverse_transformed_pred_products_TPSA",
    "pred_products_MolLogP",
    "inverse_transformed_pred_products_MolLogP",
    "pred_products_MaxPartialCharge",
    "inverse_transformed_pred_products_MaxPartialCharge",
    "pred_products_MinPartialCharge",
    "inverse_transformed_pred_products_MinPartialCharge",
]


def _resolve_database(database: str):
    """Return the validated path to a database pickle inside ``SEQUENCE_EMBEDDINGS_DIR``.

    Args:
        database: The filename chosen in the modal.

    Returns:
        The resolved ``Path`` to the pickle.

    Raises:
        ValueError: If the name escapes ``SEQUENCE_EMBEDDINGS_DIR`` or does not exist.
    """
    db_root = SEQUENCE_EMBEDDINGS_DIR.resolve()
    db_path = (SEQUENCE_EMBEDDINGS_DIR / database).resolve()
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

    # Minimum a pickle must carry to be scorable: an identifier, the sequence,
    # and the protein embedding (enzymetk's ``protein_emb_col`` default).
    required_cols = (COL_ENTRY, COL_SEQUENCE, "esm3_mean")

    frames = []
    # Skipped names carry the same spelling as every other surface: the filename
    # exactly as it appears in data/sequence_embeddings/, extension included.
    skipped: list[str] = []
    for name in databases:
        safe_name = Path(name).name
        try:
            db_path = _resolve_database(name)
            # nosec B301 — operator-supplied file: _resolve_database confines the path to
            # SEQUENCE_EMBEDDINGS_DIR (a read-only mount), so this never deserialises user input.
            frame = pd.read_pickle(db_path)  # nosec B301
        except (ValueError, OSError, pickle.UnpicklingError, EOFError):
            skipped.append(safe_name)
            continue

        # A pickle can hold any object.  Check the type before touching
        # ``.columns`` / ``.empty``, or a dict — or even a legitimate Series —
        # raises AttributeError and fails the whole job instead of skipping
        # the one bad database.
        if not isinstance(frame, pd.DataFrame):
            skipped.append(safe_name)
            continue

        if any(c not in frame.columns for c in required_cols) or frame.empty:
            skipped.append(safe_name)
            continue

        # Drop any reaction embeddings the pickle carries of its own.  Fixtures like
        # Funce_pairs.pkl were built with one reaction already broadcast across every
        # row; the query's vectors must win, and leaving these in place would let a
        # stale reaction survive into rows the broadcast in ``run`` does not reach.
        frame = frame.drop(columns=RXN_COLS, errors="ignore")

        # Named exactly as the file is named in data/sequence_embeddings/, extension
        # included — see the data_loading module docstring.
        frame[COL_DATABASE] = db_path.name
        frames.append(frame)

    if not frames:
        raise ValueError(f"None of the selected databases could be read: {', '.join(skipped)}")

    return pd.concat(frames, ignore_index=True), skipped


def _split_reaction(smiles: str) -> tuple[str, str]:
    """Split a reaction SMILES into ``(substrate, product)`` on ``>>``.

    The product is the *last* segment, so a multi-arrow string like ``A>>B>>C``
    yields ``(A, C)``.  Each side may be dot-joined (``A.B>>C``); it is embedded
    whole, exactly as the reference example does.
    """
    parts = smiles.strip().split(">>")
    return parts[0].strip(), parts[-1].strip()


def validate_reaction_smiles(smiles: object) -> str | None:
    """Return an error message for an unusable reaction SMILES, or ``None``.

    Message-or-``None`` matches ``validate_db_names`` and ``validate_top_n``, so the
    modal callback and :func:`run` can share one definition of "valid".  The string
    is typed by the user and encoding is slow, so a typo rejected here saves a
    minute-long job that would otherwise die deep inside UniMol.

    Args:
        smiles: The reaction SMILES from the modal.

    Returns:
        A human-readable error message, or ``None`` when *smiles* is usable.
    """
    from rdkit.Chem import MolFromSmiles  # noqa: PLC0415

    if not isinstance(smiles, str) or not smiles.strip():
        return "Enter a reaction SMILES."

    if ">>" not in smiles:
        return "Reaction SMILES must separate substrate from product with '>>'."

    substrate, product = _split_reaction(smiles)
    if not substrate or not product:
        return "Reaction SMILES needs a substrate before '>>' and a product after it."

    # RDKit returns None rather than raising on an unparseable molecule.
    for label, side in (("substrate", substrate), ("product", product)):
        if MolFromSmiles(side) is None:
            return f"The {label} is not a valid SMILES: {side}"

    return None


def _ensure_python_on_path() -> None:
    """Make a bare ``python`` resolve to the interpreter running this process.

    ``RxnFP`` shells out with ``cmd[0] == "python"`` rather than ``sys.executable``,
    so with ``env_name=None`` it runs on whatever ``python`` the PATH happens to
    find — and an environment that only ships ``python3`` gets
    ``FileNotFoundError: 'python'``.  A no-op in the Docker image, where ``python``
    is already the right interpreter.
    """
    bindir = str(Path(sys.executable).parent)
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")


@contextmanager
def _allow_forking():
    """Let a step fork worker processes while inside Celery's prefork pool.

    Celery runs each task in a *daemonic* child, and a daemonic process may not
    have children of its own.  ``unimol_tools`` builds conformers with a
    ``multiprocessing.Pool``, so under Celery it raises "daemonic processes are
    not allowed to have children" — which UniMol's own ``except`` swallows into a
    ``None`` embedding rather than an error.  Clearing the flag for the duration
    of the call is the standard Celery workaround.

    Ceiling: unimol_tools pools up to 8 processes to embed our two molecules, and
    a hard kill of the worker mid-call could orphan them.  Forwarding a kwarg will
    not fix it: ``multi_process`` is read from the ``params`` dict ``UniMolRepr``
    builds from its own named arguments, and anything else passed to it is dropped,
    so the flag never reaches the conformer generator.  Dropping this needs a change
    inside unimol_tools itself.
    """
    process = multiprocessing.current_process()
    was_daemon = getattr(process, "daemon", False)
    if was_daemon:
        process.daemon = False
    try:
        yield
    finally:
        if was_daemon:
            process.daemon = True


def _encode_reaction(smiles: str) -> dict:
    """Embed *smiles* into the three reaction vectors the Funce step reads.

    The reaction is fingerprinted with RxnFP (256-d) and its substrate and product
    are embedded with UniMol (768-d each) — widths fixed by the trained Funce
    checkpoints.  RxnFP, not DRFP: ``forward_reaction`` is ``nn.Linear(in=256)`` and
    was fit on RxnFP's dense continuous basis, so a DRFP vector folded to 256 is
    *accepted* and silently reranks rather than failing.

    Ceiling: both steps reload their checkpoint on every call — roughly ten of the
    twelve seconds a small job takes, and flat regardless of database size.  The
    upgrade is module-level cached ``UniMolRepr`` / ``RXNBERTFingerprintGenerator``
    singletons, worth doing only if that fixed cost ever stops being noise next to
    scoring itself.

    Args:
        smiles: The query reaction SMILES, already passed through
            :func:`validate_reaction_smiles`.

    Returns:
        Mapping of each name in ``RXN_COLS`` to its ``float32`` vector.
    """
    import numpy as np  # noqa: PLC0415
    from enzymetk.embedchem_rxnfp_step import RxnFP  # noqa: PLC0415
    from enzymetk.embedchem_unimol_step import UniMol  # noqa: PLC0415

    substrate, product = _split_reaction(smiles)

    # RxnFP round-trips the frame through to_csv/read_csv in a subprocess, so it must
    # see no array columns — hence this bare one-row frame, before anything is merged.
    # env_name=None skips the `conda run -n rxnfp` wrapper; tmp_dir must be a real
    # path, because left None the step f-strings the TemporaryDirectory *object*
    # into a filename and breaks.
    _ensure_python_on_path()
    with TemporaryDirectory() as tmp_dir:
        rxn_df = RxnFP("reaction", 1, env_name=None, tmp_dir=tmp_dir).execute(pd.DataFrame({"reaction": [smiles]}))

    # Both molecules in one call: UniMol rebuilds its model on every execute() and
    # always writes to "unimol_repr", so one call per molecule would cost a second
    # checkpoint load *and* need renaming in between.  weights_dir names the bundled
    # checkpoint; left off, unimol_tools resolves UNIMOL_WEIGHT_DIR instead and downloads
    # ~660 MB into its own site-packages directory on every fresh container.
    with _allow_forking():
        mol_df = UniMol("smiles", weights_dir=str(UNIMOL_WEIGHTS_DIR)).execute(
            pd.DataFrame({"smiles": [substrate, product]})
        )

    # UniMol logs its own failures and writes None rather than raising.  numpy turns
    # that None into a 1-wide nan vector, which survives the broadcast and only
    # surfaces as "mat1 and mat2 shapes cannot be multiplied" inside Funce — or, if
    # the widths happened to line up, as silently meaningless scores.  Stop here,
    # where the cause is still named.
    reprs = list(mol_df["unimol_repr"])
    if any(v is None for v in reprs):
        raise ValueError(
            "UniMol could not embed the substrate or product of this reaction — "
            "see the job log for the underlying error."
        )

    # UniMol hands back a nested cls_repr ([[...768...]]); flatten to the
    # one-vector-per-cell shape the Funce step expects.
    substrate_repr, product_repr = (np.asarray(v).flatten().astype(np.float32) for v in reprs)
    return {
        "rxnfp": np.asarray(rxn_df["rxnfp"].iloc[0]).flatten().astype(np.float32),
        "substrate_unimol_repr": substrate_repr,
        "product_unimol_repr": product_repr,
    }


def run(params: dict) -> dict:
    """Score a pre-encoded protein database against a query reaction.

    Args:
        params: Dictionary with keys:
            - ``"task_name"`` (str): human-readable label for the job.
            - ``"smiles"`` (str): query reaction SMILES.
            - ``"databases"`` (list[str]): pickle filenames in ``sequence_embeddings/``.
              All selected databases are merged and ranked together.
            - ``"top_n"`` (int): maximum number of ranked hits to return.

    Returns:
        A JSON-serialisable dict with:
        - ``_stat_cards``: list of stat-card dicts (label/value).
        - ``dataframe``: ``{"columns": [...], "data": [records]}``.

    Raises:
        ValueError: When the reaction SMILES is invalid or no database can be read.
        ImportError: When ``enzymetk`` (or torch) is not available.
    """
    # Lazy import — enzymetk pulls in torch, which is heavy; worker only.
    import torch  # noqa: PLC0415
    from enzymetk import Funce  # noqa: PLC0415

    smiles: str = params["smiles"]
    databases: list[str] = params["databases"]
    top_n: int = int(params["top_n"])

    # The modal validates too, but a replayed job reaches this function directly —
    # and encoding is far too slow to spend on a string we can reject up front.
    invalid = validate_reaction_smiles(smiles)
    if invalid:
        raise ValueError(invalid)

    run_time_start = time.monotonic()

    db_df, databases_skipped = _load_databases(databases)
    candidate_count = len(db_df)

    # Broadcast the single query reaction across every protein row — the step
    # scores pairs and does no broadcasting of its own.
    for col, vector in _encode_reaction(smiles).items():
        db_df[col] = [vector] * candidate_count

    # Initialize the Funce step for scoring the reaction against the protein database.
    step = Funce(COL_ENTRY, model_dir=str(FUNCE_MODELS_DIR))
    scored = step.execute(db_df)

    # The step leaves ranking to the caller.
    ranked = scored.sort_values(PRED_COL, ascending=False).head(top_n).reset_index(drop=True)

    # Everything the step returned is kept except the columns named at the top
    # of this module — see ``DROPPED_COLS``.  A column enzymetk adds later is
    # kept and shown rather than silently discarded.
    ranked = ranked.drop(columns=DROPPED_COLS, errors="ignore")

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
