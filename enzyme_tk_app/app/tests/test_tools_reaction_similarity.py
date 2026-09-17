"""Tests for the Reaction Similarity tool — compute, results layout, and callbacks.

Covers ``run()`` (return contract, enzymetk column regression, stat-card
consistency, edge cases), ``_get_column_defs``, ``results_layout``, and
the four modal callbacks (toggle, populate example, validate form,
submit job).
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server  # noqa: F401 — register pages
from enzyme_tk_app.app.tests.conftest import find_components, make_job, offered_databases
from enzyme_tk_app.app.tools.reaction_similarity import TOOL_DEF, SimilarityAlgorithm, get_similarity_algorithms
from enzyme_tk_app.app.tools.reaction_similarity.callbacks import (
    populate_example_reaction,
    submit_reaction_similarity_job,
    toggle_reaction_similarity_modal,
    validate_reaction_form,
)
from enzyme_tk_app.app.tools.reaction_similarity.modal import _get_example_reactions
from enzyme_tk_app.app.tools.reaction_similarity.results import _get_column_defs, results_layout
from enzyme_tk_app.app.utils.columns import COL_RXN_SVG, COL_UNMAPPED_SMILES

SLUG = TOOL_DEF["slug"]

# All similarity column names produced by enzymetk — the core regression signal.
_ALL_SIM_COLUMNS = [a["column"] for a in get_similarity_algorithms()]

# Sample reaction SMILES from the 20-row test CSV for convenience.
_RXN_SMILES_1 = (
    "O.O=P(O)(O)OC[C@H]1O[C@H](O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)"
    "[C@H](O)[C@@H](O)[C@@H]1O>>"
    "O=P(O)(O)O.OC[C@H]1O[C@H](O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)"
    "[C@H](O)[C@@H](O)[C@@H]1O"
)
_RXN_SMILES_2 = "CCCCCC(=O)N[C@H]1CCOC1=O.O>>CCCCCC(=O)N[C@@H](CCO)C(=O)O"
_RXN_SMILES_3 = "CCCC(=O)N[C@H]1CCOC1=O.O>>CCCC(=O)N[C@@H](CCO)C(=O)O"
_RXN_SMILES_4 = "CCCCCC(=O)N[C@@H](CCO)C(=O)O>>CCCCCC(=O)N[C@H]1CCOC1=O.O"
_RXN_SMILES_5 = "CCCCCCCCCC(=O)CC(=O)N[C@H]1CCOC1=O.O>>CCCCCCCCCC(=O)CC(=O)N[C@@H](CCO)C(=O)O"

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def _patch_rxn_data_dir(reactions_dir, monkeypatch):
    """Patch ``REACTIONS_DIR`` so ``run()`` reads the 20-row test fixture."""
    from enzyme_tk_app.app.paths import REACTIONS_DIR  # noqa: PLC0415

    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.reaction_similarity.compute.REACTIONS_DIR",
        reactions_dir / REACTIONS_DIR.name,
    )


def _default_params(**overrides):
    """Return a valid ``run()`` params dict with sensible defaults."""
    defaults = {
        "task_name": "test-run",
        "databases": ["test_reactions_20.csv"],
        "smiles": _RXN_SMILES_1,
        "algorithms": [SimilarityAlgorithm.TANIMOTO.value],
        "top_n": 10,
    }
    defaults.update(overrides)
    return defaults


# ── run() — return contract ──────────────────────────────────────────────────


def test_run_stat_cards_shape(_patch_rxn_data_dir):
    """_stat_cards must be a list of dicts, each with 'label' and 'value'."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    stat_cards = result["_stat_cards"]

    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 4
    for card in stat_cards:
        assert "label" in card
        assert "value" in card


def test_run_dataframe_has_columns_and_data(_patch_rxn_data_dir):
    """The dataframe payload must have 'columns' and 'data' keys."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    df_payload = result["dataframe"]

    assert "columns" in df_payload
    assert "data" in df_payload
    assert isinstance(df_payload["columns"], list)
    assert isinstance(df_payload["data"], list)
    assert len(df_payload["data"]) > 0, "Expected at least one result"


def test_run_result_is_json_serializable(_patch_rxn_data_dir):
    """The entire return dict must be JSON-serializable — backend requirement."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    serialized = json.dumps(result)
    assert isinstance(serialized, str)


