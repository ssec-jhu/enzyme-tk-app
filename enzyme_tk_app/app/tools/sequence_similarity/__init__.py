"""Sequence Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_SEQUENCE
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "sequence-similarity",
    "title": "Sequence Similarity",
    "desc": ("High-performance pairwise and multiple sequence alignment using Smith-Waterman and BLAST algorithms."),
    "icon": ICON_TOOL_SEQUENCE,
    "libraries": ["diamand-blastp"],
}
