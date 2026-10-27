"""Master column-name constants for all tools and results.

Every DataFrame column string used across the app lives here, grouped by
domain, and each is written once as ``_col(name, description)``: the name is
what the data carries, the description is the sentence ``build_ag_grid`` shows
as that column's header tooltip.  When enzymetk or an upstream data source
renames a column, update this file — all tools, results layouts, and tests
pick up the change automatically.
"""

COLUMN_DESCRIPTIONS: dict[str, str] = {}
"""Field name → one plain-English sentence, filled by ``_col`` as the module loads.

``build_ag_grid`` turns each entry into the column's header tooltip and info
icon, so a user can find out what a column means without leaving the page.
Write for a scientist who has not read the tool's source.  A field shared by
several tools (``database``, ``target``, ``mismatch``) means the same thing in
each, so it has one entry.  ``test_every_results_column_has_a_description``
fails the build when a tool declares a column that is missing here.
"""


def _col(name: str, description: str) -> str:
    """Record ``name``'s header help and return ``name``, so a constant and its help are one line."""
    # A dict literal had ruff's F601 to catch a duplicate key; this is its replacement.

    if name in COLUMN_DESCRIPTIONS:
        raise ValueError(f"column {name!r} registered twice")
    COLUMN_DESCRIPTIONS[name] = description
    return name


# ── CSV / Data-Loading Columns ───────────────────────────────────────────────
# Columns used during CSV ingestion and molecule extraction.

COL_UNMAPPED_SMILES = _col("unmapped", "Reaction SMILES, substrates >> products, without atom maps.")
COL_MOL_SMILES = _col(
    "molecule_smiles", "SMILES of the matching molecule, one substrate or product of the reaction in its row."
)
COL_MOL_INDEX = _col(
    "molecule_index", "Position of this molecule within its reaction's substrate or product list, counting from 0."
)
# Added at runtime, like ``COL_RXN_SVG``.
COL_MOL_SVG = _col("molecule_svg", "Drawing of the database molecule. Click it to compare it with your query.")

EXCLUDE_COLS = frozenset({"Unnamed: 0"})
"""Columns to drop automatically when loading CSVs (internal pandas index, etc.)."""

# ── Sequence / Protein Metadata Columns ──────────────────────────────────────
# Columns present in the protein-sequence CSVs.

COL_EC_NUMBER = _col("EC number", "Enzyme Commission number(s): the class of reaction this protein catalyses.")
COL_SEQUENCE = _col("Sequence", "Amino-acid sequence. Hover a cell to see all of it.")
COL_ENTRY = _col("Entry", "UniProt accession of the protein.")

# ── EnzymeTK Similarity-Score Columns ────────────────────────────────────────
# Exact DataFrame column names produced by enzymetk's execute() methods.
# If enzymetk renames a column, update only here.

COL_TANIMOTO = _col(
    "TanimotoSimilarity", "Tanimoto similarity to your query, from 0 (nothing shared) to 1 (identical fingerprints)."
)
COL_COSINE = _col(
    "CosineSimilarity", "Cosine similarity to your query, from 0 (nothing shared) to 1 (identical fingerprints)."
)
COL_RUSSELL = _col(
    "RusselSimilarity", "Russell similarity to your query, from 0 (nothing shared) to 1 (identical fingerprints)."
)

ENZYMETK_SIMILARITY_COLUMNS: dict[str, str] = {
    "tanimoto": COL_TANIMOTO,
    "cosine": COL_COSINE,
    "russell": COL_RUSSELL,
}
"""Map from ``SimilarityAlgorithm.value`` → enzymetk DataFrame column name.

Keyed by the plain string values (not enum members) to avoid a
circular import with the enum defined in
``substrate_product_similarity/__init__.py``.
"""

# ── Reaction / Rule Metadata Columns ────────────────────────────────────────
# Columns from the enzymetk reaction-similarity output and the reactions CSV.

# Added at runtime, not read from the file: each tool tags a hit with the database it came from.
COL_DATABASE = _col("database", "The reference database file this row came from.")
COL_ID = _col("id", "Record ID: the reaction's EC number joined to its reaction index.")
COL_RXN_IDX = _col("rxn_idx", "Index of the source BRENDA entry; rows split from the same entry share it.")
COL_MAPPED = _col(
    "mapped", "Reaction SMILES with atom maps, linking each product atom to the substrate atom it came from."
)
COL_ORIG_RXN_TEXT = _col("orig_rxn_text", "The reaction as written in BRENDA, by compound name.")
COL_RULE = _col("rule", "Reaction rule (SMARTS template) describing the bonds the enzyme breaks and forms.")
COL_RULE_ID = _col("rule_id", "ID of the reaction rule; rows with the same ID follow the same bond changes.")
COL_SOURCE = _col(
    "source",
    "How EnzymeMap got this reaction: 'direct' is as recorded in BRENDA, 'suggested' is EnzymeMap's "
    "correction of an entry it could not map, and 'reversed' is the reverse direction of a reversible reaction.",
)
COL_STEPS = _col(
    "steps", "Whether BRENDA records a single step, a multi-step reaction, or one step taken from a multi-step one."
)
COL_QUALITY = _col(
    "quality",
    "Share of this EC class's reactions that follow the same reaction rule, from 0 to 1. "
    "Higher means a more typical mechanism for the class.",
)
COL_NATURAL = _col("natural", "True when BRENDA lists this as the enzyme's natural (physiological) reaction.")

