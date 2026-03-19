"""Auto-discovery hub for tool sub-packages.

Each tool lives in its own sub-package under ``tools/``.  Adding a new tool
requires no edits here — just create a sub-package with:

- ``__init__.py`` exporting ``TOOL_DEF: ToolDef``  (required)
- ``modal.py`` exporting ``modal() → dbc.Modal``   (optional)
- ``callbacks.py`` with ``@callback`` decorators   (optional, side-effect only)
"""

import importlib
import json
import logging
import pkgutil
from typing import Callable, NotRequired, TypedDict

from dash import html

# Module-level logger used by the discovery machinery to surface import errors
# without crashing the whole app (a broken tool should not prevent others from loading).
logger = logging.getLogger(__name__)


class ToolDef(TypedDict):
    """Schema for a single tool card entry.

    Attributes:
        slug: URL-safe identifier used in routes and component IDs.
            Must use hyphens, not underscores (e.g., ``"reaction-similarity"``).
        title: Human-readable name shown as the card heading
            (e.g., ``"Reaction Similarity"``).
        desc: Short description displayed beneath the title on the tool card.
            One or two sentences that explain what the tool does.
        icon: FontAwesome class string for the card icon.  Must be a free
            icon imported from ``enzyme_tk_app.app.components.icons``
            (e.g., ``ICON_SIMILARITY``).
        order: Display position in the tool card grid (lower numbers appear
            first).  Keeps the grid deterministic regardless of filesystem
            directory listing order.
        libraries: Optional list of Python package names shown as monospace
            badges on the card (e.g., ``["rdkit", "scipy"]``).  Omit if the
            tool has no noteworthy dependencies.
        max_duration: Timeout in seconds for the tool's computation.
            When this limit is reached the worker raises
            ``SoftTimeLimitExceeded``, which the task catches and records
            as ``TIMEOUT``.  A small hard-kill buffer (60 s) is added
            automatically so cleanup code can run.  Defaults to
            ``DEFAULT_MAX_DURATION`` (3600 s) in ``backend.config``.
    """

    slug: str
    title: str
    desc: str
    icon: str
    order: int
    libraries: NotRequired[list[str]]
    max_duration: NotRequired[int]


# ---------------------------------------------------------------------------
# Auto-discovery: scan sub-packages and collect TOOL_DEF / Modal / callbacks
# ---------------------------------------------------------------------------
# These module-level lists are populated once by ``_discover_tools()`` (called
# at the bottom of this file).  Every subsequent ``import`` of this package
# simply reuses the already-populated lists — Python only executes
# ``__init__.py`` once per interpreter session.
TOOLS: list[ToolDef] = []  # Accumulated ToolDef dicts, one per discovered tool
_modal_funcs: list = []  # Callables (Modal factories) that return dbc.Modal components
RESULTS_LAYOUTS: dict[str, Callable] = {}  # slug → ResultsLayout callable


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

        # --- Validate required keys before accepting the definition ---
        # ``ToolDef`` is a TypedDict, which is only enforced by static type
        # checkers — not at runtime.  This guard catches typos or missing
        # fields early (at import time) instead of letting a broken card
        # surface as a cryptic KeyError during layout rendering.
        # ``__required_keys__`` is a frozenset maintained by Python's
        # TypedDict machinery — it automatically reflects any additions or
        # removals of required fields in ``ToolDef``, so this check never
        # drifts out of sync with the schema.
        missing_keys = ToolDef.__required_keys__ - tool_def.keys()
        if missing_keys:
            logger.warning(
                "Tool package %s TOOL_DEF is missing required key(s): %s — skipping",
                full_name,
                ", ".join(sorted(missing_keys)),
            )
            continue

        TOOLS.append(tool_def)

        # --- Step 2: Import callbacks.py (optional) ---
        # Importing this module is done purely for its side-effect: the
        # ``@callback`` decorators at module level register themselves with
        # the Dash app instance.  We don't need to capture any return value.
        try:
            importlib.import_module(f"{full_name}.callbacks")
        except ModuleNotFoundError as exc:
            # Only silence the error when callbacks.py itself is absent.
            # If callbacks.py exists but imports a missing dependency, that
            # is a real bug and must not be silently swallowed.
            expected_module = f"{full_name}.callbacks"
            if exc.name != expected_module:
                logger.warning(
                    "callbacks module for %s failed: missing dependency %r",
                    full_name,
                    exc.name,
                    exc_info=True,
                )
        except Exception:
            logger.warning("Failed to import callbacks for %s", full_name, exc_info=True)

        # --- Step 3: Import modal.py (optional) ---
        # If present, ``modal.py`` must expose a ``modal()`` factory function
        # that returns a ``dbc.Modal`` component.  We store the *callable*
        # (not the component) so the modal is instantiated lazily when
        # ``tool_modals()`` is called during layout construction.
        try:
            modal_mod = importlib.import_module(f"{full_name}.modal")
            modal_fn = getattr(modal_mod, "modal", None)
            if modal_fn is not None:
                _modal_funcs.append(modal_fn)
        except ModuleNotFoundError as exc:
            # Only silence the error when modal.py itself is absent.
            # A missing dependency inside an existing modal.py is a real bug.
            expected_module = f"{full_name}.modal"
            if exc.name != expected_module:
                logger.warning(
                    "modal module for %s failed: missing dependency %r",
                    full_name,
                    exc.name,
                    exc_info=True,
                )
        except Exception:
            logger.warning("Failed to import modal for %s", full_name, exc_info=True)

        # --- Step 4: Import results.py (optional) ---
        # If present, ``results.py`` must expose a ``results_layout(job)``
        # callable that renders tool-specific output on the job results page.
        # Falls back to ``default_results_layout`` when not provided.
        try:
            results_mod = importlib.import_module(f"{full_name}.results")
            results_fn = getattr(results_mod, "results_layout", None)
            if results_fn is not None:
                RESULTS_LAYOUTS[tool_def["slug"]] = results_fn
        except ModuleNotFoundError as exc:
            expected_module = f"{full_name}.results"
            if exc.name != expected_module:
                logger.warning(
                    "results module for %s failed: missing dependency %r",
                    full_name,
                    exc.name,
                    exc_info=True,
                )
        except Exception:
            logger.warning("Failed to import results for %s", full_name, exc_info=True)

    # Sort tools by explicit ``order`` field so the card grid is deterministic
    # regardless of filesystem directory listing order.  Sorting here (rather
    # than once at module level) ensures the list is ordered whenever this
    # function is called — not just on the first import.
    TOOLS.sort(key=lambda t: t["order"])


