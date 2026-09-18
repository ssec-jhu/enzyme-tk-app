"""Tests for the Func-E Activity Prediction tool.

Four things are pinned here:

* **The results grid** — every column header must be the raw enzymetk
  dataframe column name, never a friendlier display label.  A relabelled
  header (e.g. "Activity Probability" for ``Funce_prediction``) hides which
  enzymetk column a number actually came from, so scientists cannot trace a
  result back to the model output.
* **The dropped columns** — ``compute.DROPPED_COLS`` names what is stripped
  from the Funce output before it is JSON-encoded.  Dropping too much silently
  loses results; dropping an embedding short breaks the payload.
* **Compute** — how the reaction and the two data directories are handed to
  ``enzymetk.Funce_rxnfp_unimol``, which databases are loaded, which are skipped,
  and what the stat cards say about all of it.  *How* a reaction is encoded is no
  longer the app's contract; the step owns it.
* **The example picker** — selecting an example fills the Task Name as well as
  the SMILES, since the Task Name is the one field that otherwise blocks submit.

What makes a reaction acceptable in the first place is not pinned here: that
lives in ``utils/smiles_validation.py`` and is tested in
``test_smiles_validation.py``, since Reaction Similarity shares it.  This file
only pins that Func-E *applies* it — in the form callback, on submit, and in
``run()``.

Nothing here touches ``data/sequence_embeddings/``.  Everything in that directory is
git-ignored bar the ~640 KB ``enzymes_demo_set.pkl`` demo set (the full reference
pickles and the ~1.5 GB checkpoint ensemble are not in the repository), so every
compute test writes the database pickles it needs into ``tmp_path`` and repoints
``SEQUENCE_EMBEDDINGS_DIR`` at it — otherwise these tests would pass only on a
machine that happens to have the real data.

``compute.py`` imports ``torch``/``enzymetk`` inside the functions that use them
rather than at module scope, so importing it here is cheap: only the tests that
run the pipeline need the stand-in modules, and they install them in
``sys.modules`` for one test at a time.  RDKit is the exception — it is a real
dependency and a small one, so the tests that reject a reaction run against it
unstubbed.

One test does reach for the real package, to check the step's signature against the
call ``run()`` makes — the one thing a hand-written stub cannot do.  It is the sole
test here that pays for a real ``import enzymetk``, which *does* drag in torch, so
keep it to one: it ``importorskip``s, skipping in a dev venv whose build predates
the step and running for real in the container.
"""

import inspect
import json
import multiprocessing
import pickle
import re
import sys
import types
from unittest.mock import MagicMock, patch

import dash_ag_grid as dag
import numpy as np
import pandas as pd
import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.funce import DEHP_MEHP_SMILES, EXAMPLE_REACTIONS, TOOL_DEF
from enzyme_tk_app.app.tools.funce.callbacks import (
    populate_example_reaction,
    submit_funce_job,
    validate_funce_form,
)
from enzyme_tk_app.app.tools.funce.compute import (
    DROPPED_COLS,
    FUNCE_MODELS_DIR,
    PRED_COL,
    RXN_COLS,
    UNIMOL_WEIGHTS_DIR,
    _allow_forking,
    _load_databases,
    _resolve_database,
    run,
)
from enzyme_tk_app.app.tools.funce.results import _get_column_defs, results_layout
from enzyme_tk_app.app.utils.columns import COL_DATABASE, COL_ENTRY, COL_SEQUENCE
from enzyme_tk_app.app.utils.smiles_validation import split_reaction, validate_reaction_smiles

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

# Vector widths the trained Func-E checkpoints require: RxnFP's reaction
# fingerprint and UniMol's per-molecule embedding.  The stubbed step below writes
# these widths, so the columns ``run()`` has to drop are the shape the real ones
# would be — without them the drop would have nothing to remove and its test
# would pass with the drop deleted.
RXNFP_WIDTH = 256
UNIMOL_WIDTH = 768

# Stand-in default for the stubbed step's optional arguments, so a test can tell an
# argument the app never passed from one it passed the default value of.
_OMITTED = "<argument not passed>"


