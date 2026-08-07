"""Results layout for the Func-E Activity Prediction tool.

Renders the ranked protein hits as an interactive ``dag.AgGrid``.

The query reaction diagram and the stat cards (database, candidates scored,
top score, device, run time) are rendered automatically by
``build_result_input_params`` and the results-page header (which merges this
tool's ``_stat_cards``) in ``my_tasks_view_results.py`` — this module only
owns the grid.
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, numeric_col_def, sequence_col_def
from enzyme_tk_app.app.tools.funce.compute import PRED_COL
from enzyme_tk_app.app.utils import columns as col

# Four decimal places on every predicted number — the activity probability and
# the descriptors are both meaningless past that.
_DECIMALS = 4


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the Func-E results grid.

    Every column enzymetk emits is written out on its own line — the
    ``Funce_`` prefix and the ``_mean`` / ``_std`` suffixes come from the
    library, not from this app, and are spelled here exactly as they arrive so
    a reader can see the whole table without cross-referencing enzymetk.

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    defs: list[dict] = [
        # ── Identity ─────────────────────────────────────────────────
        {"field": col.COL_ENTRY, "pinned": "left", "width": 180},
        {"field": col.COL_DATABASE, "width": 140},
        sequence_col_def(col.COL_SEQUENCE, width=400),
        # ── Activity prediction ──────────────────────────────────────
        numeric_col_def(PRED_COL, decimals=_DECIMALS) | {"sort": "desc", "pinned": "left"},
        numeric_col_def("Funce_std_preds", decimals=_DECIMALS),
        # True on every row — enzymetk hardcodes it, but it is part of the
        # output, so it is shown rather than quietly withheld.
        {"field": "Funce_epistemic", "width": 140},
        # ── Predicted enzyme properties ──────────────────────────────
        numeric_col_def("Funce_Length_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_Length_std", decimals=_DECIMALS),
        numeric_col_def("Funce_Mass_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_Mass_std", decimals=_DECIMALS),
        numeric_col_def("Funce_Polarity_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_Polarity_std", decimals=_DECIMALS),
        numeric_col_def("Funce_temperature_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_temperature_std", decimals=_DECIMALS),
        # ── Predicted substrate descriptors ──────────────────────────
        numeric_col_def("Funce_substrates_MolWt_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MolWt_std", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MolLogP_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MolLogP_std", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MaxPartialCharge_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MaxPartialCharge_std", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MinPartialCharge_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_substrates_MinPartialCharge_std", decimals=_DECIMALS),
        # ── Predicted product descriptors ────────────────────────────
        numeric_col_def("Funce_products_MolWt_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MolWt_std", decimals=_DECIMALS),
        numeric_col_def("Funce_products_TPSA_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_products_TPSA_std", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MolLogP_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MolLogP_std", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MaxPartialCharge_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MaxPartialCharge_std", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MinPartialCharge_mean", decimals=_DECIMALS),
        numeric_col_def("Funce_products_MinPartialCharge_std", decimals=_DECIMALS),
    ]

    # Pin every header to its own field.  Without an explicit headerName AG Grid
    # humanises the field (``Funce_substrates_MolWt_mean`` renders as
    # "Funce_substrates Mol Wt_mean"), which misreports the column name.
    return [d | {"headerName": d["field"]} for d in defs]


def results_layout(job: JobInfo) -> html.Div:
    """Render Func-E job results as an interactive AG Grid.

    Args:
        job: A completed ``JobInfo`` whose ``result`` dict contains
            a ``dataframe`` key with ``columns`` and ``data``.

    Returns:
        An ``html.Div`` wrapping the results grid.
    """
    # Retrieve the job result dictionary.
    result = job.result or {}

    # Extract the dataframe payload from the job result.
    df_payload = result.get("dataframe")

    # Validate the dataframe payload structure before proceeding.
    if not isinstance(df_payload, dict) or "columns" not in df_payload or "data" not in df_payload:
        return html.Div(
            html.P("Results could not be loaded.", style={"color": "var(--status-failure)"}),
        )

    # Check if the dataframe contains any data before building the grid.
    if not df_payload["data"]:
        return html.Div(
            html.P(
                "No proteins were scored for this reaction.",
                style={"color": "var(--text-secondary)"},
            ),
        )

    defs = _get_column_defs()

    # ``build_ag_grid`` renders only fields that have a def, so a column a newer
    # enzymetk adds would silently vanish.  Append a bare def for anything the
    # list above does not name — unstyled, but visible.
    known = {d["field"] for d in defs}
    defs += [{"field": c, "headerName": c} for c in df_payload["columns"] if c not in known]

    return html.Div(children=[build_ag_grid(defs, df_payload)])
