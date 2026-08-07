"""Shared UI helpers for tool results pages.

Provides :func:`build_status_badge` and :func:`build_stat_card`, the small
renderers shared by the My Tasks table and the task-results page header.
A job's ``_stat_cards`` are rendered by that header itself
(``my_tasks_view_results._build_job_info_header``), which merges them into
one ``jobs-stats-row`` alongside Duration and Expires In.

Also provides :func:`build_result_input_params` which auto-renders the job's
input parameters in a label → value table.

Provides :func:`shared_col_defs` and :func:`build_ag_grid` for tools
that render results via ``dag.AgGrid`` — every results table in the app.
Tool-specific columns (e.g. SVG previews) are prepended by each tool; the
shared columns cover similarity scores, reaction metadata, molecular
descriptors, etc.

``build_ag_grid`` also renders the shared CSV-download toolbar above the
grid, so every tool's results table gets the same export control without
any per-tool code.

Usage (AG Grid)::

    from enzyme_tk_app.app.components.results_helpers import (
        build_ag_grid,
        shared_col_defs,
    )

    column_defs = [my_tool_specific_col] + shared_col_defs()
    results_table = build_ag_grid(column_defs, df_payload)
"""

from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.components.icons import (
    ICON_RESULTS_DOWNLOAD,
    ICON_STATUS_FAILURE,
    ICON_STATUS_PENDING,
    ICON_STATUS_REVOKED,
    ICON_STATUS_STARTED,
    ICON_STATUS_SUCCESS,
    ICON_STATUS_TIMEOUT,
)
from enzyme_tk_app.app.utils import columns as col

# ---------------------------------------------------------------------------
# Results grid & CSV export identifiers
# ---------------------------------------------------------------------------
# Only one results table renders per page — ``my_tasks_view_results`` calls a
# single tool's ``results_layout`` — so these ids can be static.  Give
# ``build_ag_grid`` an id argument and move the export callback to MATCH if a
# page ever needs two grids.

GRID_ID = "id-grid-results"
"""Id of the results AG Grid built by :func:`build_ag_grid`."""

JOB_ID_SPAN_ID = "id-span-job-id"
"""Id of the task-id span in the results page header; its ``title`` is the bare job id."""

_BTN_DOWNLOAD_ID = "id-btn-results-download"
_RADIO_SCOPE_ID = "id-radio-results-download-scope"

# Export scopes offered by the toolbar radios.  The values double as the
# filename suffix, so they read the same as the labels the user picked.
SCOPE_FILTERED = "filtered"
SCOPE_ALL = "unfiltered"

# Job ids are 36-char UUIDs; the My Tasks table already shows the first 6, so
# the download matches what the user sees there.
_JOB_ID_CHARS = 6

# ---------------------------------------------------------------------------
# Shared status → icon mapping
# ---------------------------------------------------------------------------

STATUS_ICONS: dict[JobStatus, str] = {
    JobStatus.PENDING: ICON_STATUS_PENDING,
    JobStatus.STARTED: ICON_STATUS_STARTED,
    JobStatus.SUCCESS: ICON_STATUS_SUCCESS,
    JobStatus.FAILURE: ICON_STATUS_FAILURE,
    JobStatus.REVOKED: ICON_STATUS_REVOKED,
    JobStatus.TIMEOUT: ICON_STATUS_TIMEOUT,
}

STYLE_RESULTS_TOOLBAR: dict = {
    "display": "flex",
    "alignItems": "center",
    "gap": "0.75rem",
    "marginBottom": "0.5rem",
}
"""Download button + scope radios row sitting above every results grid."""


def build_status_badge(status: JobStatus) -> html.Span:
    """Render a colored status badge.

    Shared by the My Tasks table and the task-results page header so both
    show a job's status identically.

    Args:
        status: The job's current status.

    Returns:
        An ``html.Span`` with the appropriate CSS class and icon.
    """
    icon_class = STATUS_ICONS.get(status, ICON_STATUS_PENDING)
    return html.Span(
        className=f"badge-status badge-{status.value}",
        children=[
            html.I(className=f"{icon_class} badge-status-icon"),
            status.value,
        ],
    )


