"""Compute function for the Func-E Activity Prediction tool.

Runs ``enzymetk.Funce_rxnfp_unimol`` to score every protein in a pre-encoded
database against a query reaction, then ranks them by predicted activity.

The step owns the whole pipeline — fingerprinting the reaction with RxnFP,
embedding each molecule with UniMol, broadcasting those vectors across every
protein row, and scoring with the EC-level ensemble.  This module only routes:
it loads the selected database pickles into one frame, names the two data
directories, and ranks what comes back.

Invariants that live here because they are Func-E's alone
---------------------------------------------------------

**All selected databases are scored in one call.**  Func-E's cross-attention
softmaxes over the batch, so a row's score depends on which other rows went
through the same ``execute()``.  Chunking the frame, or scoring one database at a
time and merging, changes every number.

**The app never downloads.**  ``download_if_missing=False`` is passed
explicitly, so a missing UniMol checkpoint fails loudly instead of pulling
~660 MB inside a request.  ``check_data`` gates the tool off long before that.

**A multi-molecule side is split and summed** by the step's own
``combine_molecule_embeddings``.  ``sum([v]) == v``, so a single-molecule side is
byte-for-byte unchanged; a dot-joined side is no longer the silent failure it was
when the app handed UniMol a whole side as one structure.  Which reduction the
training pipeline used is not recorded anywhere, so a shipped example should not
lean on it.

**The step mutates three environment variables process-wide, permanently:** it
sets ``UNIMOL_WEIGHT_DIR``, prepends ``sys.executable``'s directory to ``PATH``
(RxnFP shells out to a bare ``python``), and ``setdefault``s
``MKL_THREADING_LAYER=GNU``.  All three are inert in this image — the bindir is
already on ``PATH``, and ``import torch`` above beats the MKL variable to first
use — but the worker is long-lived and runs other tools, so this is where to look
if one of them ever behaves oddly after a Func-E job.
"""

import multiprocessing
import pickle
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from enzyme_tk_app.app.paths import FUNCE_MODELS_DIR, SEQUENCE_EMBEDDINGS_DIR, UNIMOL_WEIGHTS_DIR
from enzyme_tk_app.app.utils.columns import COL_DATABASE, COL_ENTRY, COL_SEQUENCE
from enzyme_tk_app.app.utils.smiles_validation import split_reaction, validate_reaction_smiles

# Reaction-side embedding columns the step writes onto every row — enzymetk's own
# defaults for ``rxn_col`` / ``sub_col`` / ``prod_col``.  ``_load_databases``
# strips them from the pickles; the protein side comes from the pickle.
RXN_COLS = ["rxnfp", "substrate_unimol_repr", "product_unimol_repr"]

# The step's activity score.  enzymetk prefixes its output columns with its
# ``name`` argument, which defaults to "Funce" — we leave that default alone.
PRED_COL = "Funce_prediction"

