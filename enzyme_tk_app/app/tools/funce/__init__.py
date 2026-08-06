"""Func-E Activity Prediction tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system, plus the
constants shared between ``modal.py`` (example picker) and ``compute.py``
(reaction lookup).

Func-E scores (enzyme, reaction) pairs with an ensemble of four attention
models — one per EC level — and returns the proteins predicted most active
on the query reaction.  The step itself is *prediction-only*: the protein
database ships pre-encoded and the reaction must already be embedded.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_ACTIVITY
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "funce",
    "title": "Func-E Activity Prediction",
    "desc": (
        "Predicts which enzymes in a pre-encoded protein database are active on a "
        "given reaction, using an ensemble of attention models (one per EC level)."
    ),
    "icon": ICON_TOOL_ACTIVITY,
    "order": 5,
    # Only torch runs at query time — the ESM3 / RxnFP / UniMol embeddings are
    # baked into the database pickle offline, so they are not runtime deps.
    "libraries": ["torch"],
    "max_duration": 1800,
}

# The only reaction currently pre-encoded in data/sequence_embeddings/*.pkl.  Until the
# reaction-to-fingerprint encoder is wired up, this is the sole query that
# ``compute._encode_reaction`` can resolve.
DEHP_MEHP_SMILES = "CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)OCC(CC)CCCC>>CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)O"

EXAMPLE_REACTIONS = [
    {
        "label": "DEHP → MEHP (phthalate monoester hydrolysis)",
        "value": DEHP_MEHP_SMILES,
    },
]