def _make_funce_frame(entries: list[str]) -> pd.DataFrame:
    """Build a pre-encoded Func-E database frame, stale reaction vectors and all.

    Carries what compute requires of a database — the identity and the protein
    embedding — plus the three reaction embeddings that shipped pickles such as
    ``Funce_pairs.pkl`` were built with.  Those are exactly what
    ``_load_databases`` must strip, so the fixture keeps them; the values are
    stand-ins that no test reads.
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
    """Stand in for ``enzymetk.Funce_rxnfp_unimol`` and ``torch`` for one test.

    ``run()`` imports both inside its body, so replacing the ``sys.modules``
    entries is enough — and it is also necessary: torch is a multi-gigabyte
    dependency, the enzymetk build installed here does not export the step at all,
    and the real thing loads roughly 2 GB of checkpoints.

    The stub mirrors the real ``__init__`` parameter names with **no** ``**kwargs``,
    so a keyword ``run()`` invents fails here rather than being swallowed.  That
    catches drift on the *app's* side only.  A hand-written stub structurally cannot
    catch a rename on the *enzymetk* side — it is the thing being substituted —
    which is what ``test_the_real_step_accepts_the_call_run_makes`` is for.

    Returns:
        A recorder holding every constructor argument, plus the daemon flag seen
        during ``execute`` — the only way to pin that ``_allow_forking`` still wraps
        the right call.
    """
    recorded = types.SimpleNamespace(
        reaction=None,
        model_dir=None,
        unimol_weights_dir=None,
        download_if_missing=None,
        id_col=None,
        protein_emb_col=None,
        daemon_during_execute=None,
    )

    class StubFunceRxnfpUnimol:
        """The one step ``run()`` calls, reduced to the columns it writes.

        Signature mirrors the real class exactly — reaction first and positional,
        the rest keyword — so passing ``id_col`` into the reaction slot, or dropping
        ``download_if_missing``, fails here instead of silently letting the real step
        fingerprint the literal text "Entry" or download a checkpoint.
        """

        def __init__(
            self,
            reaction,
            model_dir,
            unimol_weights_dir=None,
            # _OMITTED, not the real defaults (False / "Entry"), on purpose: those two
            # are also the values the app passes, so mirroring them would make
            # "argument omitted" indistinguishable from "argument passed correctly" and
            # the assertions below would hold with the arguments deleted.  Real defaults
            # are pinned by test_the_real_step_accepts_the_call_run_makes; what this
            # stub pins is the parameter *names* and the values the app chooses.
            download_if_missing=_OMITTED,
            id_col=_OMITTED,
            protein_emb_col="esm3_mean",
        ):
            recorded.reaction = reaction
            recorded.model_dir = model_dir
            recorded.unimol_weights_dir = unimol_weights_dir
            recorded.download_if_missing = download_if_missing
            recorded.id_col = id_col
            recorded.protein_emb_col = protein_emb_col

        def __rlshift__(self, frame):
            """``db << step``, enzymetk's idiom — its ``Step`` base delegates like this."""
            return self.execute(frame)

        def execute(self, frame):
            """Encode, broadcast and score exactly as the real step does.

            Faithful in three ways that tests depend on: it adds the three ndarray
            reaction columns (so the drop in ``run()`` has something to remove), it
            mutates the caller's frame **in place** and returns a ``.drop()`` copy
            (matching the real aliasing contract), and it scores rows in ascending
            order so ranking has something to reorder.
            """
            recorded.daemon_during_execute = multiprocessing.current_process().daemon
            widths = {"rxnfp": RXNFP_WIDTH, "substrate_unimol_repr": UNIMOL_WIDTH, "product_unimol_repr": UNIMOL_WIDTH}
            for column, width in widths.items():
                frame[column] = [np.full(width, 0.5, dtype=np.float32)] * len(frame)
            frame[PRED_COL] = [round(0.1 * (position + 1), 4) for position in range(len(frame))]
            # The real step returns ``frame.drop(columns=LEAKED_COLS)`` — a copy, over
            # a frame it has already mutated.  It does not emit those scratch columns
            # for the app to drop, which is why nothing here does either.
            return frame.drop(columns=[], errors="ignore")

    enzymetk_stub = types.ModuleType("enzymetk")
    enzymetk_stub.Funce_rxnfp_unimol = StubFunceRxnfpUnimol
    monkeypatch.setitem(sys.modules, "enzymetk", enzymetk_stub)

    # torch is used for exactly one thing: naming the device on a stat card.
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)

    return recorded


