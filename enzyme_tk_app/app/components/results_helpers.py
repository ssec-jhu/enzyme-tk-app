"""Shared UI helpers for tool results pages.

Provides :func:`build_result_stat_cards` which automatically renders a
stat-card strip from a job's ``_stat_cards`` key using the shared
``jobs-stat-card`` / ``jobs-stats-row`` CSS classes.

Also provides :func:`build_result_input_params` which auto-renders the job's
input parameters in a label → value table.

Provides shared ``TABLE_STYLE_*`` constants for ``dash_table.DataTable``.
``DataTable`` does **not** support ``className`` — it only accepts
``style_*`` keyword arguments.  These constants ensure every tool's
results table looks identical without duplicating style dicts.

Provides :func:`shared_col_defs` and :func:`build_ag_grid` for tools
that render results via ``dag.AgGrid``.  Tool-specific columns (e.g. SVG
previews) are prepended by each tool; the shared columns cover
similarity scores, reaction metadata, molecular descriptors, etc.

Usage (DataTable)::

    from enzyme_tk_app.app.components.results_helpers import (
        TABLE_STYLE_CELL,
        TABLE_STYLE_DATA_CONDITIONAL,
        TABLE_STYLE_HEADER,
        TABLE_STYLE_TABLE,
    )

    dash_table.DataTable(
        ...,
        style_table=TABLE_STYLE_TABLE,
        style_header=TABLE_STYLE_HEADER,
        style_cell=TABLE_STYLE_CELL,
        style_data_conditional=TABLE_STYLE_DATA_CONDITIONAL,
    )

Usage (AG Grid)::

    from enzyme_tk_app.app.components.results_helpers import (
        build_ag_grid,
        shared_col_defs,
    )

    column_defs = [my_tool_specific_col] + shared_col_defs()
    grid = build_ag_grid(column_defs, df_payload)
"""

from __future__ import annotations

import dash_ag_grid as dag
from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.tools.substrate_product_similarity import SimilarityAlgorithm
from enzyme_tk_app.app.utils import columns as col

# ---------------------------------------------------------------------------
# Shared DataTable style constants
# ---------------------------------------------------------------------------
# ``dash_table.DataTable`` does NOT support ``className``.  It only
# accepts ``style_*`` keyword arguments, so these must be Python dicts
# rather than CSS classes.  Import these in every tool's ``results.py``.

TABLE_STYLE_TABLE: dict = {"overflowX": "auto"}
"""Outer table wrapper — enables horizontal scroll for wide tables."""

TABLE_STYLE_HEADER: dict = {
    "backgroundColor": "#1E3A5F",
    "color": "white",
    "fontWeight": "600",
    "textAlign": "left",
}
"""Column header cells — dark blue background, white text."""

TABLE_STYLE_CELL: dict = {
    "padding": "0.5rem 0.75rem",
    "fontFamily": "Inter, sans-serif",
    "fontSize": "0.85rem",
    "textAlign": "left",
    "border": "1px solid #E2E8F0",
}
"""Default styling for every data cell."""

TABLE_STYLE_DATA_CONDITIONAL: list[dict] = [
    {
        "if": {"row_index": "odd"},
        "backgroundColor": "#F7FAFC",
    },
]
"""Alternating-row striping for readability."""


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


def build_result_stat_cards(job: JobInfo) -> html.Div | None:
    """Build a stat-card strip from the job's ``_stat_cards`` key, if present.

    Tools opt-in by returning a ``_stat_cards`` key from ``compute.py``::

        return {
            "_stat_cards": [
                {"label": "Elapsed", "value": "12.3s"},
                {"label": "Status",  "value": "OK"},
            ],
            ...
        }

    Each item must have ``label`` and ``value`` string keys.
    If the result has no ``_stat_cards``, this returns ``None``.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict may contain
            a ``_stat_cards`` list of ``{"label": ..., "value": ...}`` dicts.

    Returns:
        An ``html.Div`` with a heading and a row of stat cards, or
        ``None`` if no ``_stat_cards`` data is present.
    """
    result = job.result or {}
    meta_items = result.get("_stat_cards")
    if not meta_items or not isinstance(meta_items, list):
        return None

    cards = [
        build_stat_card(item.get("value", ""), item.get("label", "")) for item in meta_items if isinstance(item, dict)
    ]
    if not cards:
        return None

    return html.Div(
        children=[
            html.H4("Summary", className="jobs-section-title"),
            html.Div(className="jobs-stats-row", children=cards),
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
        # to a string here.
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

STYLE_LONG_TEXT: dict = {
    "fontSize": "0.8rem",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
}
"""Cell style for long text columns — single-line with ellipsis overflow."""


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
        {"field": SimilarityAlgorithm.TANIMOTO.column, "width": 100, "filter": "agNumberColumnFilter"},
        {"field": SimilarityAlgorithm.COSINE.column, "width": 100, "filter": "agNumberColumnFilter"},
        {"field": SimilarityAlgorithm.RUSSELL.column, "width": 100, "filter": "agNumberColumnFilter"},
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


def build_ag_grid(column_defs: list[dict], df_payload: dict) -> dag.AgGrid:
    """Build an AG Grid component from column definitions and a dataframe payload.

    Filters *column_defs* to only those whose ``field`` exists in
    ``df_payload["columns"]``, sets a default ``tooltipField`` on
    every column, and returns a fully configured ``dag.AgGrid``.

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
        A configured ``dag.AgGrid`` component.

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

    return dag.AgGrid(
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
            "paginationPageSizeSelector": [10, 20, 50, 100],
            "domLayout": "autoHeight",
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
        },
        style={"width": "100%"},
        className="ag-theme-balham",
    )
