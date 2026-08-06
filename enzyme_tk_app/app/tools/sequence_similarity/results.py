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
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, numeric_col_def, sequence_col_def
from enzyme_tk_app.app.utils import columns as col


def _get_column_defs() -> list[dict]:
    """Return the curated column definitions for the Sequence Similarity grid.

    Covers the BLAST score columns followed by the protein metadata the
    reference databases commonly carry.  This is the *styled* layer — widths,
    decimal places, the sequence truncation class — not the full column list:
    ``results_layout`` appends a bare def for every other column the database
    happens to have.  Columns that do not exist in the result data are dropped
    by ``build_ag_grid``.

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        # ── BLAST hit identifier ─────────────────────────────────────
        {"field": col.COL_TARGET, "width": 130},
        # Which of the selected databases this hit came from.
        {"field": col.COL_DATABASE, "headerName": "Database", "width": 140},
        sequence_col_def(col.COL_SEQUENCE),
        # ── BLAST score columns (diamond output names) ───────────────
        # Percent identity from diamond (e.g. 100, 87.5) — 2 dp, not 4.
        numeric_col_def(col.COL_SEQ_IDENTITY, width=140, decimals=2),
        numeric_col_def(col.COL_BITSCORE, width=120, decimals=1),
        {"field": col.COL_EC_NUMBER, "width": 120},
        {"field": col.COL_RESIDUE_1INDEX, "width": 130},
        # Same residues 0-indexed — kept beside its 1-indexed twin rather than
        # left to the appended-metadata tail at the far right of the grid.
        {"field": col.COL_RESIDUE_0INDEX, "width": 130},
        {
            "field": col.COL_ACTIVE_SITE_COUNT,
            "headerName": "Active Site Count",
            "width": 150,
            "filter": "agNumberColumnFilter",
        },
        numeric_col_def(col.COL_EVALUE, width=120, exponential=True),
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
        # Fraction with values like 0.1666666666666666 — needs fixed decimals.
        numeric_col_def(col.COL_POLARITY, width=100, decimals=4),
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

    defs = _get_column_defs()

    # A sequence database is only required to have Entry, Sequence and EC number;
    # every other column is metadata this list cannot know about, and
    # ``build_ag_grid`` renders only fields that have a def.  Append a bare def
    # for anything the curated list above does not name — unstyled, but visible.
    known = {d["field"] for d in defs}
    defs += [{"field": c, "headerName": c} for c in df_payload["columns"] if c not in known]

    children.append(build_ag_grid(defs, df_payload))

    return html.Div(children=children)
