"""Tests for the demo reference data the repository ships.

Four small artifacts are tracked in ``enzyme_tk_app/app/data/`` so that a plain
``git clone`` plus ``docker compose up`` is enough to run four of the six tools --
Sequence and Structure-Based Similarity and Func-E still need model weights no clone
can ship.  Each artifact is a verbatim row-subset of a full reference file:

- ``sequences/enzymes_demo_set.tsv``
- ``reactions/enzymemap_demo_set.csv``
- ``sequence_embeddings/enzymes_demo_set.pkl``
- ``foldseek_db/enzymes_demo_set/``

**These tests read the real shipped files on purpose.**  Everywhere else in the
suite a data-directory constant is monkeypatched at ``tmp_path`` so a test cannot
depend on what a developer happens to have lying around — here the shipped files
*are* what is under test, so patching them away would leave nothing to check.  It
works in CI because all four artifacts are git-tracked.  Please do not "fix" this
by pointing the constants somewhere else.

Most of what follows reads a shipped file, but the chemistry examples are checked
by *running* their tool against the shipped reactions demo set: that demo set was
cut by measuring each example's top hits, so no string in the CSV would show that
an example still has something to find.

The four paths are derived from the app's own ``paths.py`` constants rather than
spelled out relative to this file, so a deployment that redirects ``ETK_DATA_DIR``
is held to the same contract: wherever the app looks for data, the demo sets are
what a first-time user gets.
"""

import pandas as pd
import pytest

from enzyme_tk_app.app.paths import (
    FOLDSEEK_DB_DIR,
    REACTIONS_DIR,
    SEQUENCE_EMBEDDINGS_DIR,
    SEQUENCES_DIR,
    STRUCTURES_DIR,
)
from enzyme_tk_app.app.tools.reaction_similarity.compute import run as run_reaction_similarity
from enzyme_tk_app.app.tools.reaction_similarity.modal import _get_example_reactions
from enzyme_tk_app.app.tools.sequence_similarity.modal import _get_example_sequences
from enzyme_tk_app.app.tools.sequence_structure_similarity.modal import _get_example_entries
from enzyme_tk_app.app.tools.substrate_product_similarity import get_similarity_algorithms
from enzyme_tk_app.app.tools.substrate_product_similarity.compute import run as run_substrate_product_similarity
from enzyme_tk_app.app.tools.substrate_product_similarity.modal import _get_example_smiles
from enzyme_tk_app.app.utils.columns import COL_EC_NUMBER, COL_ENTRY, COL_ID, COL_SEQUENCE, COL_UNMAPPED_SMILES
from enzyme_tk_app.app.utils.data_loading import (
    REQUIRED_SEQUENCE_COLUMNS,
    get_cofactors,
    get_ec_numbers,
    get_foldseek_database_options,
    get_reaction_database_options,
    get_sequence_database_options,
    get_sequence_embedding_database_options,
    sequence_db_separator,
)

SEQUENCE_DEMO_SET = SEQUENCES_DIR / "enzymes_demo_set.tsv"
REACTION_DEMO_SET = REACTIONS_DIR / "enzymemap_demo_set.csv"
EMBEDDING_DEMO_SET = SEQUENCE_EMBEDDINGS_DIR / "enzymes_demo_set.pkl"
FOLDSEEK_DEMO_SET = FOLDSEEK_DB_DIR / "enzymes_demo_set"

# The Func-E tool reads exactly these three columns out of an embeddings pickle
# (``required_cols`` in tools/funce/compute.py), and the builder writes exactly
# these three (``PICKLE_COLUMNS`` in scripts/db_build/build_enzyme_db.py).  The
# builder ships in its own image and cannot import the app, so this is the only
# place the two lists are ever compared against the file they describe.
EMBEDDING_PICKLE_COLUMNS = [COL_ENTRY, COL_SEQUENCE, "esm3_mean"]

# The shipped examples, with their Task Name as the parametrize id so a failure
# names the example a user would have clicked.
EXAMPLE_SEQUENCES = _get_example_sequences()
EXAMPLE_SEQUENCE_IDS = [example["task_name"] for example in EXAMPLE_SEQUENCES]


