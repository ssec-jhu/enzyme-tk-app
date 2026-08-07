"""Results layout for the Timer tool — **canonical example** for new tools.

Renders the generated random DataFrame as an interactive ``dag.AgGrid``
table — the pattern every real tool in the app uses.

How results rendering works
---------------------------
The results page (``my_tasks_view_results.py``) renders two things
**before** invoking this function:

1. The job-info header (``_build_job_info_header``) reads
   ``job.result["_stat_cards"]`` and merges those items into a single
   ``jobs-stats-row`` alongside Duration and Expires In.  Tool authors
   populate ``_stat_cards`` in ``compute.run()`` and get the stat-card
   strip for free.
2. ``build_result_input_params(job)`` — reads ``job.params`` and
   renders a label/value table of what the user submitted.  Keys
   listed in ``job.result["_params_exclude"]`` are suppressed.

This function (``results_layout``) is responsible **only** for the
tool-specific portion — in this case, the results grid.
If ``results.py`` is absent, the framework falls back to a raw-JSON
renderer (``default_results_layout``).

The AG Grid pattern
-------------------
Every results table is built the same way, in two steps:

1. ``_get_column_defs()`` returns one AG Grid ``columnDef`` per column,
   each field spelled out on its own line so this function alone shows
   what the table contains.  Numeric columns come from
   ``numeric_col_def()``, which always sets the number filter and takes
   an *opt-in* ``decimals`` — omit it for true integers, or a value like
   ``20`` renders as ``20.0000``.
2. ``build_ag_grid(column_defs, df_payload)`` drops any def whose field
   is absent from the payload, adds a hover tooltip per column, and
   returns an ``html.Div`` holding the shared CSV-export toolbar plus the
   themed ``dag.AgGrid``.

There are no style arguments here: the grid's look lives entirely in
``assets/09-ag-grid.css`` (the ``ag-theme-balham`` overrides).
"""

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, numeric_col_def
from enzyme_tk_app.app.utils import columns as col


def _get_column_defs() -> list[dict]:
    """Return the column definitions for the Timer results grid.

    Each column's treatment is picked from the value range
    ``compute._generate_random_dataframe`` actually produces — not by habit.

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        # ── Identity ─────────────────────────────────────────────────
        {"field": col.COL_SAMPLE_ID, "headerName": "Sample ID", "width": 140},
        # ── Assay measurements ───────────────────────────────────────
        # round(uniform(0.5, 150.0), 2) — a 2 dp score.
        numeric_col_def(col.COL_ACTIVITY_SCORE, "Activity Score", width=140, decimals=2),
        # round(uniform(35.0, 85.0), 1) — a 1 dp score.
        numeric_col_def(col.COL_STABILITY_SCORE, "Stability Score", width=140, decimals=1),
        # randint(20, 80) — a true integer, so no decimals: formatting it
        # would render 20 as "20.0000".
        numeric_col_def(col.COL_TEMPERATURE_C, "Temperature (C)", width=140),
        # round(uniform(5.0, 98.0), 1) — a percentage at 1 dp.
        numeric_col_def(col.COL_YIELD_PCT, "Yield (%)", width=120, decimals=1),
    ]


def results_layout(job: JobInfo) -> html.Div:
    """Render Timer job results: random DataFrame table.

    Timing metadata (requested, elapsed, rows generated) is rendered
    automatically by the results-page header from the ``_stat_cards`` key in
    the compute result.  This function only handles the tool-specific table.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key.

    Returns:
        An ``html.Div`` with the results grid (or a "no data" message if
        the payload is missing or malformed).
    """
    result = job.result or {}

    # Extract the serialised DataFrame from the compute result.
    # Expected shape: {"columns": ["col1", ...], "data": [{...}, ...]}
    df_payload = result.get("dataframe")
    # ``build_ag_grid`` raises ValueError on a malformed payload, so check the
    # shape here and show a message instead of failing the whole page.
    if df_payload and "columns" in df_payload and "data" in df_payload:
        # No ``shared_col_defs()``: this demo payload carries none of those
        # fields, and ``build_ag_grid`` drops every def whose field is absent.
        table = build_ag_grid(_get_column_defs(), df_payload)
    else:
        table = html.P("No tabular data available.", style={"color": "var(--text-secondary)"})

    # create a simple wrapper div for anything tool-specific in the results page.
    # This renders under the header's stat cards and the input parameters table,
    # both of which the results page generates automatically.
    return html.Div(
        children=[
            table,
        ],
    )
