"""Registry of available tools.

To add a new tool card to the home page, append an entry to ``TOOLS``.
No frontend code needs to be changed.

Each entry is a ``ToolDef`` with the following fields:

- ``slug``      (required) — URL-safe identifier used in component IDs.
- ``title``     (required) — Display name shown in the card heading.
- ``desc``      (required) — Short description of what the tool does.
- ``icon``      (required) — FontAwesome icon class from ``icons.py``.
- ``libraries`` (optional) — List of Python package names shown as badges.
"""

from typing import NotRequired, TypedDict

from enzyme_tk_app.app.components.icons import (
    ICON_TOOL_REACTION,
    ICON_TOOL_SEQUENCE,
    ICON_TOOL_TBD,
)


class ToolDef(TypedDict):
    """Schema for a single tool card entry."""

    slug: str  # URL-safe identifier (e.g., "reaction-similarity")
    title: str
    desc: str
    icon: str  # FontAwesome class string from icons.py
    libraries: NotRequired[list[str]]  # package names shown as monospace badges


# ---------------------------------------------------------------------------
# ADD NEW TOOLS HERE
# ---------------------------------------------------------------------------
TOOLS: list[ToolDef] = [
    {
        "slug": "reaction-similarity",
        "title": "Reaction Similarity",
        "desc": (
            "Reaction similarity search using RDKit structural reaction fingerprints "
            "with Tanimoto, Russell, and Cosine scoring."
        ),
        "icon": ICON_TOOL_REACTION,
        "libraries": ["rdkit"],
    },
    {
        "slug": "substrate-product-similarity",
        "title": "Substrate/Product Similarity",
        "desc": (
            "Molecular similarity search using Morgan circular fingerprints with Tanimoto, Russell, and Cosine scoring."
        ),
        "icon": ICON_TOOL_REACTION,
        "libraries": ["rdkit"],
    },
    {
        "slug": "sequence-similarity",
        "title": "Sequence Similarity",
        "desc": (
            "High-performance pairwise and multiple sequence alignment using Smith-Waterman and BLAST algorithms."
        ),
        "icon": ICON_TOOL_SEQUENCE,
        "libraries": ["diamand-blastp"],
    },
    {
        "slug": "sequence-structure-similarity",
        "title": "Sequence and Structure-Based Similarity",
        "desc": "Experimental tool module. Features and capabilities are under active development.",
        "icon": ICON_TOOL_TBD,
        "libraries": ["foldseek"],
    },
    {
        "slug": "tbd-tool-2",
        "title": "TBD Tool 2",
        "desc": "Experimental tool module. Features and capabilities are under active development.",
        "icon": ICON_TOOL_TBD,
        "libraries": ["foldseek"],
    },
]
