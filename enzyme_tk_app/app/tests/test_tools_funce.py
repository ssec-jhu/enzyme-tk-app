"""Tests for the Func-E Activity Prediction tool.

Three things are pinned here:

* **The results grid** — every column header must be the raw enzymetk
  dataframe column name, never a friendlier display label.  A relabelled
  header (e.g. "Activity Probability" for ``Funce_prediction``) hides which
  enzymetk column a number actually came from, so scientists cannot trace a
  result back to the model output.
* **The dropped columns** — ``compute.DROPPED_COLS`` names what is stripped
  from the Funce output before it is JSON-encoded.  Dropping too much silently
  loses results; dropping an embedding short breaks the payload.
* **Compute** — which databases are loaded, which are skipped, which reactions
  are refused, and what the stat cards say about all of it.

Nothing here touches ``data/sequence_embeddings/``.  That directory is git-ignored (the
shipped pickle and the ~3 GB checkpoint ensemble are not in the repository), so
every compute test writes the database pickles it needs into ``tmp_path`` and
repoints ``SEQUENCE_EMBEDDINGS_DIR`` at it — otherwise these tests would pass only on a
machine that happens to have the real data.

``compute.py`` imports ``torch``/``enzymetk`` inside ``run()`` rather than at
module scope, so importing it here is cheap: only the ``run()`` tests need the
stand-in modules, and they install them in ``sys.modules`` for one test at a
time.
"""

import json
import pickle
import re
import sys
import types

import dash_ag_grid as dag
import numpy as np
import pandas as pd
import pytest
from dash import html

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.funce import DEHP_MEHP_SMILES
from enzyme_tk_app.app.tools.funce.compute import (
    DROPPED_COLS,
    PRED_COL,
    RXN_COLS,
    _encode_reaction,
    _load_databases,
    _resolve_database,
    run,
)
from enzyme_tk_app.app.tools.funce.results import _get_column_defs, results_layout
from enzyme_tk_app.app.utils.columns import COL_DATABASE, COL_ENTRY, COL_SEQUENCE

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


# ── Compute — test databases ─────────────────────────────────────────────────
# Every compute test builds its own database pickles, so the real (git-ignored)
# data directory is never read.

# The protein embedding a database must carry — enzymetk's ``protein_emb_col``
# default, spelled out in ``compute._load_databases``'s required columns.
PROTEIN_EMBEDDING_COL = "esm3_mean"

# Filenames used throughout.  The bad one is never written unless a test says so.
GOOD_DB = "good_pairs.pkl"
OTHER_DB = "other_pairs.pkl"
BAD_DB = "bogus.pkl"

# Three proteins: enough for ranking and for a top_n cut to be visible.
GOOD_DB_ENTRIES = ["P00001", "P00002", "P00003"]


def _make_funce_frame(entries: list[str]) -> pd.DataFrame:
    """Build a minimal but valid pre-encoded Func-E database frame.

    Carries exactly what compute needs: the identity and protein embedding a
    database must supply, plus the three reaction embeddings
    ``_encode_reaction`` reads back out.  The vectors are stand-ins — no test
    looks at their contents, only that they are present and not NaN.
    """
    row_count = len(entries)
    frame = pd.DataFrame(
        {
            COL_ENTRY: entries,
            COL_SEQUENCE: ["MKTAYIAKQR"] * row_count,
            PROTEIN_EMBEDDING_COL: [np.array([0.0, 1.0, 2.0])] * row_count,
        }
    )
    # Built from RXN_COLS rather than hard-coded names so a rename in compute
    # shows up as a failure there, not as a silently wrong fixture here.  Each
    # column gets a distinguishable vector.
    for position, column in enumerate(RXN_COLS):
        frame[column] = [np.array([position + 0.1, position + 0.2])] * row_count
    return frame


