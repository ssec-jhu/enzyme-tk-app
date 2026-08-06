"""Sequence Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_SEQUENCE
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "sequence-similarity",
    "title": "Sequence Similarity",
    "desc": (
        "Protein sequence similarity search using DIAMOND BLASTp. Searches one or more "
        "reference databases, merged so hits are ranked globally."
    ),
    "icon": ICON_TOOL_SEQUENCE,
    "order": 3,
    "libraries": ["diamond-blastp"],
}
