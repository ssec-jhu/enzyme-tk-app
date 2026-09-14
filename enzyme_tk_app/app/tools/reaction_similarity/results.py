"""Results layout for the Reaction Similarity tool.

Renders the top-N similar reactions as an interactive ``dag.AgGrid``
with sorting, filtering, and inline SVG reaction images.

The stat cards (databases searched, reactions scanned, results returned,
elapsed time) are rendered automatically from this tool's ``_stat_cards``
by the results-page header in ``my_tasks_view_results.py``.
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, shared_col_defs
from enzyme_tk_app.app.utils.columns import COL_RXN_SVG, COL_UNMAPPED_SMILES


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the Reaction Similarity grid.

    Prepends the tool-specific reaction SVG column, then appends all
    shared columns (similarity scores, metadata, molecular descriptors).

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        {
            "field": COL_RXN_SVG,
            "cellRenderer": "SvgRenderer",
            # Captions this reaction under its image in the compare lightbox.
            "cellRendererParams": {"smilesField": COL_UNMAPPED_SMILES},
            "width": 450,
            # autoHeight tells AG Grid to automatically expand the row height
            # to fit the cell's content. Without it, content that doesn't fit in
            # a single row gets clipped.
            "autoHeight": True,
            "filter": False,
            "sortable": False,
        },
    ] + shared_col_defs()


def results_layout(job: JobInfo) -> html.Div:
    """Render Reaction Similarity job results as an interactive AG Grid.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key with ``columns`` and ``data``.

    Returns:
        An ``html.Div`` wrapping the results grid.
    """
    result = job.result or {}
    df_payload = result.get("dataframe")

    if not df_payload or "columns" not in df_payload or "data" not in df_payload or not df_payload["data"]:
        return html.Div(
            html.P("No similar reactions found.", style={"color": "var(--text-secondary)"}),
        )

    results_table = build_ag_grid(_get_column_defs(), df_payload)
    return html.Div(children=[results_table])