def test_run_data_rows_have_consistent_columns(_patch_rxn_data_dir):
    """Every data row must have exactly the same keys as 'columns'."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    columns = set(result["dataframe"]["columns"])

    for i, row in enumerate(result["dataframe"]["data"]):
        assert set(row.keys()) == columns, f"Row {i} keys differ from columns"


# ── run() — enzymetk column regression ───────────────────────────────────────


def test_run_enzymetk_similarity_columns_present(_patch_rxn_data_dir):
    """enzymetk must produce TanimotoSimilarity, CosineSimilarity, RusselSimilarity."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    params = _default_params(algorithms=[a.value for a in SimilarityAlgorithm])
    result = run(params)
    output_columns = result["dataframe"]["columns"]

    for col in _ALL_SIM_COLUMNS:
        assert col in output_columns, f"enzymetk column '{col}' missing from output — possible API change"


def test_run_similarity_scores_are_floats_in_valid_range(_patch_rxn_data_dir):
    """All similarity scores must be floats in [0.0, 1.0]."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    params = _default_params(algorithms=[a.value for a in SimilarityAlgorithm])
    result = run(params)

    for row in result["dataframe"]["data"]:
        for col in _ALL_SIM_COLUMNS:
            score = row[col]
            assert isinstance(score, float), f"Score in '{col}' is {type(score)}, expected float"
            assert 0.0 <= score <= 1.0, f"Score {score} in '{col}' out of [0, 1] range"


def test_run_single_algorithm_only_includes_selected_column(_patch_rxn_data_dir):
    """When only one algorithm is selected, the output still contains that column."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    params = _default_params(algorithms=[SimilarityAlgorithm.COSINE.value])
    result = run(params)
    output_columns = result["dataframe"]["columns"]

    assert SimilarityAlgorithm.COSINE.column in output_columns


def test_run_similarity_scores_rounded_to_4_decimals(_patch_rxn_data_dir):
    """Selected similarity columns should be rounded to at most 4 decimal places."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    params = _default_params(algorithms=[SimilarityAlgorithm.TANIMOTO.value])
    result = run(params)

    for row in result["dataframe"]["data"]:
        score = row[SimilarityAlgorithm.TANIMOTO.column]
        score_str = f"{score:.10f}".rstrip("0")
        if "." in score_str:
            decimal_part = score_str.split(".")[1]
            assert len(decimal_part) <= 4, f"Score {score} has {len(decimal_part)} decimal places, expected <= 4"


# ── run() — output quality ───────────────────────────────────────────────────


def test_run_reaction_svg_column_present(_patch_rxn_data_dir):
    """Each result row must have a reaction_svg column with a valid data URI."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    assert COL_RXN_SVG in output_columns, "reaction_svg column missing from output"

    for row in result["dataframe"]["data"]:
        svg = row[COL_RXN_SVG]
        assert isinstance(svg, str), "SVG data URI should be a string"
        assert svg.startswith("data:image/svg+xml;base64,"), f"SVG data URI has unexpected prefix: {svg[:40]}..."


def test_run_unmapped_smiles_column_present(_patch_rxn_data_dir):
    """Each result row must include the unmapped reaction SMILES."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    assert COL_UNMAPPED_SMILES in output_columns, "unmapped column missing from output"


# ── run() — top_n and sorting ────────────────────────────────────────────────


@pytest.mark.parametrize("top_n", [1, 3, 5, 20], ids=["top-1", "top-3", "top-5", "top-20"])
def test_run_respects_top_n(top_n, _patch_rxn_data_dir):
    """The number of result rows must not exceed the requested top_n."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params(top_n=top_n))
    assert len(result["dataframe"]["data"]) <= top_n


def test_run_results_sorted_by_primary_algorithm_descending(_patch_rxn_data_dir):
    """Results must be sorted by the primary algorithm score descending (best first)."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params(top_n=20))
    data = result["dataframe"]["data"]
    col = SimilarityAlgorithm.TANIMOTO.column

    if len(data) >= 2:
        scores = [row[col] for row in data]
        assert scores == sorted(scores, reverse=True), "Results not sorted by primary algorithm descending"


# ── run() — stat card consistency ────────────────────────────────────────────


def test_run_stat_cards_consistency(_patch_rxn_data_dir):
    """Stat cards must have consistent values: row count, positive scanned, and valid run time."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    actual_rows = len(result["dataframe"]["data"])

    assert stat_cards["Results Returned"] == str(actual_rows)
    assert int(stat_cards["Reactions Scanned"].replace(",", "")) > 0
    run_time = stat_cards["Run Time"]
    assert run_time.endswith("s")
    float(run_time[:-1])  # raises ValueError if not numeric
    assert stat_cards["Databases Searched"] == "1/1"