@pytest.fixture()
def embeddings_db_dir(tmp_path, monkeypatch):
    """Point ``SEQUENCE_EMBEDDINGS_DIR`` at a tmp directory holding one valid database.

    Returns the directory so a test can drop extra databases — good or
    deliberately broken — beside the good one.
    """
    db_dir = tmp_path / "sequence_embeddings"
    db_dir.mkdir()
    _make_funce_frame(GOOD_DB_ENTRIES).to_pickle(db_dir / GOOD_DB)
    monkeypatch.setattr("enzyme_tk_app.app.tools.funce.compute.SEQUENCE_EMBEDDINGS_DIR", db_dir)
    return db_dir


@pytest.fixture()
def stub_funce_step(monkeypatch):
    """Stand in for ``enzymetk`` and ``torch`` for the duration of one test.

    ``run()`` imports both inside its body, so replacing their ``sys.modules``
    entries is enough — and it is also necessary: torch is a multi-gigabyte
    dependency, and the enzymetk build installed here does not export ``Funce``
    at all, so a test relying on the real package could never run.
    """

    class StubFunce:
        """The prediction step, reduced to what ``run()`` actually calls."""

        def __init__(self, entry_col, model_dir=None):
            self.entry_col = entry_col
            self.model_dir = model_dir

        def execute(self, frame):
            """Score rows in ascending order, so ranking has something to reorder."""
            scored = frame.copy()
            scored[PRED_COL] = [round(0.1 * (position + 1), 4) for position in range(len(scored))]
            return scored

    # The stub is a module so ``from enzymetk import Funce`` works, and the
    # class is a nested attribute so ``Funce(...)`` works.
    enzymetk_stub = types.ModuleType("enzymetk")
    enzymetk_stub.Funce = StubFunce
    monkeypatch.setitem(sys.modules, "enzymetk", enzymetk_stub)

    # torch is used for exactly one thing: naming the device on a stat card.
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)


def _run_params(**overrides) -> dict:
    """Return a valid ``run()`` params dict.

    ``smiles`` defaults to the one pre-encoded reaction — anything else is
    refused by ``_encode_reaction`` before the prediction step is reached.
    """
    params = {
        "task_name": "funce-test",
        "smiles": DEHP_MEHP_SMILES,
        "databases": [GOOD_DB],
        "top_n": 10,
    }
    params.update(overrides)
    return params


# ── Compute — loading databases ──────────────────────────────────────────────


def _write_corrupt_file(path):
    """Bytes that are not a pickle at all — ``read_pickle`` raises UnpicklingError."""
    path.write_bytes(b"this is not a pickle")


def _write_pickled_dict(path):
    """A perfectly valid pickle that does not hold a DataFrame."""
    with path.open("wb") as handle:
        pickle.dump({COL_ENTRY: GOOD_DB_ENTRIES}, handle)


def _write_frame_without_embedding(path):
    """A DataFrame missing the protein embedding, so nothing in it can be scored."""
    _make_funce_frame(GOOD_DB_ENTRIES).drop(columns=[PROTEIN_EMBEDDING_COL]).to_pickle(path)


def _write_empty_frame(path):
    """A DataFrame with every required column but no proteins in it."""
    _make_funce_frame([]).to_pickle(path)


@pytest.mark.parametrize(
    "write_bad_database",
    [None, _write_corrupt_file, _write_pickled_dict, _write_frame_without_embedding, _write_empty_frame],
    ids=["file-absent", "corrupt-bytes", "not-a-dataframe", "no-protein-embedding", "no-rows"],
)
def test_load_databases_skips_the_unusable_one(embeddings_db_dir, write_bad_database):
    """One unusable database is skipped and named; the good one still loads.

    The four ways a database can be unusable are checked by separate branches
    in ``_load_databases`` — an unreadable file, a pickle holding something
    other than a DataFrame, a frame short of a required column, and an empty
    frame — and all four must end in a skip rather than a failed job.
    """
    # ``None`` means "leave the file absent", which is the fifth way.
    if write_bad_database is not None:
        write_bad_database(embeddings_db_dir / BAD_DB)

    frame, skipped = _load_databases([GOOD_DB, BAD_DB])

    # Named by the full filename, extension included — the same string the
    # modal sent and the same one the stat card shows.
    assert skipped == [BAD_DB]
    assert list(frame[COL_ENTRY]) == GOOD_DB_ENTRIES
    assert set(frame[COL_DATABASE]) == {GOOD_DB}