@pytest.fixture()
def demo_sequences():
    """The shipped sequence demo set, read the same way the app reads it."""
    return pd.read_csv(SEQUENCE_DEMO_SET, sep=sequence_db_separator(SEQUENCE_DEMO_SET))


@pytest.fixture()
def demo_embeddings():
    """The shipped embeddings demo set."""
    # nosec B301 — a pickle this repository ships, not user input.
    return pd.read_pickle(EMBEDDING_DEMO_SET)  # nosec B301


# ── Discovery ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("build_options", "demo_set_name"),
    [
        (get_sequence_database_options, SEQUENCE_DEMO_SET.name),
        (get_reaction_database_options, REACTION_DEMO_SET.name),
        (get_sequence_embedding_database_options, EMBEDDING_DEMO_SET.name),
        (get_foldseek_database_options, FOLDSEEK_DEMO_SET.name),
    ],
    ids=["sequences", "reactions", "sequence-embeddings", "foldseek"],
)
def test_every_demo_set_is_offered_by_its_own_dropdown(build_options, demo_set_name):
    """A freshly cloned checkout must offer all four demo sets without any setup.

    Containment, never equality: a developer machine also has the full reference
    sets sitting in these directories, and an equality check would pass only on a
    fresh clone — which is the one machine nobody runs the suite on.

    For the sequence demo set this is also the contract check: the builder only
    offers a file that carries every one of ``REQUIRED_SEQUENCE_COLUMNS``, so a
    demo set that lost one would drop out of this list.
    """
    offered = {option["value"] for option in build_options()}

    assert demo_set_name in offered


# ── The sequence demo set ────────────────────────────────────────────────────


def test_the_sequence_demo_set_carries_every_required_column(demo_sequences):
    """``Entry``, ``Sequence`` and ``EC number`` are what make a file a sequence database.

    The discovery test above already fails when one of these goes missing, but it
    can only say "not offered".  This one names the column, which is the difference
    between a five-minute fix and an afternoon.
    """
    missing = [column for column in REQUIRED_SEQUENCE_COLUMNS if column not in demo_sequences.columns]

    assert missing == []


def test_every_row_of_the_sequence_demo_set_declares_an_ec_number(demo_sequences):
    """The demo set was curated so that no row has a blank ``EC number``.

    A row without one is invisible to the modal's EC filter: it is in the database,
    it can be BLASTed, but no EC selection a user can make will ever include it.
    """
    rows_without_an_ec = demo_sequences[demo_sequences[COL_EC_NUMBER].isna()]

    assert rows_without_an_ec[COL_ENTRY].tolist() == []


@pytest.mark.parametrize("example", EXAMPLE_SEQUENCES, ids=EXAMPLE_SEQUENCE_IDS)
def test_every_sequence_example_is_in_the_demo_set(demo_sequences, example):
    """Clicking any shipped example must return hits against the demo set.

    Matching on the sequence rather than on the accession in the label: the
    sequence is what is actually BLASTed, so it is what decides whether the
    example returns anything.  Present in the database, it at least finds itself.
    """
    assert example["value"] in set(demo_sequences[COL_SEQUENCE])


@pytest.mark.parametrize(
    ("example_key", "read_values_in_demo_set"),
    [("ec", get_ec_numbers), ("cofactors", get_cofactors)],
    ids=["ec-number", "cofactor"],
)
def test_every_example_filter_value_is_offered_by_the_demo_set(example_key, read_values_in_demo_set):
    """An example that prefills a filter must prefill one the demo set can offer.

    The examples write their filter values verbatim — ``4.2.1.1``, ``1.15.1.1``,
    ``heme``, ``Mn(2+)`` — bypassing the option builder the dropdown is populated
    from.  If the demo set stopped carrying one of them, the example would still
    load, the filter would still show, and the search would silently return
    nothing: a filter that matches no row is not an error anywhere in the app.
    """
    offered = set(read_values_in_demo_set(SEQUENCE_DEMO_SET))

    declared = set()
    for example in EXAMPLE_SEQUENCES:
        declared.update(example.get(example_key, []))

    # Without this the test would pass by doing nothing the day the last example
    # carrying this filter is dropped.
    assert declared, f"no shipped example declares a '{example_key}' filter any more"
    # Subtracted rather than compared with <=, so a failure names the handful of values
    # that went missing instead of printing every value the demo set does offer.
    assert sorted(declared - offered) == []


