"""Tests for the Sequence & Structure-Based Similarity tool results module.

Exercises ``results_layout()`` and ``_get_column_defs()`` to verify that
the results grid is rendered correctly for various job result payloads
(valid data, empty data, missing dataframe, etc.).
"""

import dash_ag_grid as dag
import pytest
from dash import html

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.sequence_structure_similarity.results import (
    _get_column_defs,
    results_layout,
)

# ── Column definitions ────────────────────────────────────────────────────────


def test_get_column_defs_expected_fields():
    """The column defs should include the core FoldSeek output fields."""
    fields = {col["field"] for col in _get_column_defs()}

    # Core fields that must always be present
    expected = {"query", "target", "database", "fident", "bits", "evalue", "alnlen"}
    assert expected.issubset(fields), f"Missing fields: {expected - fields}"


def test_results_layout_renders_grid():
    """Valid result data should produce a layout containing an AG Grid."""
    sample_job = {
        "columns": ["query", "target", "database", "fident", "bits", "evalue"],
        "data": [
            {"query": "Q1", "target": "T1", "database": "pdb", "fident": 0.95, "bits": 120.5, "evalue": 1e-10},
            {"query": "Q1", "target": "T2", "database": "afdb", "fident": 0.80, "bits": 90.2, "evalue": 1e-5},
        ],
    }
    job = make_job(result={"dataframe": sample_job})
    layout = results_layout(job)

    # Layout should be a html.Div
    assert isinstance(layout, html.Div)

    # Should contain an AG Grid component
    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AG Grid in the results layout"


@pytest.mark.parametrize(
    ("input_result", "expected_message"),
    [
        (None, "Results could not be loaded"),
        ({"dataframe": None}, "Results could not be loaded"),
        ({"dataframe": {}}, "Results could not be loaded"),
        ({"dataframe": "not_a_dict"}, "Results could not be loaded"),
        ({"dataframe": {"columns": ["query"], "data": []}}, "No similar sequences or structures found"),
        ({"dataframe": {"columns": ["query"]}}, "No similar sequences or structures found"),
    ],
)
def test_results_layout_no_data_shows_message(input_result, expected_message):
    """Results with no valid data should render an appropriate message instead of a grid."""
    job = make_job(result=input_result)
    layout = results_layout(job)

    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 0

    paragraphs = find_components(layout, html.P)
    assert len(paragraphs) == 1
    assert expected_message in paragraphs[0].children
