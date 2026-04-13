"""Substrate/Product Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system,
``MoleculeRole`` — the single source of truth for the substrate /
product role enum, and ``get_similarity_algorithms`` — the single
source of truth for the similarity metrics available in this tool.
"""

import enum

from enzyme_tk_app.app.components.icons import ICON_TOOL_REACTION
from enzyme_tk_app.app.tools import ToolDef


class MoleculeRole(enum.StrEnum):
    """Which side of a reaction SMILES (``substrates>>products``) to search.

    Members compare equal to their string values (``StrEnum``), so
    Dash radio-button values, JSON params, and Redis payloads
    round-trip without explicit ``.value`` conversion.
    """

    SUBSTRATE = "substrate"
    PRODUCT = "product"


class SimilarityAlgorithm(enum.StrEnum):
    """Available similarity metrics for Morgan fingerprint comparison.

    Each member's ``.value`` is the short key used in params / API
    calls.  The ``.column`` property returns the **exact** DataFrame
    column name produced by ``enzymetk.SubstrateDist.execute()``.
    If enzymetk renames a column, only ``_ENZYMETK_COLUMNS`` needs
    updating.

    Why three separate representations?

    - **value** (``"tanimoto"``) — *our* API contract, stored in
      Redis job params and sent in JSON.  Stable across enzymetk
      upgrades; short and convenient for URLs / serialisation.
    - **column** (``"TanimotoSimilarity"``) — *enzymetk's* contract,
      the literal DataFrame column name its ``execute()`` method
      produces.  Isolated in ``_ENZYMETK_COLUMNS`` so a column
      rename in enzymetk is a one-line fix with no migration.
    - **label** (``"Tanimoto"``) — UI display text, derived from the
      member name.  Decoupled so it can be changed without touching
      the API or enzymetk layer.
    """

    TANIMOTO = "tanimoto"
    COSINE = "cosine"
    RUSSELL = "russell"

    @property
    def label(self) -> str:
        """Human-readable name for dropdown display."""
        return self.name.capitalize()

    @property
    def column(self) -> str:
        """Exact DataFrame column name produced by enzymetk."""
        return _ENZYMETK_COLUMNS[self]


_ENZYMETK_COLUMNS: dict[SimilarityAlgorithm, str] = {
    SimilarityAlgorithm.TANIMOTO: "TanimotoSimilarity",
    SimilarityAlgorithm.COSINE: "CosineSimilarity",
    SimilarityAlgorithm.RUSSELL: "RusselSimilarity",
}


TOOL_DEF: ToolDef = {
    "slug": "substrate-product-similarity",
    "title": "Substrate/Product Similarity",
    "desc": (
        "Molecular similarity search using Morgan circular fingerprints with Tanimoto, Russell, and Cosine scoring."
    ),
    "icon": ICON_TOOL_REACTION,
    "order": 2,
    "libraries": ["rdkit"],
    "max_duration": 180,
}


def get_similarity_algorithms() -> list[dict]:
    """Return the list of available substrate/product similarity algorithms.

    Each entry is a dict with:
    - ``label``: human-readable name for dropdown display.
    - ``value``: short key used in params / API calls.
    - ``column``: the **exact** DataFrame column name produced by
      ``enzymetk.similarity_substrate_step.SubstrateDist.execute()``.

    All values are derived from :class:`SimilarityAlgorithm`.

    Returns:
        List of algorithm descriptor dicts.
    """
    return [{"label": algo.label, "value": algo.value, "column": algo.column} for algo in SimilarityAlgorithm]
