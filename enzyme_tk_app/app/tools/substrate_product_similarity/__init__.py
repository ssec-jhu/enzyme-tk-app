"""Substrate/Product Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
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
}