def _run_params(**overrides) -> dict:
    """Return a valid ``run()`` params dict, overridable field by field."""
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


def test_load_databases_drops_the_reaction_vectors_the_pickle_carries(embeddings_db_dir):
    """A database's own reaction embeddings must not survive the load.

    Shipped pickles such as ``Funce_pairs.pkl`` were built with one reaction already
    broadcast across every row, and the query's vectors must win.

    The step overwrites all three columns on every row, so this is redundant today —
    but the redundancy is not guaranteed.  The step assigns three *hard-coded* names
    while the ``Funce`` it wraps reads ``rxn_col`` / ``sub_col`` / ``prod_col`` from
    defaults the step never passes; let those drift apart and Funce reads the pickle's
    stale reaction instead, returning a confident ranking for the wrong chemistry with
    no exception and no shape mismatch to catch it.
    """
    # Guard the fixture: without the stale columns on disk there is nothing to strip.
    assert set(RXN_COLS) <= set(_make_funce_frame(GOOD_DB_ENTRIES).columns)

    frame, _ = _load_databases([GOOD_DB])

    survivors = [column for column in RXN_COLS if column in frame.columns]
    assert survivors == [], f"Stale reaction embeddings reached the scorer: {survivors}"


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


# ── Compute — how the step is constructed ────────────────────────────────────


def test_run_hands_the_step_the_reaction_and_both_data_directories(embeddings_db_dir, stub_funce_step):
    """Every constructor argument the app is responsible for, in one place.

    ``model_dir`` and ``unimol_weights_dir`` name the bundled data.  Left off, the
    step falls back to Func-E's own default (a path that does not exist) and to
    unimol_tools' own lookup, which caches the ~660 MB checkpoint in site-packages —
    re-downloading it into every fresh container, onto a layer that is thrown away.
    """
    run(_run_params())

    assert stub_funce_step.reaction == DEHP_MEHP_SMILES
    assert stub_funce_step.model_dir == str(FUNCE_MODELS_DIR)
    assert stub_funce_step.unimol_weights_dir == str(UNIMOL_WEIGHTS_DIR)
    assert stub_funce_step.id_col == COL_ENTRY


def test_run_never_lets_the_step_download(embeddings_db_dir, stub_funce_step):
    """``download_if_missing`` must be passed, and must be ``False``.

    The app does not fetch data on a user's behalf: a missing checkpoint is a
    deployment problem to report, not ~660 MB to pull inside a request that has
    already been waiting.  ``check_data`` gates the tool off long before this, so
    reaching the step with data absent already means something is wrong.

    ``False`` is the library default too, which is exactly why this is asserted
    rather than left implicit — a default that flips upstream would otherwise turn
    the app into a downloader silently.
    """
    run(_run_params())

    assert stub_funce_step.download_if_missing is False


def test_run_passes_the_reaction_positionally_not_the_id_column(embeddings_db_dir, stub_funce_step):
    """The first argument is the reaction.  The step this replaced took ``id_col``.

    ``Funce(COL_ENTRY, model_dir=...)`` and ``Funce_rxnfp_unimol(smiles,
    model_dir=...)`` both take a string first, so writing the old call is accepted
    by Python, by the type checker, and by the step's own validation.  It fails much
    later and much further away: RxnFP tries to fingerprint the literal text
    "Entry", inside a subprocess.
    """
    run(_run_params())

    assert stub_funce_step.reaction != COL_ENTRY
    assert ">>" in stub_funce_step.reaction


