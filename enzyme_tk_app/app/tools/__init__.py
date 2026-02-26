"""Auto-discovery hub for tool packages.

Each tool lives in its own sub-package under ``tools/`` and is discovered
automatically at import time.  No central registry file needs to be edited.

Adding a new tool
-----------------
1. Create a new sub-package folder, e.g. ``tools/my_new_tool/``.
2. In ``__init__.py`` export a ``TOOL_DEF`` dict (type ``ToolDef``) with the
   tool's metadata (slug, title, desc, icon, and optionally libraries).
3. Optionally add ``modal.py`` exporting a ``Modal()`` function that returns
   a ``dbc.Modal`` component.
4. Optionally add ``callbacks.py`` with ``@callback`` decorators — they
   register automatically when the module is imported.

Convention summary
~~~~~~~~~~~~~~~~~~
| File           | Required? | Must export               | Purpose                               |
|----------------|-----------|---------------------------|---------------------------------------|
| ``__init__.py``| Yes       | ``TOOL_DEF: ToolDef``     | Metadata (slug, title, desc, icon)    |
| ``modal.py``   | No        | ``Modal() → dbc.Modal``   | Input form for the tool               |
| ``callbacks.py``| No       | *(side-effect)*           | ``@callback`` decorators auto-register|
"""

import importlib
import logging
import pkgutil
from typing import NotRequired, TypedDict

from dash import html

logger = logging.getLogger(__name__)


class ToolDef(TypedDict):
    """Schema for a single tool card entry."""

    slug: str  # URL-safe identifier (e.g., "reaction-similarity")
    title: str
    desc: str
    icon: str  # FontAwesome class string from icons.py
    libraries: NotRequired[list[str]]  # package names shown as monospace badges


# ---------------------------------------------------------------------------
# Auto-discovery: scan sub-packages and collect TOOL_DEF / Modal / callbacks
# ---------------------------------------------------------------------------
TOOLS: list[ToolDef] = []
_modal_funcs: list = []  # list of callables returning dbc.Modal


def _discover_tools():
    """Scan sub-packages and populate ``TOOLS`` and ``_modal_funcs``."""
    package_path = __path__  # type: ignore[name-defined]
    package_name = __name__

    for importer, modname, ispkg in pkgutil.iter_modules(package_path):
        if not ispkg:
            continue  # only look at sub-packages (folders with __init__.py)

        full_name = f"{package_name}.{modname}"

        # 1. Import the sub-package __init__ to get TOOL_DEF
        try:
            tool_pkg = importlib.import_module(full_name)
        except Exception:
            logger.warning("Failed to import tool package %s", full_name, exc_info=True)
            continue

        tool_def = getattr(tool_pkg, "TOOL_DEF", None)
        if tool_def is None:
            logger.warning("Tool package %s has no TOOL_DEF — skipping", full_name)
            continue

        TOOLS.append(tool_def)

        # 2. Try to import callbacks (side-effect registers @callback decorators)
        try:
            importlib.import_module(f"{full_name}.callbacks")
        except ModuleNotFoundError:
            pass  # no callbacks module — that's fine
        except Exception:
            logger.warning("Failed to import callbacks for %s", full_name, exc_info=True)

        # 3. Try to import modal layout
        try:
            modal_mod = importlib.import_module(f"{full_name}.modal")
            modal_fn = getattr(modal_mod, "Modal", None)
            if modal_fn is not None:
                _modal_funcs.append(modal_fn)
        except ModuleNotFoundError:
            pass  # no modal module — that's fine
        except Exception:
            logger.warning("Failed to import modal for %s", full_name, exc_info=True)


_discover_tools()


def ToolModals():
    """Return all discovered tool modals bundled in a single container.

    Returns:
        An ``html.Div`` containing every discovered tool modal (hidden by default).
    """
    return html.Div([fn() for fn in _modal_funcs])


__all__ = ["TOOLS", "ToolDef", "ToolModals"]
