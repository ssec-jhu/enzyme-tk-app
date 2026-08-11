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

# The four reactions below are *sanity checks*: the answer is known before the run.
# The first three name an enzyme that is actually embedded in one of the shipped
# databases, so a healthy run puts that Entry at or near rank 1; the fourth names an
# enzyme class no database contains, so it must not.  Every side is a single molecule
# — ``compute._encode_reaction`` hands each whole side to UniMol as one structure, so a
# dot-joined side is embedded as one nonsense molecule.  Leaving groups are therefore
# omitted, exactly as DEHP → MEHP omits the released 2-ethylhexanol.

# Ground truth: EnzymeMap rxn_idx 306389 lists A0A0A1H8I4 (aconitate isomerase,
# EC 5.3.3.7) as the catalyst, and that protein is in enzymes_sample_100_but_90.pkl.
# trans- to cis-aconitate is a pure double-bond geometry flip — no atoms gained or lost.
# Observed over all three databases (104 candidates): A0A0A1H8I4 ranks 1st at 0.9895
# with the tightest ensemble spread in the table (std 0.0067); the runner-up scores
# 0.5533 at std 0.3970.  Treat that gap as the regression baseline.
ACONITATE_SMILES = r"O=C(O)/C=C(\CC(=O)O)C(=O)O>>O=C(O)/C=C(/CC(=O)O)C(=O)O"

# Ground truth in a different EC class, so a run that only scores hydrolases well is
# visible as such.  EnzymeMap rxn_idx 292676 lists A0A075FBG7 (9,13-epoxylabda-14-ene
# synthase, EC 4.2.3.189), also in enzymes_sample_100_but_90.pkl.  A diterpene cyclase
# closes an ether ring across the labdane skeleton; the diphosphate leaving group is
# not written.
LABDANE_SMILES = (
    r"C/C(=C\COP(=O)(O)OP(=O)(O)O)CC[C@@]1(O)[C@H](C)CC[C@H]2C(C)(C)CCC[C@@]21C"
    r">>C=CC1(C)CC[C@@]2(O1)[C@H](C)CC[C@H]1C(C)(C)CCC[C@@]12C"
)

# EC-analogue rather than an exact pair: the standard 4-nitrophenyl acetate esterase
# assay.  A0A024SC78 (cutinase, EC 3.1.1.74) is the one protein present in *both*
# enzymes_sample_10_but_9.pkl and enzymes_sample_100_but_90.pkl, so it should surface
# twice, once per ``database``.  Tests generalisation, not a memorised pair.
PNP_ACETATE_SMILES = "CC(=O)Oc1ccc([N+](=O)[O-])cc1>>O=[N+]([O-])c1ccc(O)cc1"

# Negative control.  Glutamate → glutamine is EC 6.3.1.2, and no protein in any shipped
# database is a ligase: of the 95 embedded proteins the 60 that carry an EC span only
# classes 1-5.  Chosen over a catechol dioxygenase (EC 1.13.11.1) because EC 1.14
# monooxygenases *are* present, which would make that a near-neighbour, not a negative.
#
# It is a *soft* negative, not a floor.  Observed top score 0.8265 (A0A095C6S0, an
# amine oxidase — the closest thing to amino-acid chemistry the databases hold) at
# std 0.1858.  The signal to read is the margin, not the absolute value: a genuine
# pair clears 0.98 with std under 0.01, so a run where this reaction reaches the
# ground-truth examples' scores means the ensemble has stopped discriminating.
GLUTAMINE_SMILES = "N[C@@H](CCC(=O)O)C(=O)O>>N[C@@H](CCC(N)=O)C(=O)O"

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
    {
        "label": "Aconitate isomerisation — expect A0A0A1H8I4 (EC 5.3.3.7)",
        "value": ACONITATE_SMILES,
        "task_name": "A0A0A1H8I4-aconitate",
    },
    {
        "label": "Labdane cyclisation — expect A0A075FBG7 (EC 4.2.3.189)",
        "value": LABDANE_SMILES,
        "task_name": "A0A075FBG7-labdane",
    },
    {
        "label": "pNP-acetate hydrolysis — expect A0A024SC78 (EC 3.1.1.74)",
        "value": PNP_ACETATE_SMILES,
        "task_name": "A0A024SC78-pNP",
    },
    {
        "label": "Glutamate → glutamine — negative control (EC 6.3.1.2)",
        "value": GLUTAMINE_SMILES,
        "task_name": "glutamine-negative",
    },
]
