"""Results layout for the Func-E Activity Prediction tool.

Renders the ranked protein hits as an interactive ``dag.AgGrid``.

The query reaction diagram and the stat cards (database, candidates scored,
top score, device, run time) are rendered automatically by the shared
``build_result_input_params`` / ``build_result_stat_cards`` helpers in
``my_tasks_view_results.py`` — this module only owns the grid.
"""

from __future__ import annotations

from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, numeric_col_def, sequence_col_def
from enzyme_tk_app.app.tools.funce.compute import PRED_COL, PREDICTION_NAME

# Regression heads the ensemble predicts alongside the activity probability,
# in the order enzymetk emits them.  Each yields a ``_mean`` / ``_std`` pair.
PREDICTED_FEATURES = [
    "Length",
    "Mass",
    "Polarity",
    "temperature",
    "substrates_MolWt",
    "substrates_MolLogP",
    "substrates_MaxPartialCharge",
    "substrates_MinPartialCharge",
    "products_MolWt",
    "products_TPSA",
    "products_MolLogP",
    "products_MaxPartialCharge",
    "products_MinPartialCharge",
]

# Four decimal places on every predicted number — the activity probability and
# the descriptors are both meaningless past that.
_DECIMALS = 4


def _get_column_defs() -> list[dict]:
    """Return the ordered column definitions for the Func-E results grid.

    Identity columns first, then the activity prediction, then the
    ``_mean``/``_std`` pair for each predicted feature.  The pairs are
    generated rather than hand-written so they cannot drift from the
    feature list the ensemble actually emits.

    Returns:
        List of AG Grid ``columnDef`` dicts in display order.
    """
    defs: list[dict] = [
        {"field": "Entry", "pinned": "left", "width": 180},
        numeric_col_def(PRED_COL, "Activity Probability", decimals=_DECIMALS) | {"sort": "desc", "pinned": "left"},
        numeric_col_def(f"{PREDICTION_NAME}_std_preds", "Prediction Std", decimals=_DECIMALS),
        {"field": "database", "headerName": "Database", "width": 140},
        sequence_col_def("Sequence", width=400),
    ]
    # ``{name}_epistemic`` is omitted on purpose: enzymetk hardcodes it to True on
    # every row, and a JSON boolean renders as a checkbox, so it is pure noise.

    for feature in PREDICTED_FEATURES:
        defs.append(numeric_col_def(f"{PREDICTION_NAME}_{feature}_mean", decimals=_DECIMALS))
        defs.append(numeric_col_def(f"{PREDICTION_NAME}_{feature}_std", decimals=_DECIMALS))

    return defs


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

    # Build and return the AG Grid for displaying the results.
    # The AG Grid is constructed using the column definitions and the dataframe payload.
    grid = build_ag_grid(_get_column_defs(), df_payload)
    return html.Div(children=[grid])
