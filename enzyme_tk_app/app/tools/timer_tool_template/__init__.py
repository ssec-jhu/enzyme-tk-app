"""Timer tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
A simple testing/demo tool that sleeps for a user-specified number of seconds.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_TIMER
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "timer-tool-template",
    "title": "Timer Tool Template",
    "desc": (
        "A demo tool that runs a background task for a user-specified "
        "number of seconds. Useful for testing the job scheduling backend."
    ),
    "icon": ICON_TOOL_TIMER,
    "order": 6,
    "max_duration": 600,
}
