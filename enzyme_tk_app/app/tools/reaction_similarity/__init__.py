"""Reaction Similarity tool definition.

Exports ``TOOL_DEF`` consumed by the tools auto-discovery system and
``get_similarity_algorithms`` — the single source of truth for available
similarity metrics.
"""

from enzyme_tk_app.app.components.icons import ICON_TOOL_REACTION
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "reaction-similarity",
    "title": "Reaction Similarity",
    "desc": (
        "Reaction similarity search using RDKit structural reaction fingerprints "
        "with Tanimoto, Russell, and Cosine scoring."
    ),
    "icon": ICON_TOOL_REACTION,
    "order": 1,
    "libraries": ["rdkit"],
    "max_duration": 180,
}


def get_similarity_algorithms() -> list[dict]:
    """Return the list of available reaction-similarity algorithms.

    Each entry is a dict with:
    - ``label``: human-readable name for dropdown display (decoupled
      from enzymetk — can be any string).
    - ``value``: short key used in params / API calls (decoupled from
      enzymetk — can be any string).
    - ``column``: the **exact** DataFrame column name produced by
      ``enzymetk.similarity_reaction_step.ReactionDist.execute()``.
      This is the only key that creates a hard coupling to the enzymetk
      package.  If enzymetk renames a column, this value **must** be
      updated to match — otherwise ``_validate_result_columns()`` in
      ``compute.py`` will raise a ``ValueError`` at runtime and the
      integration test ``test_each_algorithm_column_present_in_
      reaction_dist_output`` will fail in CI.

    .. note::
        Will be replaced by an enzymetk API call (e.g.
        ``similarity_reaction_step.get_available_metrics()``) when that
        function becomes available in a future release.

    Returns:
        List of algorithm descriptor dicts.
    """
    return [
        {
            "label": "Tanimoto",
            "value": "tanimoto",
            "column": "TanimotoSimilarity",  # must match the column name in ReactionDist output
        },
        {
            "label": "Cosine",
            "value": "cosine",
            "column": "CosineSimilarity",  # must match the column name in ReactionDist output
        },
        {
            "label": "Russell",
            "value": "russell",
            "column": "RusselSimilarity",  # must match the column name in ReactionDist output
        },
    ]
