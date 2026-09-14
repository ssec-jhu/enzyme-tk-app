"""Master column-name constants for all tools and results.

Every DataFrame column string used across the app lives here,
grouped by domain.  When enzymetk or an upstream data source
renames a column, update this file — all tools, results layouts,
and tests pick up the change automatically.
"""

# ── CSV / Data-Loading Columns ───────────────────────────────────────────────
# Columns used during CSV ingestion and molecule extraction.

COL_UNMAPPED_SMILES = "unmapped"
"""Column in the reactions CSV that contains the un-mapped reaction SMILES."""

COL_MOL_SMILES = "molecule_smiles"
"""Individual molecule SMILES extracted from a reaction."""

COL_MOL_INDEX = "molecule_index"
"""0-based position of the molecule within the substrate/product list."""

COL_MOL_SVG = "molecule_svg"
"""Rendered SVG of the molecule (added at runtime)."""

EXCLUDE_COLS = frozenset({"Unnamed: 0"})
"""Columns to drop automatically when loading CSVs (internal pandas index, etc.)."""

# ── Sequence / Protein Metadata Columns ──────────────────────────────────────
# Columns present in the protein-sequence CSVs.

COL_EC_NUMBER = "EC number"
"""EC classification in the sequence CSV."""

COL_SEQUENCE = "Sequence"
"""Protein sequence string in the sequence CSV."""

COL_ENTRY = "Entry"
"""Protein entry ID in the sequence CSV."""

# ── EnzymeTK Similarity-Score Columns ────────────────────────────────────────
# Exact DataFrame column names produced by enzymetk's execute() methods.
# If enzymetk renames a column, update only here.

COL_TANIMOTO = "TanimotoSimilarity"
"""Tanimoto similarity score column produced by enzymetk."""

COL_COSINE = "CosineSimilarity"
"""Cosine similarity score column produced by enzymetk."""

COL_RUSSELL = "RusselSimilarity"
"""Russell similarity score column produced by enzymetk."""

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

COL_DATABASE = "database"
"""Source database tag (added at runtime from the CSV filename stem)."""

COL_ID = "id"
"""Reaction or record identifier."""

COL_RXN_IDX = "rxn_idx"
"""Reaction index within the database."""

COL_MAPPED = "mapped"
"""Mapped (atom-mapped) reaction SMILES."""

COL_ORIG_RXN_TEXT = "orig_rxn_text"
"""Original reaction text before any processing."""

COL_RULE = "rule"
"""Reaction rule string."""

COL_RULE_ID = "rule_id"
"""Reaction rule identifier."""

COL_SOURCE = "source"
"""Data source label."""

COL_STEPS = "steps"
"""Number of reaction steps."""

COL_QUALITY = "quality"
"""Quality flag or score."""

COL_NATURAL = "natural"
"""Natural/non-natural indicator."""

# ── Bio Metadata Columns ────────────────────────────────────────────────────

COL_ORGANISM = "organism"
"""Organism name."""

COL_PROTEIN_REFS = "protein_refs"
"""Protein reference identifiers."""

COL_PROTEIN_DB = "protein_db"
"""Protein database source."""

COL_EC_NUM = "ec_num"
"""EC number in the results (distinct from ``COL_EC_NUMBER`` in the raw CSV)."""

# ── Substrates / Products Text Columns ──────────────────────────────────────

COL_SUBSTRATES = "substrates"
"""Concatenated substrate SMILES text."""

COL_PRODUCTS = "products"
"""Concatenated product SMILES text."""

# ── Molecular Descriptor Columns ────────────────────────────────────────────
# Physicochemical descriptors attached to substrates and products.

COL_SUBSTRATES_MOLWT = "substrates_MolWt"
COL_SUBSTRATES_TPSA = "substrates_TPSA"
COL_SUBSTRATES_MOLLOGP = "substrates_MolLogP"
COL_SUBSTRATES_MAX_PARTIAL_CHARGE = "substrates_MaxPartialCharge"
COL_SUBSTRATES_MIN_PARTIAL_CHARGE = "substrates_MinPartialCharge"

COL_PRODUCTS_MOLWT = "products_MolWt"
COL_PRODUCTS_TPSA = "products_TPSA"
COL_PRODUCTS_MOLLOGP = "products_MolLogP"
COL_PRODUCTS_MAX_PARTIAL_CHARGE = "products_MaxPartialCharge"
COL_PRODUCTS_MIN_PARTIAL_CHARGE = "products_MinPartialCharge"

# ── Rendered SVG Columns ────────────────────────────────────────────────────

COL_RXN_SVG = "reaction_svg"
"""Rendered SVG of the reaction (added at runtime)."""

# ── BLAST / Sequence-Similarity Columns ─────────────────────────────────────
# Columns output by diamond / BLAST and the protein-metadata merge.

COL_QUERY = "query"
"""BLAST query identifier."""

COL_TARGET = "target"
"""BLAST target (hit) identifier."""

COL_SEQ_IDENTITY = "sequence identity"
"""Percentage sequence identity from diamond output."""

COL_BITSCORE = "bitscore"
"""BLAST bit-score."""

COL_EVALUE = "e-value"
"""BLAST expect-value."""

COL_ALIGNMENT_LENGTH = "length"
"""Alignment length (diamond output column)."""

COL_MISMATCH = "mismatch"
"""Number of mismatches in the alignment."""

COL_GAPOPEN = "gapopen"
"""Number of gap openings in the alignment."""

COL_QUERY_START = "query start"
"""Query start position in the alignment."""

COL_QUERY_END = "query end"
"""Query end position in the alignment."""

COL_TARGET_START = "target start"
"""Target start position in the alignment."""

COL_TARGET_END = "target end"
"""Target end position in the alignment."""

COL_RESIDUE_0INDEX = "Residue_0index"
"""0-indexed catalytic residue positions."""

COL_RESIDUE_1INDEX = "Residue_1index"
"""1-indexed catalytic residue positions."""

COL_ACTIVE_SITE_COUNT = "active_site_residue_counts"
"""Number of active-site residues."""

COL_POLARITY = "Polarity"
"""Average polarity score."""

COL_TEMPERATURE = "temperature"
"""Optimal temperature."""

COL_LENGTH = "Length"
"""Sequence length (protein metadata)."""

COL_MASS = "Mass"
"""Molecular mass (protein metadata)."""

COL_COFACTOR = "Cofactor"
"""UniProt cofactor annotation (optional protein metadata).

Raw cells are annotation blobs — ``COFACTOR: Name=heme b; Xref=...; Evidence=...;`` —
so a reader wants the ``Name=`` values, not the cell.  ``extract_cofactor_names()`` in
``utils/data_loading.py`` is the one parser for them."""

# ── Timer Tool Demo Columns ─────────────────────────────────────────────────
# Synthetic columns generated by the demo timer tool.

COL_SAMPLE_ID = "sample_id"
COL_ACTIVITY_SCORE = "activity_score"
COL_STABILITY_SCORE = "stability_score"
COL_TEMPERATURE_C = "temperature_c"
COL_YIELD_PCT = "yield_pct"
