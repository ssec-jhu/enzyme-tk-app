"""TBD Tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_TBD
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "tbd-tool",
    "title": "TBD Tool",
    "desc": "Experimental tool module. Features and capabilities are under active development.",
    "icon": ICON_TOOL_TBD,
    "order": 5,
    "libraries": ["foldseek"],
}
