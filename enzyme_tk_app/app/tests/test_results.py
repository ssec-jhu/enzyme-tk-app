import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pytest
from dash import html
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.backend.models import JobStatus
from enzyme_tk_app.app.components.results_helpers import (
    GRID_ID,
    SCOPE_ALL,
    SCOPE_FILTERED,
    _csv_export_params,
    _pretty_label,
    build_ag_grid,
    build_result_input_params,
    build_stat_card,
    build_status_badge,
    download_results_csv,
)

from .conftest import find_components, get_text, make_job

# ---------------------------------------------------------------------------
# build_status_badge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    list(JobStatus),
    ids=[s.value for s in JobStatus],
)
def test_build_status_badge_renders_for_every_status(status):
    """``build_status_badge`` must return a Span with the correct badge class and status text."""
    badge = build_status_badge(status)

    assert isinstance(badge, html.Span)
    assert f"badge-{status.value}" in badge.className
    assert status.value in get_text(badge)


# ---------------------------------------------------------------------------
# build_stat_card
# ---------------------------------------------------------------------------


def test_build_stat_card_renders_value_and_label():
    """``build_stat_card`` must produce a card with the given value and label."""
    card = build_stat_card(42, "Total Tasks")

    assert isinstance(card, html.Div)
    assert card.className == "jobs-stat-card"
    text = get_text(card)
    assert "42" in text
    assert "Total Tasks" in text


# ---------------------------------------------------------------------------
# build_result_input_params
# ---------------------------------------------------------------------------


def test_build_input_params_returns_none_for_empty_params():
    """No params → ``None``; the section should not render at all."""
    assert build_result_input_params(make_job(params={})) is None


def test_build_input_params_returns_none_when_params_is_none():
    """``params=None`` (e.g. if the job was never submitted) → ``None``."""
    job = make_job()
    job.params = None  # type: ignore[assignment]
    assert build_result_input_params(job) is None


def test_build_input_params_renders_label_value_rows():
    """Each parameter should appear as a human-friendly label with its value, one row per param."""
    params = {"protein_sequence": "MKFL", "temperature": "37"}
    component = build_result_input_params(make_job(params=params))

    assert component is not None
    text = get_text(component)
    assert "Input Parameters" in text
    assert "Protein Sequence" in text
    assert "MKFL" in text
    assert "Temperature" in text
    assert "37" in text

    # Row count must match the number of visible parameters.
    rows = find_components(component, html.Tr)
    assert len(rows) == 2


def test_build_input_params_hides_internal_keys():
    """Framework-internal keys (``_stat_cards``, ``_params_exclude``) must never appear."""
    params = {"visible": "yes", "_stat_cards": "hidden", "_params_exclude": "hidden"}
    component = build_result_input_params(make_job(params=params))

    text = get_text(component)
    assert "Visible" in text
    # Internal keys must not produce any table row.
    rows = find_components(component, html.Tr)
    assert len(rows) == 1


def test_build_input_params_respects_params_exclude_from_result():
    """Tool-specified ``_params_exclude`` in the result dict should suppress those params."""
    params = {"keep_me": "yes", "hide_me": "secret"}
    result = {"_params_exclude": ["hide_me"]}
    component = build_result_input_params(make_job(params=params, result=result))

    text = get_text(component)
    assert "Keep Me" in text
    assert "secret" not in text

    rows = find_components(component, html.Tr)
    assert len(rows) == 1


def test_build_input_params_returns_none_when_all_params_excluded():
    """If every parameter is excluded, the section should not render."""
    params = {"_stat_cards": "x"}
    assert build_result_input_params(make_job(params=params)) is None


def test_build_input_params_non_string_values_are_stringified():
    """Non-string param values (ints, lists, bools) should be converted to strings."""
    params = {"count": 42, "active": True, "tags": ["a", "b"]}
    component = build_result_input_params(make_job(params=params))

    text = get_text(component)
    assert "42" in text
    assert "True" in text
    assert "['a', 'b']" in text


@pytest.mark.parametrize(
    ("databases", "expected_cell_text"),
    [
        (
            ["protein_20_slice_1.csv", "Funce_pairs.pkl"],
            "['protein_20_slice_1.csv', 'Funce_pairs.pkl']",
        ),
        ("protein_20_slice_1.csv", "protein_20_slice_1.csv"),
    ],
    ids=["list-of-filenames", "non-list-falls-back-to-str"],
)
def test_build_input_params_databases_render_as_plain_filenames(databases, expected_cell_text):
    """The ``databases`` row names each database exactly as it is named on disk.

    A list keeps its repr — brackets and quotes, like every other multi-select
    param (``algorithms``, the filters) — and the filenames inside it are
    verbatim, extensions included, never prettified or stemmed.  A non-list value
    (a stray single-select dropdown value) must still stringify rather than raise.
    """
    component = build_result_input_params(make_job(params={"databases": databases}))

    assert component is not None
    value_cells = [td for td in find_components(component, html.Td) if td.className == "jobs-params-value"]
    assert [get_text(td) for td in value_cells] == [expected_cell_text]


