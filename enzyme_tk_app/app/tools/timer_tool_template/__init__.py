"""Timer tool definition — **canonical example** for creating new tools.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system.
A simple testing/demo tool that sleeps for a user-specified number of
seconds.  Use this tool as a reference when building new tools.

How tool discovery works
------------------------
The ``tools/__init__.py`` module scans every sub-package under
``enzyme_tk_app/app/tools/``.  If it finds a ``TOOL_DEF`` dict here,
the tool is registered automatically — no central file to edit.

File roles
----------
- ``__init__.py``   → ``TOOL_DEF`` (this file, required)
- ``modal.py``      → ``modal()`` factory for the launch dialog
- ``callbacks.py``  → Dash ``@callback`` decorators (side-effect import)
- ``compute.py``    → ``run(params) → dict`` executed by the Celery worker
- ``results.py``    → ``results_layout(job) → html.Div`` for custom results
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_TIMER
from enzyme_tk_app.app.tools import ToolDef

# TOOL_DEF is the single source of truth for slug, title, icon, and order.
# Every other file in this package imports TOOL_DEF and derives IDs from it.
#
# Folder-name invariant:
#   The folder name MUST equal ``slug.replace("-", "_")``.
#   e.g. slug "timer-tool-template" → folder "timer_tool_template".
#   The task dispatcher in tasks.py converts the slug back to a folder name
#   using this convention.  If you change the slug, rename the folder.
TOOL_DEF: ToolDef = {
    # URL-safe identifier — lowercase letters, numbers, and hyphens only.
    "slug": "timer-tool-template",
    # Human-readable name shown on the tool card and modal header.
    "title": "Timer Tool Template",
    # Short description for the tool card (1–2 sentences).
    "desc": (
        "A demo tool that runs a background task for a user-specified "
        "number of seconds. Useful for testing the job scheduling backend."
    ),
    # FontAwesome icon constant imported from icons.py.
    "icon": ICON_TOOL_TIMER,
    # Display position in the tool grid (lower = earlier).
    "order": 6,
    # Optional: timeout in seconds.  The worker will raise
    # SoftTimeLimitExceeded when this limit is hit; the task records it
    # as TIMEOUT.  Defaults to 3600 s if omitted.
    "max_duration": 600,
    # Optional: "libraries" — list of package names shown as badges on
    # the card.  Omitted here because the timer tool has no noteworthy
    # dependencies. Example: ``"libraries": ["rdkit", "scipy"]``.
}