def build_stat_card(value: int | str, label: str) -> html.Div:
    """Render a single stat card using the shared jobs stat-card classes.

    Args:
        value: The numeric or string value to display.
        label: The label beneath the value.

    Returns:
        An ``html.Div`` styled as a stat card.
    """
    return html.Div(
        className="jobs-stat-card",
        children=[
            html.Div(str(value), className="jobs-stat-value"),
            html.Div(str(label), className="jobs-stat-label"),
        ],
    )


# Keys that are internal to the framework and should never be shown
# to the user in the input parameters section.
_INTERNAL_KEYS = frozenset({"_stat_cards", "_params_exclude"})

# Parameter keys that contain SMILES strings eligible for a structure preview.
_SMILES_PARAM_KEYS = frozenset({"smiles"})


def _pretty_label(key: str) -> str:
    """Convert a snake_case or kebab-case key to a human-friendly label.

    Args:
        key: The raw parameter key (e.g. ``"protein_sequence"``).

    Returns:
        A title-cased label (e.g. ``"Protein Sequence"``).
    """
    return key.replace("_", " ").replace("-", " ").title()


def _render_smiles_preview(smiles: str) -> html.Img | None:
    """Render a SMILES string as an ``html.Img`` preview element.

    Automatically chooses between a reaction diagram (when the string
    contains ``>>``) and a single molecule image.

    Args:
        smiles: A SMILES or reaction SMILES string.

    Returns:
        An ``html.Img`` with a base64 data-URI ``src``, or ``None``
        if the string is empty, invalid, or RDKit is unavailable.
    """
    if not smiles or not smiles.strip():
        return None

    try:
        if ">>" in smiles:
            from enzyme_tk_app.app.utils.smiles_rendering import reaction_to_svg_data_uri  # noqa: PLC0415

            uri = reaction_to_svg_data_uri(smiles.strip(), height=200)
        else:
            from enzyme_tk_app.app.utils.smiles_rendering import smiles_to_svg_data_uri  # noqa: PLC0415

            uri = smiles_to_svg_data_uri(smiles.strip(), width=300, height=200)
    except Exception:  # noqa: BLE001 — graceful degradation
        return None

    if not uri:
        return None

    return html.Img(src=uri, className="jobs-params-preview")


def build_result_input_params(job: JobInfo) -> html.Div | None:
    """Build an "Input Parameters" section from the job's stored params.

    Automatically renders every key in ``job.params`` as a label → value
    row.  SMILES parameters get a structure-preview image inserted above
    their text value.

    Tools can suppress specific parameters by returning a
    ``_params_exclude`` list from ``compute.py``::

        return {
            "_params_exclude": ["internal_param"],
            ...
        }

    Framework-internal keys (``_stat_cards``, ``_params_exclude``) are always
    hidden.

    Args:
        job: A ``JobInfo`` whose ``params`` dict may contain user inputs.

    Returns:
        An ``html.Div`` with the section heading and a detail table,
        or ``None`` if there are no displayable parameters.
    """
    params = job.params or {}
    if not params:
        return None

    # ----------------------------------------------------
    # Collect tool-specified exclusions from the result dict.
    # ----------------------------------------------------
    result = job.result or {}
    exclude_keys = set(_INTERNAL_KEYS)
    params_exclude = result.get("_params_exclude")
    if isinstance(params_exclude, list):
        exclude_keys.update(str(k) for k in params_exclude)

    # ----------------------------------------------------
    # Build table rows, skipping excluded keys.
    # ----------------------------------------------------
    rows: list[html.Tr] = []
    for key, value in params.items():
        if key in exclude_keys:
            continue

        # The value might be a complex object (e.g. list, dict) so we convert it
        # to a string here.  A list keeps its repr — "['protein.csv', 'x.csv']" —
        # so multi-select params (databases, algorithms, filters) all read alike.
        str_value = str(value)
        # The label is derived from the key by replacing underscores and hyphens
        # with spaces and title-casing it.
        label = _pretty_label(key)

        # Insert a "Query Structure" image row above any SMILES parameter.
        if key in _SMILES_PARAM_KEYS:
            preview_img = _render_smiles_preview(str_value)
            if preview_img is not None:
                rows.append(
                    html.Tr(
                        children=[
                            html.Td("Query Structure", className="jobs-params-label"),
                            html.Td(preview_img, className="jobs-params-value"),
                        ]
                    )
                )

        value_cell = html.Td(str_value, className="jobs-params-value")

        rows.append(
            html.Tr(
                children=[
                    html.Td(label, className="jobs-params-label"),
                    value_cell,
                ]
            )
        )

    if not rows:
        return None

    return html.Div(
        className="jobs-params-section",
        children=[
            html.H4("Input Parameters", className="jobs-section-title"),
            html.Table(className="jobs-params-table", children=rows),
        ],
    )


