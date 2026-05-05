"""Sequence and Structure-Based Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_STRUCTURE
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "sequence-structure-similarity",
    "title": "Sequence and Structure-Based Similarity",
    "desc": (
        "FoldSeek-powered similarity search using protein sequences (ProstT5) "
        "or structures (CIF/PDB). Searches across multiple databases including PDB "
        "and AlphaFold/Swiss-Prot."
    ),
    "icon": ICON_TOOL_STRUCTURE,
    "order": 4,
    "libraries": ["foldseek","prostt5"],
    "max_duration": 3600,
}
