"""Func-E Activity Prediction tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system, plus the
constants shared between ``modal.py`` (example picker) and ``compute.py``
(reaction lookup).

Func-E scores (enzyme, reaction) pairs with an ensemble of four attention
models — one per EC level — and returns the proteins predicted most active
on the query reaction.  The protein database ships pre-encoded; the query
reaction is encoded at run time by the step ``compute`` calls.
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

# The two reactions below the first are **supplied by the client** — do not reword the
# chemistry, add a leaving group, or split a dot-joined side to make them look tidier.
# Both need every molecule they name: the step embeds each one separately and SUMS the
# per-side vectors into Func-E's single 768-d slot, so dropping one changes the score.

# The reaction behind the Funce_pairs.pkl fixture, kept as the first example so a
# run can be compared against the numbers the tool used to return.
DEHP_MEHP_SMILES = "CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)OCC(CC)CCCC>>CCCCC(CC)COC(=O)C1=CC=CC=C1C(=O)O"

# Two substrates: the amino acid and the ketone it alkylates.
TRPB_ALKYLATION_SMILES = "N[C@H](C(O)=O)CO.CCC(C1=CC=CC=C1)=O>>CC(C(C2=CC=CC=C2)=O)C[C@@H](C(O)=O)N"

# Three substrates, one of them a bare fluoride ion.  ``[F-]`` is monatomic, which is
# the shape most likely to defeat a 3D conformer generator — UniMol does embed it
# (768-d, finite), so leave it in: it is the nucleophile the reaction is named for.
FLUORINASE_SMILES = (
    "CSCC[C@@H](C(O)=O)N.NC1=C2N=CN([C@@H]3O[C@@H]([C@H]([C@H]3O)O)CCl)C2=NC=N1.[F-]"
    ">>NC4=C5N=CN([C@@H]6O[C@@H]([C@H]([C@H]6O)O)CF)C5=NC=N4"
)

# ``task_name`` is the name the example picker prefills into the Task Name field
# (see ``callbacks.populate_example_reaction``).  It is deliberately short and
# kebab-case while the label carries the client's full title: the My Tasks table has no
# max-width on its Task Name column, so a title-length name there squeezes the other
# eight columns.
EXAMPLE_REACTIONS = [
    {
        "label": "DEHP → MEHP (phthalate monoester hydrolysis)",
        "value": DEHP_MEHP_SMILES,
        "task_name": "DEHP-MEHP",
    },
    {
        "label": "Asymmetric Alkylation of Ketones Catalyzed by Engineered TrpB",
        "value": TRPB_ALKYLATION_SMILES,
        "task_name": "trpb-alkylation",
    },
    {
        "label": "Fluorinase for Improved Fluorination Efficiency with a Non-native Substrate",
        "value": FLUORINASE_SMILES,
        "task_name": "fluorinase",
    },
]
