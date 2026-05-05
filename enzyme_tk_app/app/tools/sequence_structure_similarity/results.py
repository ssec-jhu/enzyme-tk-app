"""Results layout for the Sequence & Structure-Based Similarity tool.

Renders the FoldSeek search results as an interactive ``dag.AgGrid``
table.  Columns cover the standard FoldSeek output fields (alignment
identity, bit score, e-value, etc.) plus the ``database`` column that
identifies which database each hit came from.

The stat cards (mode, databases, hits found, elapsed time) are rendered
automatically by the shared header in ``my_tasks_view_results.py``.
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the FoldSeek results grid.

    Covers all standard FoldSeek easy-search output columns plus the
    ``database`` column appended by the compute function.  Only columns
    that actually exist in the result data will be rendered (filtering
    is done in ``build_ag_grid``).

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        # ── Hit identifiers ──────────────────────────────────────────
        {"field": "query", "headerName": "Query", "width": 120},
        {"field": "target", "headerName": "Target", "width": 180},
        {"field": "database", "headerName": "Database", "width": 140},
        # ── Alignment scores ─────────────────────────────────────────
        {
            "field": "fident",
            "headerName": "Frac. Identity",
            "width": 140,
            "filter": "agNumberColumnFilter",
            "valueFormatter": {"function": "params.value != null ? params.value.toFixed(4) : ''"},
        },
        {
            "field": "bits",
            "headerName": "Bit Score",
            "width": 120,
            "filter": "agNumberColumnFilter",
            "valueFormatter": {"function": "params.value != null ? params.value.toFixed(1) : ''"},
        },
        {
            "field": "evalue",
            "headerName": "E-value",
            "width": 120,
            "filter": "agNumberColumnFilter",
            "valueFormatter": {"function": "params.value != null ? params.value.toExponential(2) : ''"},
        },
        # ── Alignment details ────────────────────────────────────────
        {
            "field": "alnlen",
            "headerName": "Alignment Length",
            "width": 150,
            "filter": "agNumberColumnFilter",
        },
        {"field": "mismatch", "headerName": "Mismatches", "width": 120, "filter": "agNumberColumnFilter"},
        {"field": "gapopen", "headerName": "Gap Opens", "width": 120, "filter": "agNumberColumnFilter"},
        # ── Position ranges ──────────────────────────────────────────
        {"field": "qstart", "headerName": "Query Start", "width": 110, "filter": "agNumberColumnFilter"},
        {"field": "qend", "headerName": "Query End", "width": 110, "filter": "agNumberColumnFilter"},
        {"field": "tstart", "headerName": "Target Start", "width": 110, "filter": "agNumberColumnFilter"},
        {"field": "tend", "headerName": "Target End", "width": 110, "filter": "agNumberColumnFilter"},
    ]


def results_layout(job: JobInfo) -> html.Div:
    """Render Sequence & Structure-Based Similarity job results.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key with ``columns`` and ``data``.

    Returns:
        An ``html.Div`` wrapping the results grid or an informational
        message when no hits were found.
    """
    result = job.result or {}

    # Extract the dataframe payload from the result dict. It should have
    # 'columns' and 'data' keys. If not present or empty, we'll show a
    # "no results" message instead of the grid.
    df_payload = result.get("dataframe")

    # Initialize the list of children components for the results layout.
    children: list = []

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------
    # If the dataframe payload is missing or contains no data, display a
    # message instead of the grid. The message can be customized via the
    # 'no_results_message' key in the result dict, or defaults to a generic
    # "No similar sequences or structures found." notice.
    if not df_payload or not df_payload.get("data"):
        message = result.get("no_results_message", "No similar sequences or structures found.")

        # Append the message as a styled paragraph to the children list, then return the layout.
        children.append(
            html.P(message, style={"color": "var(--text-secondary)"}),
        )
        return html.Div(children=children)

    # If we have valid data, build the AG Grid with the appropriate column definitions.
    grid = build_ag_grid(_get_column_defs(), df_payload)
    children.append(grid)

    # return the results layout as a Div containing either the grid or the no-results message.
    return html.Div(children=children)
