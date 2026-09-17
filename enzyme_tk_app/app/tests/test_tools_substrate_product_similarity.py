"""Tests for the Substrate/Product Similarity tool compute module.

These tests exercise ``_expand_reactions()`` and ``run()`` with **real**
enzymetk and rdkit calls — no mocking.  The goal is regression detection:
if enzymetk changes its output column names, score types, or API, these
tests will fail immediately.

A small 20-row CSV (``test_reactions_20.csv``) extracted from the
production reactions database is used as the test fixture.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from dash import html
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.app import server
from enzyme_tk_app.app.tests.conftest import find_components, make_job, make_reaction_df, offered_databases
from enzyme_tk_app.app.tools.substrate_product_similarity import (
    TOOL_DEF,
    MoleculeRole,
    SimilarityAlgorithm,
    get_similarity_algorithms,
)
from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
    submit_substrate_product_similarity_job,
    validate_substrate_product_form,
)
from enzyme_tk_app.app.tools.substrate_product_similarity.compute import (
    _ROW_ID,
    _expand_reactions,
    run,
)
from enzyme_tk_app.app.utils.columns import (
    COL_MOL_INDEX,
    COL_MOL_SMILES,
    COL_MOL_SVG,
)

# ── Shared helpers ────────────────────────────────────────────────────────────

# All similarity column names produced by enzymetk — the core regression signal.
_ALL_SIM_COLUMNS = [a["column"] for a in get_similarity_algorithms()]

# A real, parseable molecule for the callback tests — the form validates the
# structure now, so a placeholder like "A" would be rejected on its own merits.
_GLUCOSE_SMILES = "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"


def _default_params(**overrides):
    """Return a valid ``run()`` params dict with sensible defaults.

    Override any key by passing it as a keyword argument.
    """
    defaults = {
        "task_name": "test-run",
        "databases": ["test_reactions_20.csv"],
        "smiles": "O",
        "algorithms": [SimilarityAlgorithm.TANIMOTO.value],
        "top_n": 10,
        "role": MoleculeRole.SUBSTRATE.value,
    }
    defaults.update(overrides)
    return defaults


# ── _expand_reactions() ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reaction", "role", "expected_smiles"),
    [
        ("A.B>>C", MoleculeRole.SUBSTRATE, ["A", "B"]),
        ("A.B>>C.D", MoleculeRole.PRODUCT, ["C", "D"]),
    ],
    ids=["substrate-side", "product-side"],
)
def test_expand_reactions_by_role(reaction, role, expected_smiles):
    """Expanding a reaction splits the selected side on '.' to yield one row per molecule."""
    df = make_reaction_df([reaction])
    result = _expand_reactions(df, role)

    assert len(result) == len(expected_smiles)
    assert list(result[COL_MOL_SMILES]) == expected_smiles
    # molecule_index should be sequential (position within the molecule list)
    assert list(result[COL_MOL_INDEX]) == list(range(len(expected_smiles)))


def test_expand_reactions_preserves_metadata():
    """Original columns are carried through to every expanded row."""
    df = make_reaction_df(["X.Y>>Z"])
    df["ec_num"] = "1.2.3.4"
    result = _expand_reactions(df, MoleculeRole.SUBSTRATE)

    # Both expanded rows should carry the original ec_num value
    assert all(result["ec_num"] == "1.2.3.4")


@pytest.mark.parametrize(
    ("reaction", "role"),
    [
        ("INVALID_NO_ARROW", MoleculeRole.SUBSTRATE),
        ("A.B>>", MoleculeRole.PRODUCT),
    ],
    ids=["malformed-no-arrow", "empty-product-side"],
)
def test_expand_reactions_empty_result(reaction, role):
    """Edge-case reactions (malformed or empty side) produce no rows."""
    df = make_reaction_df([reaction])
    result = _expand_reactions(df, role)

    assert result.empty, f"Expected no rows for reaction={reaction!r}, role={role!r}"


def test_expand_reactions_multiple_reactions():
    """Multiple reactions expand independently, molecule_index resets per reaction."""
    df = make_reaction_df(["A.B>>C", "D.E.F>>G"])
    result = _expand_reactions(df, MoleculeRole.SUBSTRATE)

    # 2 molecules from first reaction + 3 from second = 5 total
    assert len(result) == 5

    # molecule_index resets for each (id, unmapped) group
    first_rxn = result[result["id"] == 0]
    second_rxn = result[result["id"] == 1]
    assert list(first_rxn[COL_MOL_INDEX]) == [0, 1]
    assert list(second_rxn[COL_MOL_INDEX]) == [0, 1, 2]


# ── run() — return contract ──────────────────────────────────────────────────


def test_run_returns_expected_top_level_keys(_patch_reactions_dir):
    """run() must return _stat_cards and dataframe at the top level."""
    result = run(_default_params())

    assert "_stat_cards" in result, "Result must contain '_stat_cards'"
    assert "dataframe" in result, "Result must contain 'dataframe'"


def test_run_stat_cards_shape(_patch_reactions_dir):
    """_stat_cards must be a list of dicts, each with 'label' and 'value'."""
    result = run(_default_params())
    stat_cards = result["_stat_cards"]

    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 4, "Expected at least 4 stat cards"
    for card in stat_cards:
        assert "label" in card, f"Stat card missing 'label': {card}"
        assert "value" in card, f"Stat card missing 'value': {card}"


def test_run_dataframe_has_columns_and_data(_patch_reactions_dir):
    """The dataframe payload must have 'columns' and 'data' keys."""
    result = run(_default_params())
    df_payload = result["dataframe"]

    assert "columns" in df_payload
    assert "data" in df_payload
    assert isinstance(df_payload["columns"], list)
    assert isinstance(df_payload["data"], list)


def test_run_result_is_json_serializable(_patch_reactions_dir):
    """The entire return dict must be JSON-serializable — backend requirement.

    Large results are offloaded to disk as JSON; non-serializable objects
    (e.g. numpy arrays, bare datetimes) would break the pipeline silently.
    """
    result = run(_default_params())

    # json.dumps will raise TypeError for non-serializable values.
    serialized = json.dumps(result)
    assert isinstance(serialized, str)


# ── run() — enzymetk column regression ───────────────────────────────────────


def test_run_enzymetk_similarity_columns_present(_patch_reactions_dir):
    """enzymetk must produce TanimotoSimilarity, CosineSimilarity, RusselSimilarity.

    This is the core regression signal — if enzymetk renames any of these
    columns, this test fails immediately.
    """
    # Request all three algorithms so all columns appear in output
    params = _default_params(algorithms=[a.value for a in SimilarityAlgorithm])
    result = run(params)
    output_columns = result["dataframe"]["columns"]

    for col in _ALL_SIM_COLUMNS:
        assert col in output_columns, f"enzymetk column '{col}' missing from output — possible API change"


def test_run_similarity_scores_are_floats_in_valid_range(_patch_reactions_dir):
    """All similarity scores must be floats in [0.0, 1.0]."""
    params = _default_params(algorithms=[a.value for a in SimilarityAlgorithm])
    result = run(params)

    for row in result["dataframe"]["data"]:
        for col in _ALL_SIM_COLUMNS:
            score = row[col]
            assert isinstance(score, float), f"Score in '{col}' is {type(score)}, expected float"
            assert 0.0 <= score <= 1.0, f"Score {score} in '{col}' out of [0, 1] range"


def test_run_single_algorithm_only_includes_selected_column(_patch_reactions_dir):
    """When only one algorithm is selected, the output still contains that column."""
    params = _default_params(algorithms=[SimilarityAlgorithm.COSINE.value])
    result = run(params)
    output_columns = result["dataframe"]["columns"]

    assert SimilarityAlgorithm.COSINE.column in output_columns


# ── run() — output quality ───────────────────────────────────────────────────


def test_run_internal_row_id_not_in_output(_patch_reactions_dir):
    """The internal _row_id join key must be dropped from the final output."""
    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    assert _ROW_ID not in output_columns, f"Internal column '{_ROW_ID}' leaked into output"


def test_run_molecule_svg_column_present(_patch_reactions_dir):
    """Each result row must have a molecule_svg column with a valid data URI."""
    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    assert COL_MOL_SVG in output_columns, "molecule_svg column missing from output"

    # Check that SVG data URIs are base64-encoded SVGs
    for row in result["dataframe"]["data"]:
        svg = row[COL_MOL_SVG]
        assert isinstance(svg, str), "SVG data URI should be a string"
        assert svg.startswith("data:image/svg+xml;base64,"), f"SVG data URI has unexpected prefix: {svg[:40]}..."


def test_run_database_column_derived_from_filename(_patch_reactions_dir):
    """Each result row must carry a 'database' column derived from the CSV filename."""
    result = run(_default_params())

    for row in result["dataframe"]["data"]:
        assert "database" in row, "Missing 'database' column in result row"
        # Named exactly as the file is named in data/reactions/ — not prettified
        # and not stripped, so the value matches the dropdown label and the file
        # on disk.
        assert row["database"] == "test_reactions_20.csv"


def test_run_similarity_scores_rounded_to_4_decimals(_patch_reactions_dir):
    """Selected similarity columns should be rounded to at most 4 decimal places."""
    params = _default_params(algorithms=[SimilarityAlgorithm.TANIMOTO.value])
    result = run(params)

    for row in result["dataframe"]["data"]:
        score = row[SimilarityAlgorithm.TANIMOTO.column]
        # Convert to string and check decimal places
        score_str = f"{score:.10f}".rstrip("0")
        if "." in score_str:
            decimal_part = score_str.split(".")[1]
            assert len(decimal_part) <= 4, f"Score {score} has {len(decimal_part)} decimal places, expected <= 4"


def test_run_respects_top_n(_patch_reactions_dir):
    """The number of result rows must not exceed the requested top_n."""
    params = _default_params(top_n=3)
    result = run(params)

    assert len(result["dataframe"]["data"]) <= 3


def test_run_molecule_smiles_column_present(_patch_reactions_dir):
    """Each result row must include the individual molecule SMILES."""
    result = run(_default_params())
    output_columns = result["dataframe"]["columns"]

    assert COL_MOL_SMILES in output_columns, "molecule_smiles column missing from output"


# ── run() — stat card consistency ────────────────────────────────────────────


def test_run_stat_card_databases_searched_matches_input(_patch_reactions_dir):
    """The 'Databases Searched' stat card must match len(databases)."""
    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    assert stat_cards["Databases Searched"] == "1/1"


def test_run_stat_card_results_returned_matches_data(_patch_reactions_dir):
    """The 'Results Returned' stat card must match the actual row count."""
    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    actual_rows = len(result["dataframe"]["data"])

    assert stat_cards["Results Returned"] == str(actual_rows)


def test_run_stat_card_run_time_is_numeric(_patch_reactions_dir):
    """The 'Run Time' stat card must be a numeric value followed by 's'."""
    result = run(_default_params())
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}

    run_time = stat_cards["Run Time"]
    assert run_time.endswith("s"), f"Run time '{run_time}' should end with 's'"
    # The numeric part should be parseable as a float
    float(run_time[:-1])  # raises ValueError if not numeric


# ── run() — product role ─────────────────────────────────────────────────────


def test_run_product_role(_patch_reactions_dir):
    """run() with role='product' should search against product side molecules."""
    params = _default_params(role="product")
    result = run(params)

    # Should still return valid structure — the test CSV has products on the
    # right side of >> in every reaction.
    assert "dataframe" in result
    assert "_stat_cards" in result
    assert len(result["dataframe"]["data"]) > 0, "Expected results for product role search"


def test_run_invalid_role_raises_value_error(_patch_reactions_dir):
    """run() must reject an invalid role string with a ValueError."""
    params = _default_params(role="invalid")
    with pytest.raises(ValueError, match="not a valid MoleculeRole"):
        run(params)


def test_expand_reactions_invalid_role_raises_value_error():
    """_expand_reactions() must reject a non-MoleculeRole value."""
    df = make_reaction_df(["A.B>>C"])
    with pytest.raises(ValueError, match="role must be a MoleculeRole member"):
        _expand_reactions(df, "invalid")


def test_run_invalid_algorithm_raises_value_error(_patch_reactions_dir):
    """run() must reject an invalid algorithm string with a ValueError."""
    params = _default_params(algorithms=["bogus"])
    with pytest.raises(ValueError, match="not a valid SimilarityAlgorithm"):
        run(params)


# ── run() — edge cases ───────────────────────────────────────────────────────


def test_run_nonexistent_database_raises(_patch_reactions_dir):
    """A missing CSV is the only selection, so it is a total wipeout and must raise.

    Returning an empty grid would be indistinguishable from a legitimate
    "no similar molecules found".
    """
    params = _default_params(databases=["nonexistent_database.csv"])

    with pytest.raises(ValueError, match="None of the selected databases"):
        run(params)


def test_run_data_rows_have_consistent_columns(_patch_reactions_dir):
    """Every data row must have exactly the same keys as the 'columns' list."""
    result = run(_default_params())
    columns = set(result["dataframe"]["columns"])

    for i, row in enumerate(result["dataframe"]["data"]):
        assert set(row.keys()) == columns, f"Row {i} keys {set(row.keys())} differ from columns {columns}"


def test_run_empty_algorithms_raises_value_error(_patch_reactions_dir):
    """run() must reject an empty algorithms list with a ValueError."""
    params = _default_params(algorithms=[])
    with pytest.raises(ValueError, match="At least one similarity algorithm must be selected"):
        run(params)


def test_run_non_csv_database_raises_when_it_is_the_only_selection(_patch_reactions_dir):
    """A non-.csv filename is skipped; being the only selection makes that fatal."""
    params = _default_params(databases=["not_a_csv.txt"])

    # Named by its filename, like every other database the user sees.
    with pytest.raises(ValueError, match="not_a_csv.txt"):
        run(params)


def test_run_skipped_databases_stat_card_in_success_path(_patch_reactions_dir):
    """When some databases are skipped but others produce results, the stat card appears."""
    params = _default_params(databases=["test_reactions_20.csv", "bad.txt"])
    result = run(params)

    # Valid database should still produce results
    assert len(result["dataframe"]["data"]) > 0
    stat_cards = {c["label"]: c["value"] for c in result["_stat_cards"]}
    assert stat_cards["Databases Searched"] == "1/2"
    # Skipped names keep their extension, matching the dropdown and the grid.
    assert stat_cards["Databases Skipped"] == "bad.txt"


# ── run() — exact molecule match (score = 1.0) ──────────────────────────────
# Uses the ``csv_molecules`` fixture to iterate over real molecules
# extracted from the test CSV.  When a molecule is used as the query
# against the side it belongs to, the self-vs-self fingerprint
# comparison MUST yield a similarity score of exactly 1.0.


@pytest.mark.parametrize(
    ("algorithm", "score_column"),
    [
        (SimilarityAlgorithm.TANIMOTO.value, SimilarityAlgorithm.TANIMOTO.column),
        (SimilarityAlgorithm.COSINE.value, SimilarityAlgorithm.COSINE.column),
    ],
    ids=["tanimoto", "cosine"],
)
def test_run_exact_substrate_returns_score_1(_patch_reactions_dir, csv_molecules, algorithm, score_column):
    """Every substrate from the CSV must have a top-result score of 1.0.

    Iterates over the non-trivial substrates extracted by the
    ``csv_molecules`` fixture and asserts that the top-ranked result
    has a perfect similarity score.  The SMILES string of the top
    result is *not* checked because Morgan fingerprints are folded
    into a fixed-length bit vector, so structurally similar molecules
    (e.g. xylobiose vs xylotetraose) can share identical fingerprints
    and tie at 1.0, and RDKit may also canonicalise the SMILES
    differently from the raw CSV form.
    """
    for smiles in csv_molecules["substrates"]:
        params = _default_params(smiles=smiles, role="substrate", algorithms=[algorithm], top_n=20)
        result = run(params)

        top_score = result["dataframe"]["data"][0][score_column]
        assert top_score == 1.0, (
            f"Top result {score_column} for exact substrate query {smiles!r} should be 1.0, got {top_score}"
        )


@pytest.mark.parametrize(
    ("algorithm", "score_column"),
    [
        (SimilarityAlgorithm.TANIMOTO.value, SimilarityAlgorithm.TANIMOTO.column),
        (SimilarityAlgorithm.COSINE.value, SimilarityAlgorithm.COSINE.column),
    ],
    ids=["tanimoto", "cosine"],
)
def test_run_exact_product_returns_score_1(_patch_reactions_dir, csv_molecules, algorithm, score_column):
    """Every product from the CSV must have a top-result score of 1.0.

    See the substrate counterpart for why the SMILES string is not checked.
    """
    for smiles in csv_molecules["products"]:
        params = _default_params(smiles=smiles, role="product", algorithms=[algorithm], top_n=20)
        result = run(params)

        top_score = result["dataframe"]["data"][0][score_column]
        assert top_score == 1.0, (
            f"Top result {score_column} for exact product query {smiles!r} should be 1.0, got {top_score}"
        )


# ── run() — pinned score regression ──────────────────────────────────────────


def test_run_known_scores(_patch_reactions_dir, csv_molecules_known_scores):
    """Similarity scores for known query molecules must match pinned values.

    Guards against silent changes in enzymetk's fingerprint calculation
    or RDKit version upgrades that alter Morgan fingerprint bit-sets.
    All three algorithms (Tanimoto, Cosine, Russell) are requested in a
    single ``run()`` call and checked against hardcoded expected scores.
    """
    for case in csv_molecules_known_scores:
        params = _default_params(
            smiles=case["query"],
            role=case["role"],
            algorithms=[a.value for a in SimilarityAlgorithm],
            top_n=20,
        )
        result = run(params)
        top_row = result["dataframe"]["data"][0]

        assert top_row[SimilarityAlgorithm.TANIMOTO.column] == case["expected_tanimoto"], (
            f"Tanimoto mismatch for query {case['query']!r}: "
            f"expected {case['expected_tanimoto']}, got {top_row[SimilarityAlgorithm.TANIMOTO.column]}"
        )
        assert top_row[SimilarityAlgorithm.COSINE.column] == case["expected_cosine"], (
            f"Cosine mismatch for query {case['query']!r}: "
            f"expected {case['expected_cosine']}, got {top_row[SimilarityAlgorithm.COSINE.column]}"
        )
        assert top_row[SimilarityAlgorithm.RUSSELL.column] == case["expected_russell"], (
            f"Russell mismatch for query {case['query']!r}: "
            f"expected {case['expected_russell']}, got {top_row[SimilarityAlgorithm.RUSSELL.column]}"
        )

        if case["expected_top_smiles"] is not None:
            assert top_row[COL_MOL_SMILES] == case["expected_top_smiles"], (
                f"Top result SMILES mismatch for query {case['query']!r}: "
                f"expected {case['expected_top_smiles']!r}, got {top_row[COL_MOL_SMILES]!r}"
            )


# ---------------------------------------------------------------------------
# Substrate/Product Similarity callbacks
# ---------------------------------------------------------------------------


def test_subprod_toggle_modal_opens_on_launch_click():
    """The substrate/product modal must open when the launch button is clicked."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
        toggle_substrate_product_similarity_modal,
    )

    with patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-launch-substrate-product-similarity"
        result = toggle_substrate_product_similarity_modal(1, 0)

    assert result is True