def test_run_collapses_a_multi_arrow_route_to_one_arrow(embeddings_db_dir, stub_funce_step):
    """A route the app accepts must reach the step as a two-block reaction.

    ``utils.smiles_validation`` deliberately reads ``A>>B>>C`` as "first segment is
    the substrate, last is the product" and Reaction Similarity depends on that, so
    the shared validator cannot be tightened.  But the step splits on a *single*
    ``>`` and demands exactly three blocks, so the raw string would raise inside
    enzymetk — turning a reaction that scores today into a failed job.
    """
    run(_run_params(smiles="CCO>>CC=O>>CC(=O)O"))

    assert stub_funce_step.reaction == "CCO>>CC(=O)O"


def test_the_real_step_accepts_the_call_run_makes():
    """Bind ``run()``'s exact arguments against the installed class.

    The stub in this file mirrors the real signature, but it cannot catch a rename
    on enzymetk's side — it *is* the substitute.  ``bind`` proves the call is valid
    against the genuine class without instantiating it or loading a checkpoint.

    Skipped rather than failed where the installed build predates the step, so a dev
    venv stays usable; it runs for real in the container, which is the environment
    that matters.
    """
    module = pytest.importorskip("enzymetk.predict_funce_step_rxnfp_unimol_workflow")

    inspect.signature(module.Funce_rxnfp_unimol.__init__).bind(
        None,  # self
        DEHP_MEHP_SMILES,
        model_dir=str(FUNCE_MODELS_DIR),
        unimol_weights_dir=str(UNIMOL_WEIGHTS_DIR),
        download_if_missing=False,
        id_col=COL_ENTRY,
    )


@pytest.mark.parametrize("started_daemonic", [True, False], ids=["celery-worker", "plain-process"])
def test_allow_forking_clears_the_daemon_flag_and_puts_it_back(monkeypatch, started_daemonic):
    """The flag must be cleared for the call and restored after it.

    Celery runs tasks in daemonic children, which may not have children of their
    own — so UniMol's conformer ``Pool`` cannot be created without this.  Leaving
    the flag cleared afterwards would extend that exemption past the one step
    that needed it, to every later step in the same worker.
    """
    process = multiprocessing.current_process()
    monkeypatch.setattr(process, "daemon", started_daemonic)

    with _allow_forking():
        assert process.daemon is False

    assert process.daemon is started_daemonic


def test_run_executes_the_step_with_the_daemon_flag_cleared(embeddings_db_dir, stub_funce_step, monkeypatch):
    """``_allow_forking`` has to wrap the step call, not merely exist.

    The test above proves the context manager works; nothing proved it was still
    around the right call.  Move the ``with`` outside ``execute()``, or delete it,
    and UniMol's conformer ``Pool`` raises inside a daemonic Celery child — which
    UniMol swallows into a ``None`` embedding rather than an error.
    """
    monkeypatch.setattr(multiprocessing.current_process(), "daemon", True)

    run(_run_params())

    assert stub_funce_step.daemon_during_execute is False


# ── Compute — run() ──────────────────────────────────────────────────────────


def test_run_refuses_a_bad_reaction_before_it_opens_a_database(embeddings_db_dir, stub_funce_step):
    """The SMILES is checked first, so nothing slow happens on behalf of a typo.

    The database named here does not exist — reading it would raise as well.
    Getting the reaction message instead is what proves validation ran first, on
    the replay path that reaches ``run()`` without going through the modal.
    """
    with pytest.raises(ValueError) as excinfo:
        run(_run_params(smiles="CCO", databases=["no_such_database.pkl"]))

    message = str(excinfo.value)
    assert "'>>'" in message
    assert "no_such_database.pkl" not in message, "A database was opened before the reaction was checked"


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


# ── Example reactions ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "example",
    EXAMPLE_REACTIONS,
    ids=[example["task_name"] for example in EXAMPLE_REACTIONS],
)
def test_every_example_reaction_is_runnable(example):
    """A shipped example must pass the same validator a typed reaction does.

    Two of these are supplied by the client and were transcribed by hand — long
    strings with stereocentres, ring-closure digits and a bracketed ion, where a
    single lost character still parses as *some* molecule or fails only once the
    job reaches the worker.  Running the real validator here is what makes a
    transcription slip a test failure instead of a broken dropdown entry.
    """
    assert validate_reaction_smiles(example["value"]) is None


