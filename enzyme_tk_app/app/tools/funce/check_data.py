"""Data availability check for the Func-E tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.paths import FUNCE_MODELS_DIR, SEQUENCE_EMBEDDINGS_DIR, UNIMOL_WEIGHTS_DIR

# The ensemble loads one model per EC level; each needs a config + checkpoint pair.
EC_LEVELS = (1, 2, 3, 4)
_CHECKPOINT_STEM = "run_easy_0-50_ESRP_{ec}_model_1_500000"

# What the UniMol step resolves under the ``weights_dir`` compute passes it — its own
# ``MODEL_CONFIG_V2["weight"]["164m"]``, matching the model and size
# ``compute._encode_reaction`` asks for (unimolv2 / 164m, the UniMol defaults).
# Duplicated from unimol_tools rather than imported: reading it live would pull torch
# into every home-page render.  The step raises naming both paths if they ever diverge.
_UNIMOL_CHECKPOINT = ("modelzoo", "164M", "checkpoint.pt")


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = OK).

    Func-E requires at least one pre-encoded protein database pickle, the
    complete four-model ensemble — a partial ensemble still runs but
    silently changes the prediction, so treat it as missing — and the UniMol
    checkpoint used to embed the query reaction.

    Returns:
        A list of 0-3 labels naming the missing items.
    """
    missing: list[str] = []

    if not SEQUENCE_EMBEDDINGS_DIR.exists() or not any(SEQUENCE_EMBEDDINGS_DIR.glob("*.pkl")):
        missing.append("Pre-encoded protein databases (data/sequence_embeddings/*.pkl)")

    for ec in EC_LEVELS:
        stem = _CHECKPOINT_STEM.format(ec=ec)
        if (
            not (FUNCE_MODELS_DIR / f"{stem}_conf.pkl").exists()
            or not (FUNCE_MODELS_DIR / f"{stem}_checkpoint.pth").exists()
        ):
            missing.append("Func-E ensemble checkpoints (data/funce_models/)")
            break

    # Check the exact checkpoint rather than just a populated directory: the data
    # mount is read-only, so unimol_tools cannot download a replacement, and a
    # wrongly-laid-out unimol_weights/ would otherwise pass and fail at run time.
    if not UNIMOL_WEIGHTS_DIR.joinpath(*_UNIMOL_CHECKPOINT).exists():
        missing.append("UniMol weights (data/unimol_weights/)")

    return missing
