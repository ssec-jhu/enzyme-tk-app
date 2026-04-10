"""Results layout for the Substrate/Product Similarity tool.

Renders the top-N similar molecules as an interactive ``dag.AgGrid``
with sorting, filtering, and inline SVG molecule images.

The stat cards (databases searched, molecules compared, etc.) are
rendered automatically by the shared ``build_result_stat_cards`` helper
in ``my_tasks_view_results.py``.
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, shared_col_defs


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the Substrate/Product Similarity grid.

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        {
            # The "molecule_svg" column displays an inline SVG image of the molecule.
            "field": "molecule_svg",
            "cellRenderer": "SvgRenderer",
            "width": 200,
            # autoHeight tells AG Grid to automatically expand the row height
            # to fit the cell's content. Without it, content that doesn't fit in
            # a single row gets clipped.
            "autoHeight": True,
            "filter": False,
            "sortable": False,
        },
        {
            # The "molecule_smiles" column shows the SMILES string for the molecule.
            "field": "molecule_smiles",
            "wrapText": True,
            "width": 200,
        },
        {
            # The "molecule_index" column shows the index of the molecule in the dataset.
            "field": "molecule_index",
            "width": 80,
        },
    ] + shared_col_defs()


def results_layout(job: JobInfo) -> html.Div:
    """Render Substrate/Product Similarity job results as an interactive AG Grid.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key with ``columns`` and ``data``.

    Returns:
        An ``html.Div`` wrapping the results grid.
    """
    result = job.result or {}
    # The result dict should contain a "dataframe" key with "columns" and "data",
    # but we check for its presence and validity before trying to render the grid.
    df_payload = result.get("dataframe", {})

    if not all(key in df_payload for key in ("columns", "data")) or not df_payload.get("data"):
        return html.Div(
            # If the dataframe payload is missing, malformed, or empty,
            # show a user-friendly message instead of an empty grid.
            html.P("No similar molecules found.", style={"color": "var(--text-secondary)"}),
        )

    # If we have a valid dataframe with data, render it as an AG Grid using our helper function.
    grid = build_ag_grid(_get_column_defs(), df_payload)
    return html.Div(children=[grid])