def test_an_example_exercises_the_summed_multi_molecule_path():
    """At least one shipped example must carry a dot-joined side.

    The step embeds each molecule of a side separately and sums the per-side
    vectors.  Because ``sum([v]) == v``, a single-molecule example scores
    identically whether or not that reduction works — so without a multi-molecule
    example among them, nothing shipped would notice it breaking.
    """
    multi = [ex["task_name"] for ex in EXAMPLE_REACTIONS if "." in split_reaction(ex["value"])[0]]

    assert multi, "No shipped example has a dot-joined substrate; the summed path is untested"


# ── Populate example ─────────────────────────────────────────────────────────


def test_populate_example_reaction_returns_value():
    """Selecting a shipped example populates the SMILES textarea and the Task Name."""
    smiles, task_name = populate_example_reaction(DEHP_MEHP_SMILES)

    assert smiles == DEHP_MEHP_SMILES
    assert task_name == "DEHP-MEHP"


def test_populate_example_reaction_leaves_task_name_for_unknown_smiles():
    """A SMILES that is not a shipped example fills the textarea but not the Task Name."""
    smiles, task_name = populate_example_reaction("CCO>>CC=O")

    assert smiles == "CCO>>CC=O"
    assert task_name is no_update


@pytest.mark.parametrize("empty_value", [None, "", 0], ids=["none", "empty-string", "zero"])
def test_populate_example_reaction_raises_prevent_update(empty_value):
    """Clearing the example dropdown must leave every field alone."""
    with pytest.raises(PreventUpdate):
        populate_example_reaction(empty_value)


# ── Validate form ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("task_name", "smiles", "databases", "expected_disabled", "expected_invalid"),
    [
        ("My Task", DEHP_MEHP_SMILES, ["db.pkl"], False, False),
        ("", DEHP_MEHP_SMILES, ["db.pkl"], True, False),
        ("My Task", "", ["db.pkl"], True, False),
        ("My Task", DEHP_MEHP_SMILES, [], True, False),
        ("   ", "   ", ["db.pkl"], True, False),
        (None, None, None, True, False),
        # An unusable reaction disables Run *and* marks the field, which an absent
        # one deliberately does not — a blank form is not yet a mistake.
        ("My Task", "XYZ>>CCO", ["db.pkl"], True, True),
        ("My Task", "CCO", ["db.pkl"], True, True),
    ],
    ids=[
        "all-valid",
        "missing-name",
        "missing-smiles",
        "no-databases",
        "whitespace-only",
        "all-none",
        "unparseable-substrate",
        "no-arrow",
    ],
)
def test_validate_funce_form(task_name, smiles, databases, expected_disabled, expected_invalid):
    """Run must be disabled unless the form is complete *and* the reaction parses.

    Encoding takes about a minute in the worker, so the button is the cheapest
    place to stop a typo — the user never gets as far as clicking it.
    """
    disabled, invalid, message = validate_funce_form(task_name, smiles, databases)

    assert disabled is expected_disabled
    assert invalid is expected_invalid
    # The message and the red border go together: a marked field always says why.
    assert bool(message) is expected_invalid


# ── Submit job ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "smiles",
    ["", "   ", "XYZ>>CCO", "CCO", ">>"],
    ids=["empty", "whitespace-only", "unparseable-substrate", "no-arrow", "arrow-only"],
)
def test_submit_returns_error_when_smiles_invalid(smiles):
    """A bad reaction must be reported in the modal, not handed to the scheduler.

    The disabled Run button is client-side only, so this is the check that
    actually stops a crafted request from starting a minute-long encode that
    would die inside UniMol.
    """
    mock_scheduler = MagicMock()

    with (
        patch("enzyme_tk_app.app.tools.funce.callbacks.ctx") as mock_ctx,
        patch("enzyme_tk_app.app.tools.funce.callbacks.get_task_scheduler", return_value=mock_scheduler),
    ):
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_funce_job(1, 0, "My Task", smiles, ["db.pkl"], 10, None)

    assert isinstance(result, str) and result.strip(), "Expected a non-empty error message string"
    mock_scheduler.submit_job.assert_not_called()
