"""Sequence and Structure-Based Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_STRUCTURE
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "sequence-structure-similarity",
    "title": "Sequence and Structure-Based Similarity",
    "desc": "Experimental tool module. Features and capabilities are under active development.",
    "icon": ICON_TOOL_STRUCTURE,
    "order": 4,
    "libraries": ["foldseek"],
}
