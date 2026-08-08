"""Func-E Activity Prediction tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system, plus the
constants shared between ``modal.py`` (example picker) and ``compute.py``
(reaction lookup).

Func-E scores (enzyme, reaction) pairs with an ensemble of four attention
models — one per EC level — and returns the proteins predicted most active
on the query reaction.  The step itself is *prediction-only*: the protein
database ships pre-encoded, and ``compute._encode_reaction`` embeds the
query reaction before scoring.
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
    # The protein side is still embedded offline (ESM3, baked into the database
    # pickle), but the reaction is encoded at query time — so rxnfp and UniMol
    # run in the worker alongside torch.
    "libraries": ["torch", "rxnfp", "unimol"],
    "max_duration": 1800,
}

# The reaction behind the Funce_pairs.pkl fixture, kept as the first example so a
# run can be compared against the numbers the tool used to return.
DEHP_MEHP_SMILES = "CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)OCC(CC)CCCC>>CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)O"

# The same phthalate ester hydrolysis two carbons down each chain.  Nothing on
# disk was ever pre-encoded for it, so it exercises the query-time encoder.
DBP_MBP_SMILES = "CCCCOC(=O)c1ccccc1C(=O)OCCCC>>CCCCOC(=O)c1ccccc1C(=O)O"

# ``task_name`` is the name the example picker prefills into the Task Name field
# (see ``callbacks.populate_example_reaction``).
EXAMPLE_REACTIONS = [
    {
        "label": "DEHP → MEHP (phthalate monoester hydrolysis)",
        "value": DEHP_MEHP_SMILES,
        "task_name": "DEHP-MEHP",
    },
    {
        "label": "DBP → MBP (phthalate monoester hydrolysis)",
        "value": DBP_MBP_SMILES,
        "task_name": "DBP-MBP",
    },
]