# ── The embeddings demo set ──────────────────────────────────────────────────


def test_the_embedding_demo_set_carries_exactly_the_columns_funce_requires(demo_embeddings):
    """Exactly these three columns, in this order — not merely at least them.

    The full ``enzymes.tsv`` has 17 columns and the builder drops the other 14 on
    purpose: they are metadata Func-E never reads, and carrying them would only
    make the pickle bigger.  The builder also refuses to resume from a pickle whose
    columns differ, so a drifted demo set stops the next build outright.
    """
    assert list(demo_embeddings.columns) == EMBEDDING_PICKLE_COLUMNS


def test_the_embedding_demo_set_covers_the_sequence_demo_set_exactly(demo_embeddings, demo_sequences):
    """The shipped pickle holds an embedding for every protein in the TSV, and no other.

    Equality, not containment.  ``build_enzyme_db.py`` tops the pickle up run by run, so a
    half-built one is a normal *intermediate* state — but shipping one would make Func-E
    silently score fewer enzymes than Sequence Similarity searches, over what looks like
    the same 100 proteins.  That is the failure this guards: an ``Entry`` the TSV has never
    heard of means the two were built from different inputs, and a missing one means the
    build was shipped unfinished (a long sequence skipped at the ESM3 memory ceiling is how
    that happens in practice).
    """
    assert set(demo_embeddings[COL_ENTRY]) == set(demo_sequences[COL_ENTRY])


# ── The FoldSeek demo database ───────────────────────────────────────────────


def test_the_foldseek_demo_database_has_the_index_enzymetk_looks_for():
    """``<name>.index`` is the one file enzymetk checks before searching.

    Its ``_database_exists()`` keys on exactly that path.  Ship every other file and
    leave this one out and the step does not fail — it decides the database is not
    there and tries to *build* one, which needs ProstT5 weights no clone has.
    """
    assert (FOLDSEEK_DEMO_SET / f"{FOLDSEEK_DEMO_SET.name}.index").exists()


def test_the_foldseek_demo_database_covers_the_sequence_demo_set(demo_sequences):
    """A FoldSeek hit is reported by accession, and that accession comes from ``.lookup``.

    The database is built from the same TSV in one pass — there is no partial state to
    allow for — so the two sides hold exactly the same proteins.  An accession the TSV
    has never heard of would surface as a hit with no metadata behind it, and an ``Entry``
    the database is missing is a demo sequence no structure search can ever return.

    Equality also catches a duplicate ``Entry`` creeping into the TSV, which the builder
    drops without a word rather than writing a duplicate FASTA header.
    """
    accessions = set()
    for line in (FOLDSEEK_DEMO_SET / f"{FOLDSEEK_DEMO_SET.name}.lookup").read_text().splitlines():
        if not line.strip():
            continue
        # Tab-separated: internal key, accession, source-file number.
        accessions.add(line.split("\t")[1])

    assert accessions == set(demo_sequences[COL_ENTRY])


# ── The reactions demo set ───────────────────────────────────────────────────


def test_the_reaction_demo_set_carries_the_columns_both_reaction_tools_read():
    """``unmapped`` holds the reaction SMILES and ``id`` identifies the row.

    Reaction Similarity passes both straight to enzymetk; Substrate/Product
    Similarity groups on them to number the molecules it explodes out of each
    side.  Nothing in ``get_reaction_database_options()`` checks a reaction CSV's
    header — a ``.csv`` in that directory is offered on sight — so this is the only
    place a demo set missing one of them would be caught before a job failed.
    """
    columns = pd.read_csv(REACTION_DEMO_SET, nrows=0).columns

    assert COL_UNMAPPED_SMILES in columns
    assert COL_ID in columns


# The Top N field ships ``value=10`` in both chemistry modals, and the reaction
# demo set was cut to exactly that number: its 110 rows are the union of the
# exact top-10 hits for all 11 chemistry examples, measured with the same
# fingerprints the tools use.  Raise the modal default and the demo set can no
# longer reproduce the full 62,896-row file's answer — only the full file can.
DEFAULT_TOP_N = 10


