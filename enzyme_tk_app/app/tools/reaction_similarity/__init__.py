"""Reaction Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.

The similarity algorithms (Tanimoto, Cosine, Russell) are shared with
the Substrate/Product Similarity tool.  Import ``SimilarityAlgorithm``
and ``get_similarity_algorithms`` from
:mod:`enzyme_tk_app.app.tools.substrate_product_similarity` — that
module is the single source of truth for algorithm definitions.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_REACTION
from enzyme_tk_app.app.tools import ToolDef

# Re-export so existing consumers can keep importing from this package.
from enzyme_tk_app.app.tools.substrate_product_similarity import (  # noqa: F401
    SimilarityAlgorithm,
    get_similarity_algorithms,
)

TOOL_DEF: ToolDef = {
    "slug": "reaction-similarity",
    "title": "Reaction Similarity",
    "desc": (
        "Reaction similarity search using RDKit structural reaction fingerprints "
        "with Tanimoto, Russell, and Cosine scoring."
    ),
    "icon": ICON_TOOL_REACTION,
    "order": 1,
    "libraries": ["rdkit"],
    "max_duration": 180,
}