def test_load_databases_merges_every_selection(embeddings_db_dir):
    """Two databases are searched as one, each row tagged with its own source.

    Provenance is the whole point of the ``database`` column: a hit found in
    two databases is listed twice, once per source, and must be traceable.
    """
    _make_funce_frame(["Q00001"]).to_pickle(embeddings_db_dir / OTHER_DB)

    frame, skipped = _load_databases([GOOD_DB, OTHER_DB])

    assert skipped == []
    assert list(frame[COL_ENTRY]) == [*GOOD_DB_ENTRIES, "Q00001"]
    assert list(frame[COL_DATABASE]) == [GOOD_DB] * len(GOOD_DB_ENTRIES) + [OTHER_DB]


@pytest.mark.parametrize(
    ("databases", "expected_fragment"),
    [
        ([], "At least one protein database"),
        # The names matter more than the wording: the user has to learn which
        # of their selections failed, spelled as they selected them.
        ([BAD_DB, OTHER_DB], f"could be read: {BAD_DB}, {OTHER_DB}"),
    ],
    ids=["nothing-selected", "every-selection-unusable"],
)
def test_load_databases_raises_when_nothing_can_be_searched(embeddings_db_dir, databases, expected_fragment):
    """A run with no usable database must fail loudly, not return zero hits.

    An empty result would read as "no enzymes match this reaction", which is a
    scientific claim the run never actually made.
    """
    with pytest.raises(ValueError, match=re.escape(expected_fragment)):
        _load_databases(databases)


@pytest.mark.parametrize(
    "database",
    ["../outside.pkl", "no_such_database.pkl"],
    ids=["escapes-to-a-real-file-outside", "does-not-exist"],
)
def test_resolve_database_rejects_anything_but_a_file_inside_its_directory(embeddings_db_dir, database):
    """A name arriving from the browser must resolve to a file, and to one inside ``SEQUENCE_EMBEDDINGS_DIR``.

    This is the trust boundary in front of ``read_pickle``: unpickling a file
    an attacker chose is arbitrary code execution.  The first case plants a
    genuinely readable pickle one level up, so only the parent-directory check
    can stop it.
    """
    _make_funce_frame(["P00001"]).to_pickle(embeddings_db_dir.parent / "outside.pkl")

    with pytest.raises(ValueError, match="Unknown protein database"):
        _resolve_database(database)


# ── Compute — encoding the reaction ──────────────────────────────────────────


@pytest.mark.parametrize(
    "smiles",
    [DEHP_MEHP_SMILES, f"  {DEHP_MEHP_SMILES}\n"],
    ids=["exact", "padded-with-whitespace"],
)
def test_encode_reaction_reads_vectors_from_the_first_row_that_has_them(smiles):
    """The vectors come from the first row that carries them, not from row zero.

    A database without the reaction embeddings contributes NaN rows once the
    selections are concatenated, and those rows may well come first.
    """
    with_vectors = _make_funce_frame(["Q00001"])
    without_vectors = _make_funce_frame(["P00001"]).assign(**dict.fromkeys(RXN_COLS, np.nan))
    concatenated = pd.concat([without_vectors, with_vectors], ignore_index=True)

    vectors = _encode_reaction(smiles, concatenated)

    assert sorted(vectors) == sorted(RXN_COLS)
    for column in RXN_COLS:
        np.testing.assert_array_equal(vectors[column], with_vectors[column].iloc[0])