# ── run() — score regression ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "algo",
    [SimilarityAlgorithm.TANIMOTO, SimilarityAlgorithm.COSINE],
    ids=["tanimoto", "cosine"],
)
def test_run_self_search_returns_score_1(algo, _patch_rxn_data_dir):
    """Querying a reaction SMILES present in the DB must return a perfect 1.0 self-match."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params(smiles=_RXN_SMILES_1, algorithms=[algo.value], top_n=1))
    top_score = result["dataframe"]["data"][0][algo.column]

    assert top_score == 1.0, f"Expected self-match score 1.0 for {algo.column}, got {top_score}"


@pytest.mark.parametrize(
    ("query_smiles", "expected_tanimoto", "expected_cosine"),
    [
        (_RXN_SMILES_1, [1.0, 0.5098, 0.5018], [1.0, 0.6849, 0.6777]),
        (_RXN_SMILES_2, [1.0, 0.6667, 0.6111], [1.0, 0.8, 0.765]),
        (_RXN_SMILES_3, [1.0, 0.6111, 0.4545], [1.0, 0.765, 0.6563]),
        (_RXN_SMILES_4, [1.0, 0.6667, 0.4799], [1.0, 0.8, 0.6598]),
        (_RXN_SMILES_5, [1.0, 0.6836, 0.4507], [1.0, 0.8184, 0.6516]),
    ],
    ids=["rxn-1", "rxn-2", "rxn-3", "rxn-4", "rxn-5"],
)
def test_run_known_query_top_scores_regression(query_smiles, expected_tanimoto, expected_cosine, _patch_rxn_data_dir):
    """Pin exact top-3 scores for known queries to catch enzymetk changes."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(
        _default_params(
            smiles=query_smiles,
            algorithms=[a.value for a in SimilarityAlgorithm],
            top_n=3,
        )
    )
    data = result["dataframe"]["data"]
    tanimoto_col = SimilarityAlgorithm.TANIMOTO.column
    cosine_col = SimilarityAlgorithm.COSINE.column

    actual_tanimoto = [row[tanimoto_col] for row in data]
    actual_cosine = [row[cosine_col] for row in data]

    assert actual_tanimoto == expected_tanimoto, (
        f"Tanimoto regression: expected {expected_tanimoto}, got {actual_tanimoto}"
    )
    assert actual_cosine == expected_cosine, f"Cosine regression: expected {expected_cosine}, got {actual_cosine}"


# ── run() — edge cases ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "databases",
    [
        ["nonexistent_database.csv"],
        ["../../etc/passwd.csv"],
        [],
    ],
    ids=["nonexistent-file", "path-traversal", "empty-list"],
)
def test_run_invalid_databases_raise(databases, _patch_rxn_data_dir):
    """Invalid or missing database inputs must raise, not return an empty grid.

    An empty result would be indistinguishable from a legitimate
    "no similar reactions found".
    """
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    with pytest.raises(ValueError, match="database"):
        run(_default_params(databases=databases))


@pytest.mark.parametrize(
    "smiles",
    ["", "XYZ>>CCO", "CCO", ">>", "CCO>>"],
    ids=["empty", "unparseable-substrate", "no-arrow", "arrow-only", "no-product"],
)
def test_run_refuses_a_bad_reaction_before_it_opens_a_database(smiles, _patch_rxn_data_dir):
    """A replayed job never touches the modal, so ``run()`` re-checks the query.

    Without this, ``ReactionDist`` reads the last three as SMARTS and returns a
    grid of scores against a degenerate fingerprint — a job that says SUCCESS
    and means nothing.
    """
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    with pytest.raises(ValueError):
        run(_default_params(smiles=smiles))