# ---------------------------------------------------------------------------
# Shared AG Grid column definitions & grid builder
# ---------------------------------------------------------------------------


def numeric_col_def(
    field: str,
    header: str | None = None,
    width: int | None = None,
    decimals: int | None = None,
    exponential: bool = False,
) -> dict:
    """Return the column def for a numeric column.

    Always sets ``agNumberColumnFilter`` so the column filters as a number
    rather than a string.  Formatting is opt-in because the app renders three
    different kinds of number: integers (counts, positions, masses) that must
    stay unformatted, fractions and percentages that need fixed decimals, and
    e-values that only read sensibly in exponential form.

    Args:
        field: The dataframe column name.
        header: Optional display name; defaults to AG Grid's own.
        width: Optional column width in pixels.
        decimals: Decimal places for a fixed-point float.  Leave ``None`` for
            integers — formatting them renders ``269`` as ``269.0000``.
        exponential: Render in exponential notation with *decimals* places
            (default 2), for values like an e-value of ``3.09e-163``.

    Returns:
        An AG Grid ``columnDef`` dict.
    """
    col_def: dict = {"field": field, "filter": "agNumberColumnFilter"}
    if header:
        col_def["headerName"] = header
    if width:
        col_def["width"] = width

    if exponential:
        fn = f"params.value != null ? params.value.toExponential({decimals if decimals is not None else 2}) : ''"
        col_def["valueFormatter"] = {"function": fn}
    elif decimals is not None:
        col_def["valueFormatter"] = {"function": f"params.value != null ? params.value.toFixed({decimals}) : ''"}

    return col_def


def sequence_col_def(field: str, width: int = 300, header: str | None = None) -> dict:
    """Return the column def for an amino-acid sequence column.

    Every tool that shows protein sequences must use this so they render
    identically.  Sequences are truncated to one line (see the
    ``ag-cell-sequence`` class in ``09-ag-grid.css``) to keep row heights
    uniform; ``build_ag_grid`` adds a ``tooltipField`` so the full sequence
    shows on hover, and cell text selection keeps it copy-pasteable.

    Args:
        field: The dataframe column holding the sequence.
        width: Column width in pixels.
        header: Optional display name; defaults to AG Grid's own.

    Returns:
        An AG Grid ``columnDef`` dict.
    """
    col_def = {"field": field, "width": width, "cellClass": "ag-cell-sequence"}
    if header:
        col_def["headerName"] = header
    return col_def