@pytest.mark.parametrize(
    ("smiles", "frame", "expected_fragment"),
    [
        # The SMILES is refused before the frame is read at all, so a perfectly
        # good database is passed here.  Names the example the user must pick
        # instead — the label of the only entry in the modal's examples dropdown.
        ("CCO>>CC=O", _make_funce_frame(GOOD_DB_ENTRIES), "'DEHP → MEHP'"),
        # A database that never carried the reaction embeddings at all; the
        # message names the columns it lacks, built from the source constant.
        (
            DEHP_MEHP_SMILES,
            _make_funce_frame(GOOD_DB_ENTRIES).drop(columns=RXN_COLS),
            f"(missing {', '.join(RXN_COLS)})",
        ),
        # The embedding columns are present but empty on every row.
        (
            DEHP_MEHP_SMILES,
            _make_funce_frame(GOOD_DB_ENTRIES).assign(**dict.fromkeys(RXN_COLS, np.nan)),
            "reaction embeddings.",
        ),
    ],
    ids=["reaction-is-not-pre-encoded", "database-lacks-the-columns", "columns-are-all-nan"],
)
def test_encode_reaction_refuses_what_it_cannot_encode(smiles, frame, expected_fragment):
    """Each refusal must say which of the three causes it hit.

    Until the reaction encoder is wired up, only the pre-encoded example
    resolves, and only from a database that carries its vectors.  The last two
    messages share a long prefix, so each assertion deliberately targets the
    part that differs — matching the shared prefix would pass either way.
    """
    with pytest.raises(ValueError) as excinfo:
        _encode_reaction(smiles, frame)

    assert expected_fragment in str(excinfo.value)


# ── Compute — run() ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("databases", "expected_skipped"),
    [
        ([GOOD_DB], None),
        ([GOOD_DB, BAD_DB], BAD_DB),
    ],
    ids=["clean-run-has-no-card", "one-skipped-is-named"],
)
def test_run_databases_skipped_stat_card(embeddings_db_dir, stub_funce_step, databases, expected_skipped):
    """The "Databases Skipped" card appears only when a database was skipped.

    It is spliced into the card list conditionally, so both halves matter: a
    clean run must not show an empty card, and a skipped database must be named
    so the user knows the search was narrower than they asked for.
    """
    cards = {card["label"]: card["value"] for card in run(_run_params(databases=databases))["_stat_cards"]}

    # ``.get`` returns None when the card is absent, covering the clean run.
    assert cards.get("Databases Skipped") == expected_skipped
    # Only the databases that were actually read count as searched.
    assert cards["Databases Searched"] == "1"


def test_run_ranks_by_prediction_and_keeps_only_top_n(embeddings_db_dir, stub_funce_step):
    """Hits come back best-first and cut to ``top_n``; the Top Score card agrees."""
    result = run(_run_params(top_n=2))

    scores = [row[PRED_COL] for row in result["dataframe"]["data"]]
    assert len(scores) == 2, "top_n was not applied"
    assert scores == sorted(scores, reverse=True), "Hits are not ranked best-first"

    cards = {card["label"]: card["value"] for card in result["_stat_cards"]}
    assert cards["Top Score"] == f"{scores[0]:.4f}"
    # Every protein is scored, even though only top_n are shown.
    assert cards["Candidates Scored"] == str(len(GOOD_DB_ENTRIES))


def test_run_result_drops_embeddings_and_stays_json_serialisable(embeddings_db_dir, stub_funce_step):
    """Embeddings must not reach the payload — ``json.dumps`` cannot encode an ndarray.

    The backend stores the result as JSON, so an embedding left on the frame
    fails the job after all the work is done.
    """
    result = run(_run_params())
    columns = result["dataframe"]["columns"]

    for embedding in [PROTEIN_EMBEDDING_COL, *RXN_COLS]:
        assert embedding not in columns, f"Embedding column '{embedding}' reached the payload"

    # Dropping embeddings must not take the provenance column with it.
    assert COL_DATABASE in columns
    assert isinstance(json.dumps(result), str)