def _chemistry_example_cases():
    """Build the ``run()`` params one click on each shipped chemistry example produces.

    Both chemistry modals open with every database selected, every similarity
    algorithm ticked and Top N at 10, so an example itself only supplies the
    structure — plus, for Substrate/Product Similarity, which side of the
    reaction that structure sits on.  Its dropdown packs the two into a single
    ``"role||smiles"`` value that ``populate_example_smiles`` splits again; both
    halves are read straight off the example dict both sides are built from.
    """
    all_algorithms = [algorithm["value"] for algorithm in get_similarity_algorithms()]

    cases = []
    for example in _get_example_reactions():
        cases.append(
            (
                run_reaction_similarity,
                {
                    "task_name": example["task_name"],
                    "databases": [REACTION_DEMO_SET.name],
                    "smiles": example["value"],
                    "algorithms": all_algorithms,
                    "top_n": DEFAULT_TOP_N,
                },
            )
        )

    for example in _get_example_smiles():
        cases.append(
            (
                run_substrate_product_similarity,
                {
                    "task_name": example["task_name"],
                    "databases": [REACTION_DEMO_SET.name],
                    "smiles": example["value"],
                    "algorithms": all_algorithms,
                    "top_n": DEFAULT_TOP_N,
                    "role": example["role"],
                },
            )
        )

    return cases


# Shared across the cases below, which is safe because a params dict is an inert
# job payload: ``run()`` only reads it (the worker deserialises its own copy out
# of Redis), so no case can leave a changed dict behind for the next one.
CHEMISTRY_EXAMPLE_CASES = _chemistry_example_cases()
CHEMISTRY_EXAMPLE_IDS = [params["task_name"] for _run_tool, params in CHEMISTRY_EXAMPLE_CASES]


@pytest.mark.parametrize(("run_tool", "params"), CHEMISTRY_EXAMPLE_CASES, ids=CHEMISTRY_EXAMPLE_IDS)
def test_every_chemistry_example_returns_a_full_page_of_hits(run_tool, params):
    """Clicking any shipped chemistry example must fill the results grid.

    **Ten rows is the guarantee here, not ten good scores.**  Four of these
    examples — bisphenol-A, triclocarban, indigo and PFOA — have no close
    analogue even in the full 62,896-row database: their best hits score
    0.42-0.64 Tanimoto.  Asserting a similarity floor would therefore be
    asserting something false about the chemistry rather than something true
    about the demo set, so what is checked is that a ranked list came back at
    all and that it is as long as the user asked for.

    Unlike the sequence examples above this runs the tool, because the demo set
    was sized by *measuring* each example's top hits: none of these queries is a
    string in the CSV, so there is nothing to look up.  Both tools are pure RDKit
    over 110 rows and the whole set finishes in a couple of seconds.
    """
    result = run_tool(params)
    rows = result["dataframe"]["data"]

    # Two assertions on purpose: nothing at all means the demo set lost the
    # chemistry this example was chosen for, while a short list means it kept
    # only some of it.  Those are different mornings' work.
    assert rows, "returned no hits against the reactions demo set"
    assert len(rows) == DEFAULT_TOP_N, f"returned {len(rows)} hits, not the {DEFAULT_TOP_N} requested"


# ── The example query structures ─────────────────────────────────────────────


def test_every_example_query_structure_ships_with_the_repository():
    """An example offering a structure must offer one that is actually on disk.

    ``populate_example_sequence`` reads the file with a bare ``read_bytes()``, so
    a renamed or dropped ``.cif`` does not degrade to a sequence-only search — it
    is an uncaught ``FileNotFoundError`` raised inside the callback the moment the
    example is picked.  ``data/structures/`` is git-tracked for exactly that
    reason, the only directory besides the demo sets that ``.gitignore``
    un-ignores under ``data/``.
    """
    entries_with_a_structure = [entry for entry in _get_example_entries() if entry.get("structure_file")]

    # Without this the test would pass by doing nothing the day the last example
    # carrying a structure is dropped.
    assert entries_with_a_structure, "no shipped example offers a query structure any more"

    missing = [
        entry["structure_file"]
        for entry in entries_with_a_structure
        if not (STRUCTURES_DIR / entry["structure_file"]).is_file()
    ]

    assert missing == []
