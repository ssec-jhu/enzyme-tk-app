"""Data availability check for the Func-E tool.

Returns a list of human-readable labels describing missing data items.
An empty list means the tool's data prerequisites are satisfied.
"""

from enzyme_tk_app.app.paths import FUNCE_DB_DIR, FUNCE_MODELS_DIR

# The ensemble loads one model per EC level; each needs a config + checkpoint pair.
EC_LEVELS = (1, 2, 3, 4)
_CHECKPOINT_STEM = "run_easy_0-50_ESRP_{ec}_model_1_500000"


def check_data() -> list[str]:
    """Return labels of missing data items (empty list = OK).

    Func-E requires at least one pre-encoded protein database pickle and
    the complete four-model ensemble — a partial ensemble still runs but
    silently changes the prediction, so treat it as missing.

    Returns:
        A list of 0-2 labels naming the missing items.
    """
    missing: list[str] = []

    if not FUNCE_DB_DIR.exists() or not any(FUNCE_DB_DIR.glob("*.pkl")):
        missing.append("Pre-encoded protein databases (data/funce_db/*.pkl)")

    for ec in EC_LEVELS:
        stem = _CHECKPOINT_STEM.format(ec=ec)
        if (
            not (FUNCE_MODELS_DIR / f"{stem}_conf.pkl").exists()
            or not (FUNCE_MODELS_DIR / f"{stem}_checkpoint.pth").exists()
        ):
            missing.append("Func-E ensemble checkpoints (data/funce_models/)")
            break

    return missing
