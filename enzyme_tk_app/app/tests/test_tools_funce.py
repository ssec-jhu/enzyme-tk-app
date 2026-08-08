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
* **Compute** — which reactions are refused, how the accepted ones are encoded,
  which databases are loaded, which are skipped, and what the stat cards say
  about all of it.
* **The example picker** — selecting an example fills the Task Name as well as
  the SMILES, since the Task Name is the one field that otherwise blocks submit.

Nothing here touches ``data/sequence_embeddings/``.  That directory is git-ignored (the
shipped pickle and the ~3 GB checkpoint ensemble are not in the repository), so
every compute test writes the database pickles it needs into ``tmp_path`` and
repoints ``SEQUENCE_EMBEDDINGS_DIR`` at it — otherwise these tests would pass only on a
machine that happens to have the real data.

``compute.py`` imports ``torch``/``enzymetk`` inside the functions that use them
rather than at module scope, so importing it here is cheap: only the tests that
run the pipeline need the stand-in modules, and they install them in
``sys.modules`` for one test at a time.  RDKit is the exception — it is a real
dependency, small, and the whole point of the validation tests, so those run
against it unstubbed.
"""

import json
import multiprocessing
import os
import pickle
import re
import sys
import types
from pathlib import Path

import dash_ag_grid as dag
import numpy as np
import pandas as pd
import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.tests.conftest import find_components, make_job
from enzyme_tk_app.app.tools.funce import DEHP_MEHP_SMILES, EXAMPLE_REACTIONS
from enzyme_tk_app.app.tools.funce.callbacks import populate_example_reaction
from enzyme_tk_app.app.tools.funce.compute import (
    DROPPED_COLS,
    PRED_COL,
    RXN_COLS,
    UNIMOL_WEIGHTS_DIR,
    _allow_forking,
    _encode_reaction,
    _ensure_python_on_path,
    _load_databases,
    _resolve_database,
    _split_reaction,
    run,
    validate_reaction_smiles,
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

# Vector widths the trained Func-E checkpoints require: RxnFP's reaction
# fingerprint and UniMol's per-molecule embedding.  The stand-in steps below
# emit these widths so the arrays flowing through ``_encode_reaction`` have the
# shape the real ones would.
RXNFP_WIDTH = 256
UNIMOL_WIDTH = 768

# The directory holding the interpreter running these tests, and a stand-in for
# any other PATH entry — the two ingredients of the PATH tests below.
INTERPRETER_BIN_DIR = str(Path(sys.executable).parent)
UNRELATED_BIN_DIR = "/somewhere/else/bin"


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
def stub_enzymetk_steps(monkeypatch):
    """Stand in for the three ``enzymetk`` steps and ``torch`` for one test.

    ``run()`` and ``_encode_reaction`` import them inside their bodies, so
    replacing the ``sys.modules`` entries is enough — and it is also necessary:
    torch is a multi-gigabyte dependency, the enzymetk build installed here does
    not export ``Funce`` at all, and each embedding step loads a checkpoint of
    several hundred megabytes.

    Returns:
        A recorder holding what the UniMol step was built with — currently
        just its ``weights_dir``.
    """
    recorded = types.SimpleNamespace(unimol_weights_dir=None)

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

    class StubRxnFP:
        """The reaction fingerprinter, reduced to the column it writes.

        The signature mirrors the real one, so a change to how
        ``_encode_reaction`` constructs the step fails here instead of passing
        silently.
        """

        def __init__(self, reaction_col, num_threads=1, env_name=None, tmp_dir=None):
            self.reaction_col = reaction_col
            self.num_threads = num_threads
            self.env_name = env_name
            self.tmp_dir = tmp_dir

        def execute(self, frame):
            """Add one flat fingerprint per reaction row."""
            fingerprinted = frame.copy()
            fingerprinted["rxnfp"] = [[0.5] * RXNFP_WIDTH] * len(frame)
            return fingerprinted

    class StubUniMol:
        """The molecule embedder, reduced to the nested column it writes.

        The signature mirrors the real one, so dropping ``weights_dir`` — or passing
        it positionally into some other parameter — fails here rather than silently
        letting unimol_tools download its own checkpoint.
        """

        def __init__(self, smiles_col, weights_dir=None):
            self.smiles_col = smiles_col
            recorded.unimol_weights_dir = weights_dir

        def execute(self, frame):
            """Embed every molecule in the frame."""
            embedded = frame.copy()
            # Real UniMol nests its cls_repr one level deep ([[...768 floats...]]),
            # which compute has to flatten.  Each vector is filled with the length of
            # the molecule it came from, so a test can tell substrate from product.
            embedded["unimol_repr"] = [[[float(len(smiles))] * UNIMOL_WIDTH] for smiles in frame[self.smiles_col]]
            return embedded

    # One module per import in compute.  The two embedding steps need real
    # submodule entries — a single flat ``enzymetk`` stub fails with
    # "'enzymetk' is not a package" the moment one of them is imported.
    enzymetk_stub = types.ModuleType("enzymetk")
    enzymetk_stub.Funce = StubFunce
    rxnfp_stub = types.ModuleType("enzymetk.embedchem_rxnfp_step")
    rxnfp_stub.RxnFP = StubRxnFP
    unimol_stub = types.ModuleType("enzymetk.embedchem_unimol_step")
    unimol_stub.UniMol = StubUniMol
    for module_name, module in [
        ("enzymetk", enzymetk_stub),
        ("enzymetk.embedchem_rxnfp_step", rxnfp_stub),
        ("enzymetk.embedchem_unimol_step", unimol_stub),
    ]:
        monkeypatch.setitem(sys.modules, module_name, module)

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

    Shipped pickles such as ``Funce_pairs.pkl`` were built with one reaction
    already broadcast across every row.  ``run()`` writes the query's vectors
    afterwards, so a stale column left in place would be scored for any row that
    broadcast does not reach — a confident prediction for the wrong reaction.
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


# ── Compute — reading the reaction ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("CCO>>CC=O", ("CCO", "CC=O")),
        # A multi-arrow string is a route, not a reaction: the last segment is the
        # product and everything between is intermediate.
        ("CCO>>CC=O>>CC(=O)O", ("CCO", "CC(=O)O")),
        ("  CCO >> CC=O\n", ("CCO", "CC=O")),
    ],
    ids=["one-arrow", "multi-arrow-keeps-the-last-product", "padded-with-whitespace"],
)
def test_split_reaction_returns_the_substrate_and_the_final_product(smiles, expected):
    """Whatever the user pasted, the two sides come back trimmed and in order."""
    assert _split_reaction(smiles) == expected


# ── Compute — validating the reaction ────────────────────────────────────────
# Real RDKit here, no stand-ins: whether RDKit itself can read the string is the
# whole question.  The modal's submit callback shares this one answer, so a
# reaction accepted here is a reaction the worker will be asked to encode.


@pytest.mark.parametrize(
    "smiles",
    [
        "CCO>>CC=O",
        # A dot-joined side is one multi-component reaction, not two reactions —
        # it is embedded whole, so it must not be refused.
        "CCO.O>>CC(=O)O",
        # Pasted out of a paper, trailing newline and all.
        "  CCO>>CC=O \n",
    ],
    ids=["one-molecule-a-side", "dot-joined-multi-component", "padded-with-whitespace"],
)
def test_validate_reaction_smiles_accepts_a_usable_reaction(smiles):
    """A parseable substrate and product either side of ``>>`` is usable."""
    assert validate_reaction_smiles(smiles) is None


@pytest.mark.parametrize(
    ("smiles", "expected_fragment"),
    [
        # ``None`` as the fragment means any message will do — for these cases the
        # point is only that the string is refused, not how the refusal is worded.
        ("", None),
        ("   ", None),
        (None, None),
        ("CCO", "'>>'"),
        (">>CCO", None),
        ("CCO>>", None),
        # RDKit returns None rather than raising on these, so the check is easy to
        # lose; the message has to name the side the user must fix.
        ("XYZ>>CCO", "substrate"),
        ("CCO>>XYZ", "product"),
    ],
    ids=[
        "empty",
        "whitespace-only",
        "not-a-string",
        "no-arrow",
        "no-substrate",
        "no-product",
        "unparseable-substrate",
        "unparseable-product",
    ],
)
def test_validate_reaction_smiles_rejects_what_cannot_be_encoded(smiles, expected_fragment):
    """Every unusable string comes back as a message — never ``None``, never an exception.

    Encoding takes about ten seconds inside the worker, so a typo caught here
    saves a job that would otherwise fail a minute later, deep inside UniMol.
    """
    message = validate_reaction_smiles(smiles)

    assert isinstance(message, str) and message.strip(), "An unusable reaction must be reported, not accepted"
    if expected_fragment:
        assert expected_fragment in message


@pytest.mark.parametrize(
    "smiles",
    [example["value"] for example in EXAMPLE_REACTIONS],
    ids=[example["label"].split()[0] for example in EXAMPLE_REACTIONS],
)
def test_every_example_reaction_offered_in_the_modal_is_accepted(smiles):
    """An example the modal hands the user must not be refused when they submit it.

    Read out of ``EXAMPLE_REACTIONS`` rather than listed here, so a newly added
    example is checked the moment it appears in the dropdown.
    """
    assert validate_reaction_smiles(smiles) is None


# ── Compute — encoding the reaction ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("path_before", "expected_path_after"),
    [
        ([UNRELATED_BIN_DIR], [INTERPRETER_BIN_DIR, UNRELATED_BIN_DIR]),
        ([UNRELATED_BIN_DIR, INTERPRETER_BIN_DIR], [UNRELATED_BIN_DIR, INTERPRETER_BIN_DIR]),
    ],
    ids=["interpreter-missing-from-path", "interpreter-already-on-path"],
)
def test_ensure_python_on_path_makes_a_bare_python_resolvable(monkeypatch, path_before, expected_path_after):
    """A bare ``python`` must find the interpreter this process is running on.

    RxnFP shells out to ``python`` rather than ``sys.executable``, so on a machine
    that only ships ``python3`` the step dies with ``FileNotFoundError``.  Adding
    the directory a second time would be harmless but would grow PATH on every
    call, so an entry that is already there is left where it is.
    """
    monkeypatch.setenv("PATH", os.pathsep.join(path_before))

    _ensure_python_on_path()

    assert os.environ["PATH"].split(os.pathsep) == expected_path_after


def test_encode_reaction_returns_one_flat_vector_per_column_the_step_reads(stub_enzymetk_steps):
    """The keys must be exactly ``RXN_COLS``, each holding a flat float32 vector.

    ``_encode_reaction`` writes those three names out as literals, so this is
    what keeps them in step with ``RXN_COLS`` — the list ``run()`` broadcasts and
    ``_load_databases`` strips.  Flatness is a real transformation, not a
    formality: UniMol nests its output one level and the Funce step reads one
    vector per cell.
    """
    smiles = "CCO>>CC=O"
    substrate, product = _split_reaction(smiles)

    vectors = _encode_reaction(smiles)

    assert set(vectors) == set(RXN_COLS)
    for column, vector in vectors.items():
        assert vector.ndim == 1, f"'{column}' is still nested; the Funce step reads one vector per cell"
        assert vector.dtype == np.float32

    # The stand-in embedder fills each vector with the length of the molecule it
    # came from, so substrate and product swapped over would show up right here.
    assert vectors["substrate_unimol_repr"][0] == len(substrate)
    assert vectors["product_unimol_repr"][0] == len(product)

    # The two stand-in steps emit the widths their real counterparts do, so a
    # crossed wire — the fingerprint read off the molecule embedder, say — comes
    # back the wrong length.
    assert len(vectors["rxnfp"]) == RXNFP_WIDTH


def test_encode_reaction_points_unimol_at_the_bundled_weights(stub_enzymetk_steps):
    """The UniMol step must be given the app's weights directory.

    Without ``weights_dir`` the step falls back to unimol_tools' own lookup, which
    caches the ~660 MB checkpoint in its site-packages directory — re-downloading it
    into every fresh container, onto a layer that is thrown away.
    """
    _encode_reaction(DEHP_MEHP_SMILES)

    assert stub_enzymetk_steps.unimol_weights_dir == str(UNIMOL_WEIGHTS_DIR)


def test_encode_reaction_refuses_an_embedding_unimol_could_not_produce(stub_enzymetk_steps, monkeypatch):
    """A ``None`` from UniMol has to stop the job, not become a one-wide ``nan``.

    UniMol catches its own failures, logs them, and writes ``None`` instead of
    raising.  ``np.asarray(None).astype(np.float32)`` is ``array([nan])``, which
    survives the broadcast and only surfaces as "mat1 and mat2 shapes cannot be
    multiplied (10x1 and 768x1024)" inside Funce — and had the widths happened to
    line up, it would have scored nonsense silently instead.  This is not
    hypothetical: it is what a Celery worker did before ``_allow_forking``,
    because a daemonic process may not create the Pool UniMol builds conformers
    with.
    """
    unimol_step = sys.modules["enzymetk.embedchem_unimol_step"].UniMol

    def execute_failing_to_embed(self, frame):
        """Mimic UniMol swallowing an error: a None per molecule, no exception."""
        unembedded = frame.copy()
        unembedded["unimol_repr"] = [None] * len(frame)
        return unembedded

    monkeypatch.setattr(unimol_step, "execute", execute_failing_to_embed)

    with pytest.raises(ValueError, match="UniMol could not embed"):
        _encode_reaction(DEHP_MEHP_SMILES)


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


# ── Compute — run() ──────────────────────────────────────────────────────────


def test_run_refuses_a_bad_reaction_before_it_opens_a_database(embeddings_db_dir, stub_enzymetk_steps):
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
def test_run_databases_skipped_stat_card(embeddings_db_dir, stub_enzymetk_steps, databases, expected_skipped):
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


def test_run_ranks_by_prediction_and_keeps_only_top_n(embeddings_db_dir, stub_enzymetk_steps):
    """Hits come back best-first and cut to ``top_n``; the Top Score card agrees."""
    result = run(_run_params(top_n=2))

    scores = [row[PRED_COL] for row in result["dataframe"]["data"]]
    assert len(scores) == 2, "top_n was not applied"
    assert scores == sorted(scores, reverse=True), "Hits are not ranked best-first"

    cards = {card["label"]: card["value"] for card in result["_stat_cards"]}
    assert cards["Top Score"] == f"{scores[0]:.4f}"
    # Every protein is scored, even though only top_n are shown.
    assert cards["Candidates Scored"] == str(len(GOOD_DB_ENTRIES))


def test_run_result_drops_embeddings_and_stays_json_serialisable(embeddings_db_dir, stub_enzymetk_steps):
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