# ── Bio Metadata Columns ────────────────────────────────────────────────────

COL_ORGANISM = _col("organism", "Organism the reaction was reported in.")
COL_PROTEIN_REFS = _col("protein_refs", "Accessions of the proteins reported to catalyse this reaction.")
COL_PROTEIN_DB = _col("protein_db", "Database the protein accessions come from (UniProt or Swiss-Prot).")
# The results' EC column — ``COL_EC_NUMBER`` is the sequence CSV's.
COL_EC_NUM = _col("ec_num", "Enzyme Commission number: the class of enzyme that catalyses this reaction.")

# ── Substrates / Products Text Columns ──────────────────────────────────────

COL_SUBSTRATES = _col("substrates", "Atom-mapped SMILES of each substrate.")
COL_PRODUCTS = _col("products", "Atom-mapped SMILES of each product.")

# ── Molecular Descriptor Columns ────────────────────────────────────────────
# Physicochemical descriptors attached to substrates and products (RDKit).

COL_SUBSTRATES_MOLWT = _col("substrates_MolWt", "Combined molecular weight of the substrates, in daltons.")
COL_SUBSTRATES_TPSA = _col(
    "substrates_TPSA", "Topological polar surface area of the substrates, in Å². Higher means more polar."
)
COL_SUBSTRATES_MOLLOGP = _col(
    "substrates_MolLogP", "Predicted logP of the substrates. Higher is more fat-soluble, lower more water-soluble."
)
COL_SUBSTRATES_MAX_PARTIAL_CHARGE = _col(
    "substrates_MaxPartialCharge", "Largest atomic partial charge in the substrates."
)
COL_SUBSTRATES_MIN_PARTIAL_CHARGE = _col(
    "substrates_MinPartialCharge", "Smallest (most negative) atomic partial charge in the substrates."
)

COL_PRODUCTS_MOLWT = _col("products_MolWt", "Combined molecular weight of the products, in daltons.")
COL_PRODUCTS_TPSA = _col(
    "products_TPSA", "Topological polar surface area of the products, in Å². Higher means more polar."
)
COL_PRODUCTS_MOLLOGP = _col(
    "products_MolLogP", "Predicted logP of the products. Higher is more fat-soluble, lower more water-soluble."
)
COL_PRODUCTS_MAX_PARTIAL_CHARGE = _col("products_MaxPartialCharge", "Largest atomic partial charge in the products.")
COL_PRODUCTS_MIN_PARTIAL_CHARGE = _col(
    "products_MinPartialCharge", "Smallest (most negative) atomic partial charge in the products."
)

# ── Rendered SVG Columns ────────────────────────────────────────────────────

# Added at runtime.
COL_RXN_SVG = _col("reaction_svg", "Drawing of the database reaction. Click it to compare it with your query.")

# ── BLAST / Sequence-Similarity Columns ─────────────────────────────────────
# Columns output by diamond / BLAST and the protein-metadata merge.

COL_QUERY = _col("query", "Name of your query sequence or structure.")
COL_TARGET = _col("target", "Accession of the matching protein in the database.")
COL_SEQ_IDENTITY = _col("sequence identity", "Percentage of aligned positions with the same amino acid as your query.")
COL_BITSCORE = _col("bitscore", "Alignment score that does not depend on database size. Higher means a better match.")
COL_EVALUE = _col("e-value", "Number of hits this good you'd expect by chance. Smaller is more significant.")
# diamond's ``length`` is the alignment's — the protein's is ``COL_LENGTH`` (``Length``).
COL_ALIGNMENT_LENGTH = _col("length", "Number of positions in the alignment, gaps included.")
COL_MISMATCH = _col("mismatch", "Aligned positions where the amino acids differ.")
COL_GAPOPEN = _col("gapopen", "Number of gaps opened in the alignment.")
COL_QUERY_START = _col("query start", "Position in your query where the alignment starts.")
COL_QUERY_END = _col("query end", "Position in your query where the alignment ends.")
COL_TARGET_START = _col("target start", "Position in the matching protein where the alignment starts.")
COL_TARGET_END = _col("target end", "Position in the matching protein where the alignment ends.")
COL_RESIDUE_0INDEX = _col("Residue_0index", "Predicted catalytic residue positions, counting from 0.")
COL_RESIDUE_1INDEX = _col("Residue_1index", "Predicted catalytic residue positions, counting from 1 as UniProt does.")
COL_ACTIVE_SITE_COUNT = _col("active_site_residue_counts", "Number of active-site residues.")
COL_POLARITY = _col("Polarity", "Average polarity of the protein's residues.")
COL_TEMPERATURE = _col("temperature", "Optimal temperature of the enzyme.")
COL_LENGTH = _col("Length", "Length of the protein, in amino acids.")
COL_MASS = _col("Mass", "Mass of the protein, in daltons.")
# Optional.  Raw cells are UniProt blobs (``COFACTOR: Name=heme b; Xref=...;``), so a
# reader wants the ``Name=`` values — ``extract_cofactor_names()`` in
# ``utils/data_loading.py`` is the one parser for them.
COL_COFACTOR = _col("Cofactor", "Cofactors the enzyme needs, such as metal ions or vitamins.")

