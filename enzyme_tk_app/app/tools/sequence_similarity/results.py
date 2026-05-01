"""Results layout for the Sequence Similarity tool.

Renders the BLAST search results as an interactive ``dag.AgGrid``
table.  When catalytic residue prediction was requested, a collapsible
accordion section with the prediction output is shown above the table.

The stat cards (database, sequences scanned, results returned, elapsed
time) are rendered automatically by the shared header in
``my_tasks_view_results.py``.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid
from enzyme_tk_app.app.utils import columns as col


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the Sequence Similarity grid.

    Covers BLAST score columns followed by all protein metadata from
    the database CSV.  Only columns that actually exist in the result
    data will be rendered (filtering is done in ``build_ag_grid``).

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        # ── BLAST hit identifier ─────────────────────────────────────
        {"field": col.COL_TARGET, "width": 130},
        {
            "field": col.COL_SEQUENCE,
            "width": 300,
            # Long sequences are truncated in the cell; full text on hover.
            "cellStyle": {
                "fontSize": "0.8rem",
                "whiteSpace": "nowrap",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
        },
        # ── BLAST score columns (diamond output names) ───────────────
        {"field": col.COL_SEQ_IDENTITY, "width": 140, "filter": "agNumberColumnFilter"},
        {"field": col.COL_BITSCORE, "width": 120, "filter": "agNumberColumnFilter"},
        {"field": col.COL_EC_NUMBER, "width": 120},
        {"field": col.COL_RESIDUE_1INDEX, "width": 130},
        {
            "field": col.COL_ACTIVE_SITE_COUNT,
            "headerName": "Active Site Count",
            "width": 150,
            "filter": "agNumberColumnFilter",
        },
        {"field": col.COL_EVALUE, "width": 120, "filter": "agNumberColumnFilter"},
        {
            "field": col.COL_ALIGNMENT_LENGTH,
            "headerName": "Alignment Length",
            "width": 150,
            "filter": "agNumberColumnFilter",
        },
        {"field": col.COL_MISMATCH, "width": 115, "filter": "agNumberColumnFilter"},
        {"field": col.COL_GAPOPEN, "width": 110, "filter": "agNumberColumnFilter"},
        {"field": col.COL_QUERY_START, "width": 110, "filter": "agNumberColumnFilter"},
        {"field": col.COL_QUERY_END, "width": 110, "filter": "agNumberColumnFilter"},
        {"field": col.COL_TARGET_START, "width": 110, "filter": "agNumberColumnFilter"},
        {"field": col.COL_TARGET_END, "width": 110, "filter": "agNumberColumnFilter"},
        # ── Protein metadata from database CSV ───────────────────────
        {"field": col.COL_POLARITY, "width": 100, "filter": "agNumberColumnFilter"},
        {"field": col.COL_TEMPERATURE, "width": 110, "filter": "agNumberColumnFilter"},
        {"field": col.COL_LENGTH, "width": 90, "filter": "agNumberColumnFilter"},
        {"field": col.COL_MASS, "width": 110, "filter": "agNumberColumnFilter"},
        # ── Cofactor (placeholder — column coming in future data update) ─
        {"field": col.COL_COFACTOR, "width": 120},
    ]


def results_layout(job: JobInfo) -> html.Div:
    """Render Sequence Similarity job results.

    If catalytic residue prediction was requested, a collapsible
    accordion section appears above the results table.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key with ``columns`` and ``data``, and
            optionally a ``catalytic_prediction`` string.

    Returns:
        An ``html.Div`` wrapping the optional prediction section and
        the results grid.
    """
    result = job.result or {}
    df_payload = result.get("dataframe")

    children: list = []

    # ------------------------------------------------------------------
    # Catalytic residue prediction (collapsible accordion)
    # ------------------------------------------------------------------
    catalytic_prediction = result.get("catalytic_prediction")
    if catalytic_prediction is not None:
        children.append(
            dbc.Accordion(
                children=[
                    dbc.AccordionItem(
                        title="Catalytic Residue Predictions",
                        children=[
                            html.P(catalytic_prediction),
                        ],
                    ),
                ],
                start_collapsed=False,
                className="mb-3",
            )
        )

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------
    if not df_payload or "columns" not in df_payload or "data" not in df_payload or not df_payload["data"]:
        message = result.get("no_results_message", "No similar sequences found.")
        children.append(
            html.P(message, style={"color": "var(--text-secondary)"}),
        )
        return html.Div(children=children)

    grid = build_ag_grid(_get_column_defs(), df_payload)
    children.append(grid)

    return html.Div(children=children)