# Run discovery exactly once at import time.  Because Python caches imported
# modules in ``sys.modules``, this function is never executed again — every
# subsequent ``from enzyme_tk_app.app.tools import TOOLS`` simply reuses the
# already-populated ``TOOLS`` list.
_discover_tools()


def tool_modals() -> html.Div:
    """Return all discovered tool modals bundled in a single container.

    Called by the app layout (e.g., ``home.py``) to inject all tool modals
    into the page at startup so their callbacks are available on first render.

    Returns:
        An ``html.Div`` containing every discovered tool modal (hidden by default).
    """
    # Each ``fn`` is a modal() factory collected during discovery.  Calling
    # them here produces the actual dbc.Modal components, which are then
    # wrapped in a single Div and inserted into the app layout.
    return html.Div([fn() for fn in _modal_funcs])


def default_results_layout(job) -> html.Div:
    """Fallback results renderer that shows raw JSON.

    Used when a tool does not provide a custom ``results.py`` module.

    Args:
        job: A completed ``JobInfo`` instance.

    Returns:
        An ``html.Div`` with a formatted JSON dump of the result dict.
    """
    result = job.result or {}
    return html.Div(
        children=[
            html.H5("Raw Results", style={"marginBottom": "1rem"}),
            html.Pre(
                json.dumps(result, indent=2, default=str),
                style={
                    "backgroundColor": "#F7FAFC",
                    "padding": "1rem",
                    "borderRadius": "0.5rem",
                    "fontSize": "0.85rem",
                    "maxHeight": "400px",
                    "overflowY": "auto",
                    "border": "1px solid var(--border-color)",
                },
            ),
        ],
    )


# Explicit public API for ``from enzyme_tk_app.app.tools import *``.
# Without ``__all__``, a wildcard import would expose every name defined or
# imported in this file (including ``importlib``, ``logging``, ``pkgutil``,
# and internal helpers like ``_discover_tools`` and ``_modal_funcs``).
# Listing names here restricts the wildcard to only these three symbols,
# keeping the public surface clean and preventing accidental coupling to
# implementation details.
__all__ = ["RESULTS_LAYOUTS", "TOOLS", "ToolDef", "default_results_layout", "tool_modals"]