# ── FoldSeek Columns ────────────────────────────────────────────────────────
# FoldSeek's own output names, written as literals in
# ``sequence_structure_similarity/results.py`` — one library's contract, so no
# constant.  They measure what their diamond twins above do, so they say the same.

_col("fident", "Fraction of aligned positions with the same amino acid as your query, from 0 to 1.")
_col("bits", COLUMN_DESCRIPTIONS[COL_BITSCORE])
_col("evalue", COLUMN_DESCRIPTIONS[COL_EVALUE])
_col("alnlen", COLUMN_DESCRIPTIONS[COL_ALIGNMENT_LENGTH])
_col("qstart", COLUMN_DESCRIPTIONS[COL_QUERY_START])
_col("qend", COLUMN_DESCRIPTIONS[COL_QUERY_END])
_col("tstart", COLUMN_DESCRIPTIONS[COL_TARGET_START])
_col("tend", COLUMN_DESCRIPTIONS[COL_TARGET_END])

# ── UniProt Pass-Through Columns ────────────────────────────────────────────
# Metadata a sequence database may carry.  No code reads these by name —
# sequence similarity appends every column it has no def for as a bare one —
# so they get header help but no constant.

_col("Reviewed", "'reviewed' for manually curated Swiss-Prot entries, 'unreviewed' for automatic TrEMBL ones.")
_col("Entry Name", "UniProt's mnemonic name for the entry.")
_col("Protein names", "Recommended and alternative names of the protein.")
_col("Gene Names", "Names of the gene that encodes the protein.")
_col("Organism", "Organism the protein comes from.")
_col("Organism (ID)", "NCBI taxonomy ID of the organism.")
_col("Taxonomic lineage (Ids)", "NCBI taxonomy IDs of the organism's lineage.")
_col("Fragment", "Marks entries whose sequence is incomplete.")
_col("Active site", "Residues UniProt annotates as directly involved in catalysis.")
_col("Binding site", "Residues UniProt annotates as binding a substrate, cofactor, or ion.")
_col("Catalytic activity", "The reaction(s) UniProt says this enzyme catalyses.")
_col("Subunit structure", "How the protein assembles with itself or other proteins.")

# ── Func-E Columns ──────────────────────────────────────────────────────────
# enzymetk's output names, spelled out as literals in ``funce/results.py`` on
# purpose (its ``_get_column_defs`` docstring says why), so no constant here.

_col(
    "Funce_prediction",
    "Func-E's activity score for this protein on your reaction, from 0 to 1, averaged over its models. "
    "Higher means more likely to be active.",
)
_col("Funce_std_preds", "How much Func-E's models disagree on the activity score. Larger means less certain.")
_col("Funce_epistemic", "Always True: marks Funce_std_preds as model uncertainty measured across the ensemble.")

# Func-E also predicts each of these properties, once per model in its ensemble,
# and reports the mean and standard deviation as ``Funce_<property>_mean`` /
# ``_std``.  Each property is described above, so the pair is built from that
# rather than written out 26 more times.
for _prop in (
    COL_LENGTH,
    COL_MASS,
    COL_POLARITY,
    COL_TEMPERATURE,
    COL_SUBSTRATES_MOLWT,
    COL_SUBSTRATES_MOLLOGP,
    COL_SUBSTRATES_MAX_PARTIAL_CHARGE,
    COL_SUBSTRATES_MIN_PARTIAL_CHARGE,
    COL_PRODUCTS_MOLWT,
    COL_PRODUCTS_TPSA,
    COL_PRODUCTS_MOLLOGP,
    COL_PRODUCTS_MAX_PARTIAL_CHARGE,
    COL_PRODUCTS_MIN_PARTIAL_CHARGE,
):
    _col(f"Funce_{_prop}_mean", f"Func-E's prediction, averaged over its models. {COLUMN_DESCRIPTIONS[_prop]}")
    _col(f"Funce_{_prop}_std", f"How much Func-E's models disagree on Funce_{_prop}_mean. Larger means less certain.")

# ── Timer Tool Demo Columns ─────────────────────────────────────────────────
# Synthetic columns generated by the demo timer tool.

COL_SAMPLE_ID = _col("sample_id", "Identifier of the synthetic demo sample.")
COL_ACTIVITY_SCORE = _col("activity_score", "Synthetic demo activity score.")
COL_STABILITY_SCORE = _col("stability_score", "Synthetic demo stability score.")
COL_TEMPERATURE_C = _col("temperature_c", "Synthetic demo temperature, in °C.")
COL_YIELD_PCT = _col("yield_pct", "Synthetic demo yield, as a percentage.")