# ── The only columns removed from the result ────────────────────────────────
# Everything else the step returns reaches the results grid untouched.
# Delete a name from this list to keep that column; a name that the installed
# enzymetk no longer emits is ignored rather than an error.
#
# The step already drops the scratch columns itself (its own ``LEAKED_COLS``), so
# most of this list is belt over braces.  It is kept because ``errors="ignore"``
# makes it free and because the failure it prevents is silent: those columns hold
# only the *last* ensemble member's values, and they would land in the grid right
# beside the correct ``Funce_<feature>_mean`` / ``_std`` pair with nothing to tell
# a reader which is which.
#
# The real invariant is wider than these names: no column whose cells are not
# JSON-native may survive.  ``_load_databases`` keeps every column a pickle
# carries, so a legacy pickle holding some *other* array column fails
# ``json.dumps`` after the compute has already succeeded.
DROPPED_COLS = [
    # Embeddings.  Every cell holds an ndarray, which ``json.dumps`` cannot
    # encode — keeping one of these breaks the result payload.  The step does
    # *not* drop these; its docstring says the caller must.
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

    The returned frame must be **freshly owned**: the step mutates it in place,
    adding the reaction vectors and score columns.  Caching loaded pickles here —
    the obvious optimization, since these run to hundreds of MB — would let one
    job's reaction survive into the next in a long-lived worker, scoring the wrong
    chemistry with no error to show for it.

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
        # row, and the query's vectors must win.
        #
        # The step overwrites all three columns on every row, so today this is
        # redundant.  It stays because the redundancy is not guaranteed: the step
        # assigns three *hard-coded* names, while the ``Funce`` it wraps reads
        # ``rxn_col`` / ``sub_col`` / ``prod_col`` from defaults the step never
        # passes.  Let those drift apart and Funce reads the pickle's stale reaction
        # instead — a confident ranking for the wrong chemistry, with no exception
        # and no shape mismatch to catch it.  This line is what makes that
        # impossible, for the cost of one ``errors="ignore"`` drop.
        frame = frame.drop(columns=RXN_COLS, errors="ignore")

        # Named exactly as the file is named in data/sequence_embeddings/, extension
        # included — see the data_loading module docstring.
        frame[COL_DATABASE] = db_path.name
        frames.append(frame)

    if not frames:
        raise ValueError(f"None of the selected databases could be read: {', '.join(skipped)}")

    return pd.concat(frames, ignore_index=True), skipped


@contextmanager
def _allow_forking():
    """Let a step fork worker processes while inside Celery's prefork pool.

    Celery runs each task in a *daemonic* child, and a daemonic process may not
    have children of its own.  ``unimol_tools`` builds conformers with a
    ``multiprocessing.Pool``, so under Celery it raises "daemonic processes are
    not allowed to have children" — which UniMol's own ``except`` swallows into a
    ``None`` embedding rather than an error.  Clearing the flag for the duration
    of the call is the standard Celery workaround.

    This wraps the step's whole ``execute()`` because UniMol runs deep inside it
    and the step exposes no narrower hook.  The two other phases are unaffected
    either way: ``subprocess`` never consults ``daemon`` (so RxnFP would run
    daemonic or not), and Funce's forward pass spawns nothing.  Nesting is safe —
    an inner call reads ``was_daemon`` as ``False`` and neither clears nor restores.

    Ceiling: unimol_tools pools up to 8 processes to embed our molecules, and a hard
    kill of the worker mid-call could orphan them.  That window is UniMol's alone,
    not the whole ``execute()`` — the pool exists only while UniMol runs, even
    though the flag is cleared for longer.  Forwarding a kwarg will not fix it:
    ``multi_process`` is read from the ``params`` dict ``UniMolRepr`` builds from
    its own named arguments, and anything else passed to it is dropped, so the flag
    never reaches the conformer generator.  Dropping this needs a change inside
    unimol_tools itself.
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
        ValueError: When the reaction SMILES is invalid, no database can be read, or
            the step rejects the reaction or an embedding width.
        FileNotFoundError: When the Func-E checkpoints or the UniMol checkpoint are
            absent — raised by the step, and reaching the UI as a raw traceback.
        RuntimeError: When RxnFP, UniMol, or the ensemble itself fails, likewise.
        ImportError: When ``enzymetk`` (or torch) is not available.
    """
    # Lazy import — enzymetk pulls in torch, which is heavy; worker only.
    import torch  # noqa: PLC0415
    from enzymetk import Funce_rxnfp_unimol  # noqa: PLC0415

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

    # Passing validation does *not* mean the raw string is a two-block reaction:
    # ``validate_reaction_smiles`` checks the (substrate, product) pair that
    # ``split_reaction`` derives, so a multi-arrow route is accepted — `A>>B>>C` reads
    # as (A, C) and the intermediate is never even parsed.  The step splits on a
    # single ">" and demands exactly three blocks, so it sees five and raises.
    # Rebuilding from the pair is what turns "what the validator approved" into "what
    # the step accepts", preserving today's reading instead of failing a reaction that
    # scores now.  It trims both sides on the way.
    substrate, product = split_reaction(smiles)
    reaction = f"{substrate}>>{product}"

    # ``db << step`` is enzymetk's own idiom (``Step.__rlshift__``).
    #
    # First argument is the *reaction*, not the id column — unlike the bare ``Funce``
    # step this replaces, which took ``id_col`` there.  Both are strings, so passing
    # the wrong one is accepted here and only fails once RxnFP tries to fingerprint
    # the literal text "Entry".
    #
    # Every database goes through in one call — see the batch note in the module
    # docstring.  ``_allow_forking`` covers the whole step because UniMol's conformer
    # pool is built deep inside it.
    with _allow_forking():
        scored = db_df << Funce_rxnfp_unimol(
            reaction,
            model_dir=str(FUNCE_MODELS_DIR),
            unimol_weights_dir=str(UNIMOL_WEIGHTS_DIR),
            # The app never downloads: a missing checkpoint is a data problem to
            # report, not ~660 MB to fetch inside a request.  This is the library
            # default too; naming it keeps that true if the default ever flips.
            download_if_missing=False,
            id_col=COL_ENTRY,
        )

    # The step leaves ranking to the caller.
    ranked = scored.sort_values(PRED_COL, ascending=False).head(top_n).reset_index(drop=True)

    # Everything the step returned is kept except the columns named at the top
    # of this module — see ``DROPPED_COLS``.  A column enzymetk adds later is
    # kept and shown rather than silently discarded.  The embeddings in that list
    # are not optional: ``json.dumps`` in the worker has no ``default=``, so one
    # surviving ndarray records this job as FAILURE after the scoring succeeded.
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
