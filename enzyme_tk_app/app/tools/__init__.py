"""Auto-discovery hub for tool sub-packages.

Each tool lives in its own sub-package under ``tools/``.  Adding a new tool
requires no edits here — just create a sub-package with:

- ``__init__.py`` exporting ``TOOL_DEF: ToolDef``  (required)
- ``modal.py`` exporting ``Modal() → dbc.Modal``   (optional)
- ``callbacks.py`` with ``@callback`` decorators   (optional, side-effect only)
"""

import importlib
import logging
import pkgutil
from typing import NotRequired, TypedDict

from dash import html

# Module-level logger used by the discovery machinery to surface import errors
# without crashing the whole app (a broken tool should not prevent others from loading).
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
# These module-level lists are populated once by ``_discover_tools()`` (called
# at the bottom of this file).  Every subsequent ``import`` of this package
# simply reuses the already-populated lists — Python only executes
# ``__init__.py`` once per interpreter session.
TOOLS: list[ToolDef] = []  # Accumulated ToolDef dicts, one per discovered tool
_modal_funcs: list = []  # Callables (Modal factories) that return dbc.Modal components


def _discover_tools() -> None:
    """Scan sub-packages and populate ``TOOLS`` and ``_modal_funcs``."""
    for _importer, modname, ispkg in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if not ispkg:
            # Skip loose .py files — tools must be sub-packages so they can
            # house multiple files (modal.py, callbacks.py) alongside their
            # ``__init__.py`` definition.
            continue

        full_name = f"{__name__}.{modname}"

        # --- Step 1: Import the sub-package __init__.py to get TOOL_DEF ---
        # This is the only *required* export.  It supplies the metadata that
        # the home page uses to render the tool card (title, description,
        # icon, etc.).
        try:
            tool_pkg = importlib.import_module(full_name)
        except Exception:
            logger.warning("Failed to import tool package %s", full_name, exc_info=True)
            continue

        tool_def = getattr(tool_pkg, "TOOL_DEF", None)
        if tool_def is None:
            # Sub-package exists but does not define TOOL_DEF → probably not
            # a tool (could be a shared utility folder).  Skip silently.
            logger.warning("Tool package %s has no TOOL_DEF — skipping", full_name)
            continue

        TOOLS.append(tool_def)

        # --- Step 2: Import callbacks.py (optional) ---
        # Importing this module is done purely for its side-effect: the
        # ``@callback`` decorators at module level register themselves with
        # the Dash app instance.  We don't need to capture any return value.
        try:
            importlib.import_module(f"{full_name}.callbacks")
        except ModuleNotFoundError:
            pass  # No callbacks module — tool has no interactivity yet
        except Exception:
            logger.warning("Failed to import callbacks for %s", full_name, exc_info=True)

        # --- Step 3: Import modal.py (optional) ---
        # If present, ``modal.py`` must expose a ``Modal()`` factory function
        # that returns a ``dbc.Modal`` component.  We store the *callable*
        # (not the component) so the modal is instantiated lazily when
        # ``ToolModals()`` is called during layout construction.
        try:
            modal_mod = importlib.import_module(f"{full_name}.modal")
            modal_fn = getattr(modal_mod, "Modal", None)
            if modal_fn is not None:
                _modal_funcs.append(modal_fn)
        except ModuleNotFoundError:
            pass  # No modal module — tool card will have no "Launch →" dialog
        except Exception:
            logger.warning("Failed to import modal for %s", full_name, exc_info=True)


# Run discovery exactly once at import time.  Because Python caches imported
# modules in ``sys.modules``, this function is never executed again — every
# subsequent ``from enzyme_tk_app.app.tools import TOOLS`` simply reuses the
# already-populated ``TOOLS`` list.
_discover_tools()


def ToolModals() -> html.Div:
    """Return all discovered tool modals bundled in a single container.

    Called by the app layout (e.g., ``home.py``) to inject all tool modals
    into the page at startup so their callbacks are available on first render.

    Returns:
        An ``html.Div`` containing every discovered tool modal (hidden by default).
    """
    # Each ``fn`` is a Modal() factory collected during discovery.  Calling
    # them here produces the actual dbc.Modal components, which are then
    # wrapped in a single Div and inserted into the app layout.
    return html.Div([fn() for fn in _modal_funcs])


# Explicit public API for ``from enzyme_tk_app.app.tools import *``.
# Without ``__all__``, a wildcard import would expose every name defined or
# imported in this file (including ``importlib``, ``logging``, ``pkgutil``,
# and internal helpers like ``_discover_tools`` and ``_modal_funcs``).
# Listing names here restricts the wildcard to only these three symbols,
# keeping the public surface clean and preventing accidental coupling to
# implementation details.
__all__ = ["TOOLS", "ToolDef", "ToolModals"]
