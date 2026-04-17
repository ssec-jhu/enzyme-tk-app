"""Tests for the SMILES-to-SVG rendering utilities.

Covers ``_svg_to_data_uri``, ``smiles_to_svg_data_uri``, and
``reaction_to_svg_data_uri`` from ``enzyme_tk_app.app.utils.smiles_rendering``,
plus ``_render_smiles_preview`` from ``enzyme_tk_app.app.components.results_helpers``.
"""

import pytest
from dash import html

from enzyme_tk_app.app.components.results_helpers import (
    _render_smiles_preview,
    build_ag_grid,
    build_result_input_params,
)
from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.utils.smiles_rendering import (
    _svg_to_data_uri,
    reaction_to_svg_data_uri,
    smiles_to_svg_data_uri,
)

# ── _svg_to_data_uri — early returns ─────────────────────────────────────────


@pytest.mark.parametrize(
    "svg_input",
    ["", None],
    ids=["empty-string", "none-value"],
)
def test_svg_to_data_uri_returns_empty_for_falsy_input(svg_input):
    """_svg_to_data_uri must return an empty string when given falsy input."""
    assert _svg_to_data_uri(svg_input) == ""


# ── smiles_to_svg_data_uri — early returns ───────────────────────────────────


@pytest.mark.parametrize(
    "smiles_input",
    ["", "   ", None],
    ids=["empty-string", "whitespace-only", "none-value"],
)
def test_smiles_to_svg_data_uri_returns_empty_for_blank_input(smiles_input):
    """smiles_to_svg_data_uri must return an empty string for empty or whitespace-only input."""
    assert smiles_to_svg_data_uri(smiles_input) == ""


def test_smiles_to_svg_data_uri_returns_empty_for_invalid_smiles():
    """smiles_to_svg_data_uri must return an empty string when RDKit cannot parse the SMILES."""
    assert smiles_to_svg_data_uri("NOT_A_VALID_SMILES_STRING!!!") == ""


# ── reaction_to_svg_data_uri — parametrized with multiple reaction SMILES ────


@pytest.mark.parametrize(
    "reaction_smiles",
    [
        "CC(=O)O.CCO>>CC(=O)OCC",
        "O>>O",
        "CC(O)=O.[NH3]>>CC(=O)N.O",
        "CC=O.[H][H]>>CCO",
        "c1ccccc1.Cl>>c1ccc(Cl)cc1",
    ],
    ids=[
        "esterification",
        "identity-reaction",
        "amide-bond-formation",
        "aldehyde-reduction",
        "chlorination",
    ],
)
def test_reaction_to_svg_data_uri_valid_reactions(reaction_smiles):
    """reaction_to_svg_data_uri must return a valid base64 data URI for parseable reactions."""
    result = reaction_to_svg_data_uri(reaction_smiles)

    assert result.startswith("data:image/svg+xml;base64,"), (
        f"Expected a data URI for {reaction_smiles!r}, got: {result[:50]}..."
    )


@pytest.mark.parametrize(
    "reaction_input",
    [None, "", "   "],
    ids=["none", "empty-string", "whitespace-only"],
)
def test_reaction_to_svg_data_uri_returns_empty_for_blank(reaction_input):
    """reaction_to_svg_data_uri must return an empty string for blank input."""
    assert reaction_to_svg_data_uri(reaction_input) == ""


def test_reaction_to_svg_data_uri_returns_empty_for_invalid_reaction():
    """reaction_to_svg_data_uri must return an empty string when RDKit cannot parse the reaction."""
    assert reaction_to_svg_data_uri("NOT>>A>>VALID>>REACTION!!!@#$%") == ""


# ── _render_smiles_preview ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("smiles", "expect_reaction"),
    [
        ("CCO", False),
        ("CC(=O)O.CCO>>CC(=O)OCC", True),
    ],
    ids=["molecule", "reaction"],
)
def test_render_smiles_preview_returns_img(smiles, expect_reaction):
    """_render_smiles_preview must return an html.Img with a data-URI src."""
    result = _render_smiles_preview(smiles)

    assert isinstance(result, html.Img)
    assert result.src.startswith("data:image/svg+xml;base64,")
    assert result.className == "jobs-params-preview"


@pytest.mark.parametrize(
    "smiles",
    [None, "", "   "],
    ids=["none", "empty-string", "whitespace-only"],
)
def test_render_smiles_preview_returns_none_for_blank(smiles):
    """_render_smiles_preview must return None for empty or blank input."""
    assert _render_smiles_preview(smiles) is None


def test_render_smiles_preview_returns_none_for_invalid_smiles():
    """_render_smiles_preview must return None when RDKit cannot parse the input."""
    # Completely unparseable string — the except branch catches the failure
    assert _render_smiles_preview("NOT_A_VALID_SMILES!!!@#$%") is None


# ── build_ag_grid — validation ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_payload",
    [
        "not-a-dict",
        42,
        ["list", "value"],
    ],
    ids=["string", "int", "list"],
)
def test_build_ag_grid_raises_for_non_dict(bad_payload):
    """build_ag_grid must raise ValueError when df_payload is not a dict."""
    with pytest.raises(ValueError, match="must be a dict"):
        build_ag_grid([], bad_payload)


@pytest.mark.parametrize(
    ("payload", "missing_key"),
    [
        ({"columns": ["a"]}, "data"),
        ({"data": [{"a": 1}]}, "columns"),
        ({}, "columns"),
    ],
    ids=["missing-data", "missing-columns", "empty-dict"],
)
def test_build_ag_grid_raises_for_missing_keys(payload, missing_key):
    """build_ag_grid must raise ValueError when required keys are absent."""
    with pytest.raises(ValueError, match="missing required key") as exc_info:
        build_ag_grid([], payload)
    assert missing_key in str(exc_info.value)


# ── build_result_input_params — SMILES preview row ──────────────────────────


def test_build_result_input_params_inserts_query_structure_for_smiles_key():
    """When params contain a 'smiles' key, a 'Query Structure' image row must appear."""
    job = make_job(params={"task_name": "test", "smiles": "CCO"})
    layout = build_result_input_params(job)

    assert isinstance(layout, html.Div)

    # The table should contain a "Query Structure" label row with an html.Img
    all_rows = find_components(layout, html.Tr)
    structure_rows = [
        row for row in all_rows if any(td.children == "Query Structure" for td in find_components(row, html.Td))
    ]
    assert len(structure_rows) == 1, "Expected exactly one 'Query Structure' row"

    # The image cell should contain an html.Img with a data-URI src
    imgs = find_components(structure_rows[0], html.Img)
    assert len(imgs) == 1
    assert imgs[0].src.startswith("data:image/svg+xml;base64,")