def test_subprod_toggle_modal_closes_on_cancel_click():
    """The substrate/product modal must close when the cancel button is clicked."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
        toggle_substrate_product_similarity_modal,
    )

    with patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-substrate-product-similarity-cancel"
        result = toggle_substrate_product_similarity_modal(0, 1)

    assert result is False


def test_subprod_populate_example_sets_smiles_and_role():
    """Selecting an example must populate the SMILES field, the role selector and the Task Name."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    # Encoded as "role||smiles"
    smiles, role, task_name = populate_example_smiles("substrate||OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O")

    assert smiles == "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"
    assert role == "substrate"
    assert task_name == "glucose"


def test_subprod_populate_example_sets_product_role():
    """A product example must set the role to 'product'."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    smiles, role, task_name = populate_example_smiles("product||CCO")

    assert smiles == "CCO"
    assert role == "product"
    assert task_name == "ethanol"


def test_subprod_populate_example_leaves_task_name_for_unknown_smiles():
    """A SMILES that is not a shipped example fills the form but not the Task Name."""
    from dash import no_update

    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    smiles, role, task_name = populate_example_smiles("substrate||C1=CC=CC=C1")

    assert smiles == "C1=CC=CC=C1"
    assert role == "substrate"
    assert task_name is no_update


def test_subprod_populate_example_returns_defaults_for_none():
    """Clearing the example dropdown must raise PreventUpdate."""
    from dash.exceptions import PreventUpdate

    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    with pytest.raises(PreventUpdate):
        populate_example_smiles(None)


def test_subprod_populate_example_returns_defaults_for_invalid_value():
    """A value without the '||' separator must raise PreventUpdate."""
    from dash.exceptions import PreventUpdate

    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    with pytest.raises(PreventUpdate):
        populate_example_smiles("no-separator-here")


@pytest.mark.parametrize(
    ("task_name", "smiles", "databases", "algorithms", "expected_disabled", "expected_invalid"),
    [
        ("Glucose search", _GLUCOSE_SMILES, ["db.csv"], ["tanimoto"], False, False),
        ("", "", ["db.csv"], ["tanimoto"], True, False),
        (None, None, ["db.csv"], ["tanimoto"], True, False),
        ("", "CCO", ["db.csv"], ["tanimoto"], True, False),
        ("My Query", "", ["db.csv"], ["tanimoto"], True, False),
        ("   ", "   ", ["db.csv"], ["tanimoto"], True, False),
        ("My Query", _GLUCOSE_SMILES, [], ["tanimoto"], True, False),
        ("My Query", _GLUCOSE_SMILES, ["db.csv"], [], True, False),
        # An unusable structure disables Run *and* marks the field, which an
        # absent one deliberately does not — a blank form is not yet a mistake.
        ("My Query", "XYZ", ["db.csv"], ["tanimoto"], True, True),
        # This field takes one molecule; a reaction pasted in is its own mistake.
        ("My Query", "CCO>>CC=O", ["db.csv"], ["tanimoto"], True, True),
    ],
    ids=[
        "all-valid",
        "both-empty",
        "both-none",
        "missing-name",
        "missing-smiles",
        "whitespace-only",
        "no-databases",
        "no-algorithms",
        "unparseable-molecule",
        "reaction-in-a-molecule-field",
    ],
)
def test_subprod_validate_form(task_name, smiles, databases, algorithms, expected_disabled, expected_invalid):
    """Run must be disabled unless the form is complete *and* the molecule parses."""
    disabled, invalid, message = validate_substrate_product_form(task_name, smiles, databases, algorithms)

    assert disabled is expected_disabled
    assert invalid is expected_invalid
    # The message and the red border go together: a marked field always says why.
    assert bool(message) is expected_invalid


@pytest.mark.parametrize(
    "smiles",
    ["", "   ", "XYZ", "c1ccccc", "CCO>>CC=O"],
    ids=["empty", "whitespace-only", "unparseable", "unclosed-ring", "reaction-in-a-molecule-field"],
)
def test_subprod_submit_returns_error_when_smiles_invalid(smiles):
    """A bad molecule must be reported in the modal, not handed to the scheduler.

    The disabled Run button is client-side only, so this is the check that
    actually stops a crafted request — and without it the string reaches
    ``mfpgen.GetFingerprint(None)`` inside ``SubstrateDist``, which raises a C++
    signature dump the user then meets as a traceback on the My Tasks page.
    """
    mock_scheduler = MagicMock()
    slug = TOOL_DEF["slug"]
    with (
        patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{slug}-submit"
        result = submit_substrate_product_similarity_job(
            1, 0, "My Query", ["db.csv"], smiles, ["tanimoto"], 10, "substrate", None
        )

    assert isinstance(result, str) and result.strip(), "Expected a non-empty error message string"
    mock_scheduler.submit_job.assert_not_called()


# ── Results layout ───────────────────────────────────────────────────────────


def test_subprod_get_column_defs_fields_are_unique():
    """_get_column_defs must return unique field names with required keys."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.results import _get_column_defs

    col_defs = _get_column_defs()

    assert isinstance(col_defs, list)
    assert len(col_defs) > 0, "Expected at least one column definition"

    for cd in col_defs:
        assert "field" in cd, f"Column def missing 'field': {cd}"

    fields = [cd["field"] for cd in col_defs]
    assert len(fields) == len(set(fields)), f"Duplicate fields: {[f for f in fields if fields.count(f) > 1]}"


