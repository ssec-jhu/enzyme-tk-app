"""Substrate/Product Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system and
``get_similarity_algorithms`` — the single source of truth for the
similarity metrics available in this tool.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_REACTION
from enzyme_tk_app.app.tools import ToolDef

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
      This is the only key that creates a hard coupling to the enzymetk
      package.  If enzymetk renames a column, this value **must** be
      updated to match.

    Returns:
        List of algorithm descriptor dicts.
    """
    return [
        {
            "label": "Tanimoto",
            "value": "tanimoto",
            "column": "TanimotoSimilarity",
        },
        {
            "label": "Cosine",
            "value": "cosine",
            "column": "CosineSimilarity",
        },
        {
            "label": "Russell",
            "value": "russell",
            "column": "RusselSimilarity",
        },
    ]
