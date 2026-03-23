"""Shared UI helpers for tool results pages.

Provides :func:`build_result_meta` which automatically renders a
metadata strip from a job's ``_meta`` key using the shared
``jobs-stat-card`` / ``jobs-stats-row`` CSS classes.

Also provides :func:`build_input_params` which auto-renders the job's
input parameters in a label → value table.  Long values (protein
sequences, CMILES strings, etc.) get a scrollable monospace container.

Provides shared ``TABLE_STYLE_*`` constants for ``dash_table.DataTable``.
``DataTable`` does **not** support ``className`` — it only accepts
``style_*`` keyword arguments.  These constants ensure every tool's
results table looks identical without duplicating style dicts.

Usage::

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
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo

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


def build_result_meta(job: JobInfo) -> html.Div | None:
    """Build a metadata strip from the job's ``_meta`` key, if present.

    Tools opt-in by returning a ``_meta`` key from ``compute.py``::

        return {
            "_meta": [
                {"label": "Elapsed", "value": "12.3s"},
                {"label": "Status",  "value": "OK"},
            ],
            ...
        }

    Each item must have ``label`` and ``value`` string keys.
    If the result has no ``_meta``, this returns ``None``.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict may contain
            a ``_meta`` list of ``{"label": ..., "value": ...}`` dicts.

    Returns:
        An ``html.Div`` with a heading and a row of stat cards, or
        ``None`` if no ``_meta`` data is present.
    """
    result = job.result or {}
    meta_items = result.get("_meta")
    if not meta_items or not isinstance(meta_items, list):
        return None

    cards = [
        html.Div(
            className="jobs-stat-card",
            children=[
                html.Div(str(item.get("value", "")), className="jobs-stat-value"),
                html.Div(str(item.get("label", "")), className="jobs-stat-label"),
            ],
        )
        for item in meta_items
        if isinstance(item, dict)
    ]
    if not cards:
        return None

    return html.Div(
        children=[
            html.H4("Summary", className="jobs-section-title"),
            html.Div(className="jobs-stats-row", children=cards),
        ],
    )


# Threshold (characters) above which a value is rendered in a
# scrollable monospace container instead of inline text.
_LONG_VALUE_THRESHOLD = 60

# Keys that are internal to the framework and should never be shown
# to the user in the input parameters section.
_INTERNAL_KEYS = frozenset({"_meta", "_params_exclude"})


def _pretty_label(key: str) -> str:
    """Convert a snake_case or kebab-case key to a human-friendly label.

    Args:
        key: The raw parameter key (e.g. ``"protein_sequence"``).

    Returns:
        A title-cased label (e.g. ``"Protein Sequence"``).
    """
    return key.replace("_", " ").replace("-", " ").title()


def build_result_input_params(job: JobInfo) -> html.Div | None:
    """Build an "Input Parameters" section from the job's stored params.

    Automatically renders every key in ``job.params`` as a label → value
    row.  Long values (protein sequences, CMILES, SMILES, etc.) are
    displayed in a scrollable monospace container.

    Tools can suppress specific parameters by returning a
    ``_params_exclude`` list from ``compute.py``::

        return {
            "_params_exclude": ["internal_param"],
            ...
        }

    Framework-internal keys (``_meta``, ``_params_exclude``) are always
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

    # Collect tool-specified exclusions from the result dict.
    result = job.result or {}
    exclude_keys = set(_INTERNAL_KEYS)
    params_exclude = result.get("_params_exclude")
    if isinstance(params_exclude, list):
        exclude_keys.update(str(k) for k in params_exclude)

    # Build table rows, skipping excluded keys.
    rows: list[html.Tr] = []
    for key, value in params.items():
        if key in exclude_keys:
            continue

        str_value = str(value)
        label = _pretty_label(key)

        if len(str_value) >= _LONG_VALUE_THRESHOLD:
            # Long value → scrollable monospace cell
            value_cell = html.Td(str_value, className="jobs-params-value-long")
        else:
            # Short value → plain inline text
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