def shared_col_defs() -> list[dict]:
    """Return column definitions shared across AG Grid result tables.

    Covers similarity scores, reaction / rule / bio metadata,
    substrate/product text fields, and molecular descriptors.
    Each call returns a **fresh** list to prevent cross-tool mutation.

    All numeric columns use ``agNumberColumnFilter``.  No ``headerName``
    is set — AG Grid auto-generates headers from the ``field`` name.

    Only columns whose ``field`` exists in the actual data will be
    rendered (filtering is done in :func:`build_ag_grid`).

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    return [
        # ── Similarity scores ────────────────────────────────────────
        {"field": col.COL_TANIMOTO, "width": 100, "filter": "agNumberColumnFilter"},
        {"field": col.COL_COSINE, "width": 100, "filter": "agNumberColumnFilter"},
        {"field": col.COL_RUSSELL, "width": 100, "filter": "agNumberColumnFilter"},
        # ── Reaction metadata ────────────────────────────────────────
        {"field": col.COL_DATABASE, "wrapText": True, "width": 120},
        {"field": col.COL_ID, "width": 120},
        {"field": col.COL_RXN_IDX, "width": 100},
        {
            "field": col.COL_MAPPED,
            # "cellClass": "cell-wrap-dash-ag-grid",
        },
        {
            "field": col.COL_UNMAPPED_SMILES,
            "width": 350,
            "cellClass": "cell-wrap-dash-ag-grid",
            # autoHeight tells AG Grid to automatically expand the row height
            # to fit the cell's content. Without it, content that doesn't fit in
            # a single row gets clipped.
            "autoHeight": True,
        },
        {"field": col.COL_ORIG_RXN_TEXT, "wrapText": True, "width": 120},
        # ── Rule / source metadata ───────────────────────────────────
        {"field": col.COL_RULE, "width": 120},
        {"field": col.COL_RULE_ID},
        {"field": col.COL_SOURCE},
        {"field": col.COL_STEPS},
        {"field": col.COL_QUALITY},
        {"field": col.COL_NATURAL},
        # ── Bio metadata ─────────────────────────────────────────────
        {"field": col.COL_ORGANISM},
        {"field": col.COL_PROTEIN_REFS},
        {"field": col.COL_PROTEIN_DB},
        {"field": col.COL_EC_NUM},
        # ── Substrates / products text ───────────────────────────────
        {"field": col.COL_SUBSTRATES, "width": 120},
        {"field": col.COL_PRODUCTS, "width": 120},
        # ── Molecular descriptors ────────────────────────────────────
        {"field": col.COL_SUBSTRATES_MOLWT, "filter": "agNumberColumnFilter"},
        {"field": col.COL_SUBSTRATES_TPSA, "filter": "agNumberColumnFilter"},
        {"field": col.COL_SUBSTRATES_MOLLOGP, "filter": "agNumberColumnFilter"},
        {"field": col.COL_SUBSTRATES_MAX_PARTIAL_CHARGE, "filter": "agNumberColumnFilter"},
        {"field": col.COL_SUBSTRATES_MIN_PARTIAL_CHARGE, "filter": "agNumberColumnFilter"},
        {"field": col.COL_PRODUCTS_MOLWT, "filter": "agNumberColumnFilter"},
        {"field": col.COL_PRODUCTS_TPSA, "filter": "agNumberColumnFilter"},
        {"field": col.COL_PRODUCTS_MOLLOGP, "filter": "agNumberColumnFilter"},
        {"field": col.COL_PRODUCTS_MAX_PARTIAL_CHARGE, "filter": "agNumberColumnFilter"},
        {"field": col.COL_PRODUCTS_MIN_PARTIAL_CHARGE, "filter": "agNumberColumnFilter"},
    ]


def _build_export_toolbar() -> html.Div:
    """Build the CSV download button and export-scope radios shown above the grid.

    Returns:
        An ``html.Div`` flex row with the download button on the left and
        the vertically stacked scope radios beside it.
    """
    return html.Div(
        style=STYLE_RESULTS_TOOLBAR,
        children=[
            html.Button(
                id=_BTN_DOWNLOAD_ID,
                className="btn-toolbar",
                n_clicks=0,
                children=[html.I(className=ICON_RESULTS_DOWNLOAD), "Download CSV"],
            ),
            # dbc renders component labels (``_children_props``), so each option
            # carries its own native ``title`` tooltip without extra ids.
            dbc.RadioItems(
                id=_RADIO_SCOPE_ID,
                className="jobs-toolbar-radios",
                value=SCOPE_FILTERED,
                inline=True,
                options=[
                    {
                        "label": html.Span(
                            "Filtered",
                            title="Export only the rows left by the column filters, in the current sort order.",
                        ),
                        "value": SCOPE_FILTERED,
                    },
                    {
                        "label": html.Span(
                            "Unfiltered",
                            title="Export every row in the table, ignoring column filters and sorting.",
                        ),
                        "value": SCOPE_ALL,
                    },
                ],
            ),
        ],
    )


def _csv_export_params(scope: str, column_defs: list[dict], job_id: str | None) -> dict:
    """Build AG Grid ``csvExportParams`` for the requested export scope.

    Args:
        scope: Either :data:`SCOPE_FILTERED` or :data:`SCOPE_ALL`.
        column_defs: The grid's current column definitions.
        job_id: The task id; its first :data:`_JOB_ID_CHARS` characters name
            the file.  Falls back to a generic name when absent.

    Returns:
        A ``csvExportParams`` dict for ``dag.AgGrid``.
    """
    # SVG columns hold ~20 KB base64 data URIs each; the SMILES they were drawn
    # from is exported instead, so the pictures stay reproducible from the CSV.
    keys = [cd["field"] for cd in column_defs if cd.get("field") and cd.get("cellRenderer") != "SvgRenderer"]

    return {
        "fileName": f"enzymetk-{job_id[:_JOB_ID_CHARS]}-{scope}.csv" if job_id else f"enzymetk-results-{scope}.csv",
        "columnKeys": keys,
        # AG Grid defaults to "filteredAndSorted"; "all" ignores filters and sort.
        "exportedRows": "all" if scope == SCOPE_ALL else "filteredAndSorted",
    }


@callback(
    Output(GRID_ID, "exportDataAsCsv"),
    Output(GRID_ID, "csvExportParams"),
    Input(_BTN_DOWNLOAD_ID, "n_clicks"),
    State(_RADIO_SCOPE_ID, "value"),
    State(GRID_ID, "columnDefs"),
    State(JOB_ID_SPAN_ID, "title"),
    prevent_initial_call=True,
)
def download_results_csv(
    n_clicks: int | None,
    scope: str,
    column_defs: list[dict] | None,
    job_id: str | None,
) -> tuple[bool, dict]:
    """Trigger AG Grid's client-side CSV export for the results table.

    dash-ag-grid resets ``exportDataAsCsv`` to ``False`` once it has fired,
    so repeat clicks work without any reset plumbing here.
    """
    if not n_clicks:
        raise PreventUpdate

    return True, _csv_export_params(scope, column_defs or [], job_id)


def build_ag_grid(column_defs: list[dict], df_payload: dict) -> html.Div:
    """Build a results table — the shared CSV export toolbar plus an AG Grid.

    Filters *column_defs* to only those whose ``field`` exists in
    ``df_payload["columns"]``, sets a default ``tooltipField`` on
    every column, and returns the configured grid wrapped together with
    :func:`_build_export_toolbar` so every tool gets the same download
    control for free.

    Non-field column defs (e.g. selection or row-number columns without
    a ``field`` key) are passed through unmodified.

    Cell text selection is enabled (``enableCellTextSelection`` +
    ``ensureDomOrder``) so users can copy/paste string content.

    Args:
        column_defs: Ordered list of AG Grid ``columnDef`` dicts.
            Typically built by concatenating tool-specific columns
            with :func:`shared_col_defs`.
        df_payload: Dict with ``columns`` (list[str]) and ``data``
            (list[dict]) keys from the compute result.

    Returns:
        An ``html.Div`` containing the export toolbar and the configured
        ``dag.AgGrid``.

    Raises:
        ValueError: If *df_payload* is not a dict or is missing the
            required ``columns`` / ``data`` keys.
    """
    if not isinstance(df_payload, dict):
        raise ValueError(f"df_payload must be a dict, got {type(df_payload).__name__}")
    missing = {"columns", "data"} - df_payload.keys()
    if missing:
        raise ValueError(f"df_payload is missing required key(s): {', '.join(sorted(missing))}")

    data_cols = set(df_payload["columns"])

    # Keep columns whose field exists in the data; pass through non-field
    # column defs (e.g. selection checkboxes, row-number columns).
    filtered_defs: list[dict] = []
    for cd in column_defs:
        field = cd.get("field")
        if field is not None and field not in data_cols:
            continue
        # Copy to avoid mutating the caller's dicts.
        filtered_defs.append(dict(cd))

    # Ensure every field column shows its own value as a hover tooltip.
    for cd in filtered_defs:
        field = cd.get("field")
        if field is not None:
            cd.setdefault("tooltipField", field)

    grid = dag.AgGrid(
        id=GRID_ID,
        columnDefs=filtered_defs,
        rowData=df_payload["data"],
        defaultColDef={
            "resizable": True,
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
            "filterParams": {
                "buttons": ["reset", "apply"],
                "closeOnApply": True,
            },
            # don't do autoheight on every cell — only on specific columns that need it
            # — for example, SVG renderers or multiline text columns
            # only the columns that need variable height should have "autoHeight": True in their individual columnDef
            # "autoHeight": True,
            "cellStyle": {"lineHeight": "1.4"},
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 20,
            "paginationPageSizeSelector": True,
            "domLayout": "autoHeight",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
        },
        style={"width": "100%"},
        className="ag-theme-balham",
    )

    return html.Div(children=[_build_export_toolbar(), grid])