def test_run_non_csv_databases_raise(_patch_rxn_data_dir):
    """Every selection being non-.csv is a total wipeout, so it must raise."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    # Named by its filename, like every other database the user sees.
    with pytest.raises(ValueError, match="bad1.txt"):
        run(_default_params(databases=["bad1.txt", "bad2.exe"]))


def test_run_partial_database_failure_is_skipped_not_fatal(_patch_rxn_data_dir):
    """A bad database alongside a good one is skipped and named, not fatal."""
    from enzyme_tk_app.app.tools.reaction_similarity.compute import run

    result = run(_default_params(databases=["test_reactions_20.csv", "bad.txt"]))
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    assert stat_cards["Databases Searched"] == "1/2"
    # Skipped names keep their extension, matching the dropdown and the grid.
    assert stat_cards["Databases Skipped"] == "bad.txt"


# ── Column definitions ───────────────────────────────────────────────────────


def test_get_column_defs_fields_are_unique_and_svg_first():
    """_get_column_defs must start with the reaction SVG column and have no duplicate fields."""
    col_defs = _get_column_defs()

    assert isinstance(col_defs, list)
    assert len(col_defs) > 0

    # First column must be the tool-specific reaction SVG
    assert col_defs[0]["field"] == COL_RXN_SVG
    assert col_defs[0]["autoHeight"] is True

    # All field names must be unique
    fields = [cd["field"] for cd in col_defs]
    assert len(fields) == len(set(fields)), f"Duplicate fields: {[f for f in fields if fields.count(f) > 1]}"


# ── Results layout ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "result_dict",
    [
        None,
        {},
        {"dataframe": None},
        {"dataframe": {}},
        {"dataframe": {"columns": ["a"], "data": []}},
    ],
    ids=["none-result", "empty-dict", "null-dataframe", "missing-keys", "empty-data"],
)
def test_results_layout_empty_states(result_dict):
    """results_layout must show a 'no results' message for missing or empty data."""
    job = make_job(result=result_dict)
    layout = results_layout(job)

    assert isinstance(layout, html.Div)
    paragraphs = find_components(layout, html.P)
    assert any("No similar reactions" in (p.children or "") for p in paragraphs)


def test_results_layout_renders_ag_grid_with_data():
    """results_layout must produce an AgGrid when valid data is present."""
    import dash_ag_grid as dag

    job = make_job(
        result={
            "dataframe": {
                "columns": [COL_RXN_SVG, "score"],
                "data": [
                    {COL_RXN_SVG: "<svg/>", "score": 0.95},
                    {COL_RXN_SVG: "<svg/>", "score": 0.80},
                ],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)
    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AgGrid in results_layout"
    assert len(grids[0].rowData) == 2


# ── Toggle modal ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("triggered_id", "expected"),
    [
        (f"id-btn-launch-{SLUG}", True),
        (f"id-btn-{SLUG}-cancel", False),
    ],
    ids=["launch-opens", "cancel-closes"],
)
def test_toggle_reaction_similarity_modal(triggered_id, expected):
    """The modal must open on launch and close on cancel."""
    with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = triggered_id
        result = toggle_reaction_similarity_modal(1, 1)

    assert result is expected


# ── Populate example ─────────────────────────────────────────────────────────


def test_populate_example_reaction_returns_value():
    """Selecting a shipped example populates the SMILES textarea and the Task Name."""
    example = _get_example_reactions()[0]

    smiles, task_name = populate_example_reaction(example["value"])

    assert smiles == example["value"]
    assert task_name == "lactone-hydrolysis"


def test_populate_example_reaction_leaves_task_name_for_unknown_smiles():
    """A SMILES that is not a shipped example fills the textarea but not the Task Name."""
    smiles, task_name = populate_example_reaction("A.B>>C.D")

    assert smiles == "A.B>>C.D"
    assert task_name is no_update


@pytest.mark.parametrize("empty_value", [None, "", 0], ids=["none", "empty-string", "zero"])
def test_populate_example_reaction_raises_prevent_update(empty_value):
    """Falsy example values must raise PreventUpdate."""
    with pytest.raises(PreventUpdate):
        populate_example_reaction(empty_value)


# ── Validate form ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("task_name", "smiles", "databases", "algorithms", "expected_disabled", "expected_invalid"),
    [
        ("My Task", _RXN_SMILES_3, ["db.csv"], ["tanimoto"], False, False),
        ("", _RXN_SMILES_3, ["db.csv"], ["tanimoto"], True, False),
        ("My Task", "", ["db.csv"], ["tanimoto"], True, False),
        ("My Task", _RXN_SMILES_3, [], ["tanimoto"], True, False),
        ("My Task", _RXN_SMILES_3, ["db.csv"], [], True, False),
        ("   ", "   ", ["db.csv"], ["tanimoto"], True, False),
        (None, None, None, None, True, False),
        # An unusable structure disables Run *and* marks the field, which an
        # absent one deliberately does not — a blank form is not yet a mistake.
        ("My Task", "XYZ>>CCO", ["db.csv"], ["tanimoto"], True, True),
        ("My Task", "CCO", ["db.csv"], ["tanimoto"], True, True),
        # enzymetk reads the query as SMARTS and scores every row against this
        # one happily, so nothing downstream would have caught it.
        ("My Task", ">>", ["db.csv"], ["tanimoto"], True, True),
    ],
    ids=[
        "all-valid",
        "missing-name",
        "missing-smiles",
        "no-databases",
        "no-algorithms",
        "whitespace-only",
        "all-none",
        "unparseable-substrate",
        "no-arrow",
        "arrow-only",
    ],
)
def test_validate_reaction_form(task_name, smiles, databases, algorithms, expected_disabled, expected_invalid):
    """Run must be disabled unless the form is complete *and* the reaction parses."""
    disabled, invalid, message = validate_reaction_form(task_name, smiles, databases, algorithms)

    assert disabled is expected_disabled
    assert invalid is expected_invalid
    # The message and the red border go together: a marked field always says why.
    assert bool(message) is expected_invalid


# ── Submit job ───────────────────────────────────────────────────────────────


def test_submit_clears_results_on_launch():
    """Re-opening the modal must return empty string without calling the scheduler."""
    with (
        patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx,
        patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.get_task_scheduler") as mock_sched,
    ):
        mock_ctx.triggered_id = f"id-btn-launch-{SLUG}"
        result = submit_reaction_similarity_job(0, 1, "t", ["db.csv"], _RXN_SMILES_3, ["tanimoto"], 10, None)

    assert result == ""
    mock_sched.assert_not_called()


@pytest.mark.parametrize(
    "smiles",
    ["", "   ", "XYZ>>CCO", "CCO", ">>", "CCO>>"],
    ids=["empty", "whitespace-only", "unparseable-substrate", "no-arrow", "arrow-only", "no-product"],
)
def test_submit_returns_error_when_smiles_invalid(smiles):
    """A bad reaction must be reported in the modal, not handed to the scheduler.

    The disabled Run button is client-side only, so this is the check that
    actually stops a crafted request — and the last four of these would
    otherwise run to completion, scored against a degenerate fingerprint.
    """
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.reaction_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{SLUG}-submit"
        result = submit_reaction_similarity_job(1, 0, "My Task", ["db.csv"], smiles, ["tanimoto"], 10, None)

    assert isinstance(result, str) and result.strip(), "Expected a non-empty error message string"
    mock_scheduler.submit_job.assert_not_called()


def test_submit_returns_error_when_top_n_invalid():
    """An invalid Top N must return an error without scheduling a job."""
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.reaction_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{SLUG}-submit"
        result = submit_reaction_similarity_job(1, 0, "My Task", ["db.csv"], _RXN_SMILES_3, ["tanimoto"], None, None)

    assert isinstance(result, str) and len(result) > 0, "Expected a non-empty error message string"
    mock_scheduler.submit_job.assert_not_called()


def test_submit_returns_job_id():
    """A valid submission must return a message containing the job ID."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-rxn-123"

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-1"
        with (
            patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.reaction_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
            patch(
                "enzyme_tk_app.app.tools.reaction_similarity.callbacks.get_reaction_database_options",
                return_value=offered_databases("db1.csv", "db2.csv"),
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{SLUG}-submit"
            result = submit_reaction_similarity_job(
                1, 0, "  Glucose search  ", ["db1.csv", "db2.csv"], f"  {_RXN_SMILES_3}  ", ["tanimoto"], 10, None
            )

    assert "job-rxn-123" in result
    # Verify the scheduler was called with stripped values
    call_kwargs = mock_scheduler.submit_job.call_args.kwargs
    assert call_kwargs["params"]["task_name"] == "Glucose search"
    assert call_kwargs["params"]["smiles"] == _RXN_SMILES_3