# ---------------------------------------------------------------------------
# _pretty_label — internal helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("protein_sequence", "Protein Sequence"),
        ("max-duration", "Max Duration"),
        ("temperature", "Temperature"),
        ("Name", "Name"),
    ],
    ids=["snake-case", "kebab-case", "single-word", "already-titlecase"],
)
def test_pretty_label(raw, expected):
    """``_pretty_label`` converts raw keys to human-friendly title-case labels."""
    assert _pretty_label(raw) == expected


# ---------------------------------------------------------------------------
# build_ag_grid — CSV export toolbar
# ---------------------------------------------------------------------------

_PAYLOAD = {"columns": ["a"], "data": [{"a": 1}]}


def test_build_ag_grid_wraps_grid_with_export_toolbar():
    """The results table must pair one addressable grid with one download button and radio group."""
    table = build_ag_grid([{"field": "a"}], _PAYLOAD)

    assert isinstance(table, html.Div)

    grids = find_components(table, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AgGrid"
    assert grids[0].id == GRID_ID, "The grid must carry the id the export callback targets"

    assert len(find_components(table, html.Button)) == 1, "Expected exactly one download button"

    radios = find_components(table, dbc.RadioItems)
    assert len(radios) == 1, "Expected exactly one export-scope radio group"
    assert radios[0].value == SCOPE_FILTERED, "Filtered is the default — it matches what the user sees"
    assert [opt["value"] for opt in radios[0].options] == [SCOPE_FILTERED, SCOPE_ALL]
    # Each option explains itself through a native tooltip on its label.
    assert all(opt["label"].title for opt in radios[0].options)


# ---------------------------------------------------------------------------
# _csv_export_params
# ---------------------------------------------------------------------------


def test_csv_export_params_drops_svg_columns():
    """SVG columns hold huge base64 URIs and must never reach the CSV."""
    defs = [
        {"field": "reaction_svg", "cellRenderer": "SvgRenderer"},
        {"field": "unmapped_smiles"},
        {"field": "tanimoto"},
        {"headerName": "no-field-col"},
    ]

    assert _csv_export_params(SCOPE_FILTERED, defs, "abc")["columnKeys"] == ["unmapped_smiles", "tanimoto"]


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (SCOPE_FILTERED, "filteredAndSorted"),
        (SCOPE_ALL, "all"),
    ],
    ids=["filtered", "unfiltered"],
)
def test_csv_export_params_maps_scope_to_exported_rows(scope, expected):
    """The radio value must select AG Grid's ``exportedRows`` mode."""
    assert _csv_export_params(scope, [], "abc")["exportedRows"] == expected


@pytest.mark.parametrize(
    ("job_id", "expected"),
    [
        # Truncated to the same 6-char prefix the My Tasks table shows.
        ("7e1de513-69ae-44f8-a32f-626b447308f8", "enzymetk-7e1de5-filtered.csv"),
        ("abcd", "enzymetk-abcd-filtered.csv"),
        (None, "enzymetk-results-filtered.csv"),
        ("", "enzymetk-results-filtered.csv"),
    ],
    ids=["full-uuid", "shorter-than-prefix", "none-job-id", "empty-job-id"],
)
def test_csv_export_params_names_file_after_the_job(job_id, expected):
    """The download is named after the task so a user can trace it back."""
    assert _csv_export_params(SCOPE_FILTERED, [], job_id)["fileName"] == expected


# ---------------------------------------------------------------------------
# download_results_csv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_clicks", [0, None], ids=["zero", "none"])
def test_download_results_csv_prevents_update_without_a_click(n_clicks):
    """A layout write must not fire an export the user never asked for."""
    with pytest.raises(PreventUpdate):
        download_results_csv(n_clicks, SCOPE_FILTERED, [{"field": "a"}], "abc")


def test_download_results_csv_triggers_export():
    """A click must set the export flag and hand AG Grid the matching params."""
    trigger, params = download_results_csv(1, SCOPE_ALL, [{"field": "a"}], "7e1de513-69ae-44f8")

    assert trigger is True
    assert params["exportedRows"] == "all"
    assert params["columnKeys"] == ["a"]
    assert params["fileName"] == "enzymetk-7e1de5-unfiltered.csv"
