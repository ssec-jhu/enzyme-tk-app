"""Tests for the Func-E Activity Prediction tool.

Two things are pinned here:

* **The results grid** — every column header must be the raw enzymetk
  dataframe column name, never a friendlier display label.  A relabelled
  header (e.g. "Activity Probability" for ``Funce_prediction``) hides which
  enzymetk column a number actually came from, so scientists cannot trace a
  result back to the model output.
* **The dropped columns** — ``compute.DROPPED_COLS`` names what is stripped
  from the Funce output before it is JSON-encoded.  Dropping too much silently
  loses results; dropping an embedding short breaks the payload.

Neither module pulls in a heavy machine-learning dependency at import time —
``compute.py`` defers ``torch``/``enzymetk`` to inside ``run()`` — so these
tests import both directly and need no mocking.
"""

import dash_ag_grid as dag
import pytest
from dash import html

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.funce.compute import DROPPED_COLS
from enzyme_tk_app.app.tools.funce.results import _get_column_defs, results_layout

# Every column the Func-E grid is expected to define, spelled out rather than
# generated: this list is the contract with enzymetk's output, so a change on
# either side should show up as a diff a reviewer can read.
EXPECTED_FIELDS = [
    # Identity.
    "Entry",
    "database",
    "Sequence",
    # Activity prediction.
    "Funce_prediction",
    "Funce_std_preds",
    "Funce_epistemic",
    # Predicted enzyme properties (mean/std pair per feature).
    "Funce_Length_mean",
    "Funce_Length_std",
    "Funce_Mass_mean",
    "Funce_Mass_std",
    "Funce_Polarity_mean",
    "Funce_Polarity_std",
    "Funce_temperature_mean",
    "Funce_temperature_std",
    # Predicted substrate descriptors.
    "Funce_substrates_MolWt_mean",
    "Funce_substrates_MolWt_std",
    "Funce_substrates_MolLogP_mean",
    "Funce_substrates_MolLogP_std",
    "Funce_substrates_MaxPartialCharge_mean",
    "Funce_substrates_MaxPartialCharge_std",
    "Funce_substrates_MinPartialCharge_mean",
    "Funce_substrates_MinPartialCharge_std",
    # Predicted product descriptors.
    "Funce_products_MolWt_mean",
    "Funce_products_MolWt_std",
    "Funce_products_TPSA_mean",
    "Funce_products_TPSA_std",
    "Funce_products_MolLogP_mean",
    "Funce_products_MolLogP_std",
    "Funce_products_MaxPartialCharge_mean",
    "Funce_products_MaxPartialCharge_std",
    "Funce_products_MinPartialCharge_mean",
    "Funce_products_MinPartialCharge_std",
]


# ── Results grid ─────────────────────────────────────────────────────────────


def test_get_column_defs_header_names_match_their_fields():
    """No column may be relabelled — every headerName equals its own field."""
    col_defs = _get_column_defs()

    assert len(col_defs) > 0

    for col_def in col_defs:
        field = col_def["field"]
        assert col_def.get("headerName") == field, (
            f"Column '{field}' shows the display name {col_def.get('headerName')!r}; "
            "headers must be the raw enzymetk column name."
        )


def test_get_column_defs_covers_every_expected_raw_field():
    """The grid must define exactly the identity, prediction, and per-feature columns."""
    actual_fields = [col_def["field"] for col_def in _get_column_defs()]

    # Compare sorted lists so the failure message names both a column that
    # disappeared and a column that appeared without being expected.
    assert sorted(actual_fields) == sorted(EXPECTED_FIELDS), (
        f"Missing: {sorted(set(EXPECTED_FIELDS) - set(actual_fields))}, "
        f"unexpected: {sorted(set(actual_fields) - set(EXPECTED_FIELDS))}"
    )


def test_results_layout_renders_column_the_defs_do_not_name():
    """A column a newer enzymetk adds must still reach the grid, not vanish.

    ``build_ag_grid`` renders only fields that have a column def, so
    ``results_layout`` appends a bare def for any payload column the explicit
    list above does not mention.
    """
    # An invented column standing in for whatever a future enzymetk emits.
    future_column = "Funce_future_col"

    job = make_job(
        result={
            "dataframe": {
                "columns": ["Entry", "Funce_prediction", future_column],
                "data": [{"Entry": "P12345", "Funce_prediction": 0.97, future_column: 1.23}],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)

    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AgGrid in results_layout"

    rendered_fields = [col_def["field"] for col_def in grids[0].columnDefs]
    assert future_column in rendered_fields, (
        f"Unknown payload column '{future_column}' was dropped; grid rendered {rendered_fields}"
    )


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"dataframe": None},
        {"dataframe": {"columns": ["Entry"]}},
        {"dataframe": {"data": [{"Entry": "P12345"}]}},
        {"dataframe": {"columns": [], "data": []}},
    ],
    ids=["no-dataframe", "dataframe-not-a-dict", "data-key-missing", "columns-key-missing", "no-rows"],
)
def test_results_layout_explains_itself_instead_of_rendering_an_empty_grid(result):
    """A malformed or empty payload must produce a readable message, not a crash.

    A grid with no rows and no columns looks like a broken page, so every
    unusable payload is turned into a sentence the user can act on.
    """
    layout = results_layout(make_job(result=result))

    assert isinstance(layout, html.Div)
    assert find_components(layout, dag.AgGrid) == [], "An unusable payload must not reach the grid"

    # Some explanatory text must be shown in its place.
    paragraphs = find_components(layout, html.P)
    assert len(paragraphs) == 1
    assert str(paragraphs[0].children).strip() != ""


# ── Dropped columns ──────────────────────────────────────────────────────────


def test_dropped_cols_never_names_a_column_the_grid_displays():
    """The drop list and the grid's column list must not overlap.

    Both are hand-written, so the failure mode is a name landing in both: the
    column would be stripped in ``compute.run()`` and then silently missing
    from a grid that declares it.  Checked without importing torch or enzymetk.
    """
    overlap = sorted(set(DROPPED_COLS) & set(EXPECTED_FIELDS))

    assert overlap == [], f"Dropped columns the grid also displays: {overlap}"


def test_dropped_cols_covers_every_embedding_and_intermediate():
    """Every non-result column the Funce step leaves on the frame is named.

    The four embeddings must go — their cells hold ndarrays that
    ``json.dumps`` cannot encode.  The ``pred_*`` / ``inverse_transformed_*``
    scratch columns hold only the last ensemble model's values, so they are
    dropped as misleading rather than unserialisable.
    """
    # enzymetk's ENZYME_COLS + REACTION_COLS, the features it writes scratch
    # columns for (predict_Funce_step.py).  Spelled out rather than imported:
    # importing enzymetk would pull in torch.
    features = [
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
    expected = ["esm3_mean", "rxnfp", "substrate_unimol_repr", "product_unimol_repr", "pred_Activity"]
    for feature in features:
        expected.append(f"pred_{feature}")
        expected.append(f"inverse_transformed_pred_{feature}")

    assert sorted(DROPPED_COLS) == sorted(expected), (
        f"Missing: {sorted(set(expected) - set(DROPPED_COLS))}, unexpected: {sorted(set(DROPPED_COLS) - set(expected))}"
    )
