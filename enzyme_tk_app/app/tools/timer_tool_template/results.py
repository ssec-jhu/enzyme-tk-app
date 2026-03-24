"""Results layout for the Timer tool — **canonical example** for new tools.

Renders the generated random DataFrame as an interactive ``DataTable``
with sorting and filtering.

How results rendering works
---------------------------
The results page (``my_tasks_view_results.py``) calls two shared
helpers **before** invoking this function:

1. ``build_result_meta(job)`` — reads ``job.result["_meta"]`` and
   renders stat cards.  Tool authors populate ``_meta`` in
   ``compute.run()`` and get the stat-card strip for free.
2. ``build_result_input_params(job)`` — reads ``job.params`` and
   renders a label/value table of what the user submitted.  Keys
   listed in ``job.result["_params_exclude"]`` are suppressed.

This function (``results_layout``) is responsible **only** for the
tool-specific portion — in this case, a ``DataTable``.
If ``results.py`` is absent, the framework falls back to a raw-JSON
renderer (``default_results_layout``).

DataTable styling
-----------------
``dash_table.DataTable`` does **not** accept ``className`` — it uses
``style_*`` keyword arguments instead.  Use the shared constants from
``results_helpers.py`` for a consistent look:

- ``TABLE_STYLE_TABLE`` — outer wrapper (horizontal scroll).
- ``TABLE_STYLE_HEADER`` — column header cells.
- ``TABLE_STYLE_CELL`` — default cell styling.
- ``TABLE_STYLE_DATA_CONDITIONAL`` — alternating row stripes.
"""

from dash import dash_table, html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import (
    TABLE_STYLE_CELL,
    TABLE_STYLE_DATA_CONDITIONAL,
    TABLE_STYLE_HEADER,
    TABLE_STYLE_TABLE,
)


def results_layout(job: JobInfo) -> html.Div:
    """Render Timer job results: random DataFrame table.

    Timing metadata (requested, elapsed, rows generated) is rendered
    automatically by the shared ``build_result_meta`` helper via the
    ``_meta`` key in the compute result.  This function only handles
    the tool-specific table.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key.

    Returns:
        An ``html.Div`` with an interactive DataTable (or a "no data"
        message if the payload is missing).
    """
    result = job.result or {}

    # Extract the serialised DataFrame from the compute result.
    # Expected shape: {"columns": ["col1", ...], "data": [{...}, ...]}
    df_payload = result.get("dataframe")
    if df_payload and "columns" in df_payload and "data" in df_payload:
        columns = [{"name": col, "id": col} for col in df_payload["columns"]]
        table = dash_table.DataTable(
            columns=columns,
            data=df_payload["data"],
            # Enable client-side sorting and filtering — no callback needed.
            sort_action="native",
            filter_action="native",
            page_size=10,
            # Use the shared style constants for a consistent look.
            style_table=TABLE_STYLE_TABLE,
            style_header=TABLE_STYLE_HEADER,
            style_cell=TABLE_STYLE_CELL,
            style_data_conditional=TABLE_STYLE_DATA_CONDITIONAL,
        )
    else:
        table = html.P("No tabular data available.", style={"color": "var(--text-secondary)"})

    # create a simple wrapper div for anything tool-specific in the results page.
    # This renders under the shared meta cards and the input parameters table.
    # Those are generated automatically by the shared helpers.
    return html.Div(
        children=[
            table,
        ],
    )