def test_subprod_results_layout_renders_ag_grid_with_data():
    """results_layout must produce an html.Div containing an AgGrid when data is present."""
    import dash_ag_grid as dag

    from enzyme_tk_app.app.tools.substrate_product_similarity.results import results_layout

    job = make_job(
        result={
            "dataframe": {
                "columns": [COL_MOL_SVG, COL_MOL_SMILES, COL_MOL_INDEX],
                "data": [
                    {COL_MOL_SVG: "<svg/>", COL_MOL_SMILES: "CCO", COL_MOL_INDEX: 1},
                    {COL_MOL_SVG: "<svg/>", COL_MOL_SMILES: "O", COL_MOL_INDEX: 2},
                ],
            },
        },
    )
    layout = results_layout(job)

    assert isinstance(layout, html.Div)

    grids = find_components(layout, dag.AgGrid)
    assert len(grids) == 1, "Expected exactly one AgGrid in results_layout"
    assert len(grids[0].rowData) == 2, "AgGrid should contain the two data rows"


@pytest.mark.parametrize(
    "result_dict",
    [
        None,
        {},
        {"dataframe": {}},
        {"dataframe": {"columns": ["a"]}},
        {"dataframe": {"data": []}},
        {"dataframe": {"columns": ["a"], "data": []}},
    ],
    ids=[
        "none-result",
        "empty-result",
        "empty-dataframe",
        "missing-data-key",
        "missing-columns-key",
        "empty-data-list",
    ],
)
def test_subprod_results_layout_shows_fallback_for_missing_or_empty_data(result_dict):
    """results_layout must show 'No similar molecules found.' when dataframe is missing, malformed, or empty."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.results import results_layout

    job = make_job(result=result_dict)
    layout = results_layout(job)

    assert isinstance(layout, html.Div)
    paragraphs = find_components(layout, html.P)
    assert any("No similar molecules found." in str(p.children) for p in paragraphs), (
        "Expected fallback message 'No similar molecules found.'"
    )


# ── Modal layout ─────────────────────────────────────────────────────────────


def test_subprod_get_example_smiles_returns_non_empty_list():
    """_get_example_smiles must return a non-empty list of label/value/role dicts.

    Every example SMILES must also parse — a typo, or a mangled backslash escape in a
    stereo bond marker, would otherwise ship a picker entry that crashes the search.
    """
    from rdkit import Chem

    from enzyme_tk_app.app.tools.substrate_product_similarity.modal import _get_example_smiles

    examples = _get_example_smiles()
    assert isinstance(examples, list)
    assert len(examples) >= 1
    for ex in examples:
        assert "label" in ex and "value" in ex and "role" in ex
        assert len(ex["value"]) > 0, "Example SMILES must not be empty"
        assert Chem.MolFromSmiles(ex["value"]) is not None, f"Example {ex['label']!r} has invalid SMILES"


def test_subprod_modal_returns_dbc_modal():
    """modal() must return a dbc.Modal with the correct ID."""
    import dash_bootstrap_components as dbc

    from enzyme_tk_app.app.tools.substrate_product_similarity.modal import modal

    component = modal()
    assert isinstance(component, dbc.Modal)
    assert component.id == f"id-modal-{TOOL_DEF['slug']}"


# ── Submit callback ──────────────────────────────────────────────────────────


def test_subprod_submit_clears_results_on_launch():
    """Re-opening the modal must clear stale results without calling the scheduler."""
    with (
        patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx,
        patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_task_scheduler") as mock_sched,
    ):
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        result = submit_substrate_product_similarity_job(
            0, 1, "t", ["db.csv"], "CCO", ["tanimoto"], 10, "substrate", None
        )

    assert result == ""
    mock_sched.assert_not_called()


def test_subprod_submit_raises_prevent_update_when_fields_empty():
    """Missing required fields must raise PreventUpdate."""
    with (
        patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx,
        pytest.raises(PreventUpdate),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        submit_substrate_product_similarity_job(1, 0, "", None, "", None, 10, None, None)


def test_subprod_submit_returns_error_when_top_n_invalid():
    """An invalid Top N value must return the validation error without scheduling a job."""
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_task_scheduler",
            return_value=mock_scheduler,
        ),
        patch(
            "enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_reaction_database_options",
            return_value=offered_databases("db.csv"),
        ),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_substrate_product_similarity_job(
            1, 0, "My Task", ["db.csv"], "CCO", ["tanimoto"], None, "substrate", None
        )

    assert "Invalid" in result
    mock_scheduler.submit_job.assert_not_called()


def test_subprod_submit_returns_job_id():
    """A valid submission must return a message containing the job ID."""
    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-sub-789"

    with server.test_request_context():
        from flask import g

        g.session_id = "sess-1"
        with (
            patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
            patch(
                "enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.get_reaction_database_options",
                return_value=offered_databases("db.csv"),
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_substrate_product_similarity_job(
                1, 0, "Glucose search", ["db.csv"], "CCO", ["tanimoto"], 10, "substrate", None
            )

    assert "job-sub-789" in result
    assert "Substrate" in result
