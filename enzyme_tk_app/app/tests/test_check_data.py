"""Tests for per-tool ``check_data()`` callables.

Each tool that has data dependencies ships a ``check_data.py`` submodule
exporting ``check_data() -> list[str]``.  Returning a non-empty list means
some required data is missing; an empty list means the data prerequisites
are satisfied.
"""

import pytest

from enzyme_tk_app.app.tools import CHECK_DATA
from enzyme_tk_app.app.tools.funce import check_data as funce_check
from enzyme_tk_app.app.tools.funce.check_data import _CHECKPOINT_STEM
from enzyme_tk_app.app.tools.reaction_similarity import check_data as reaction_check
from enzyme_tk_app.app.tools.sequence_similarity import check_data as sequence_check
from enzyme_tk_app.app.tools.sequence_structure_similarity import check_data as struct_check
from enzyme_tk_app.app.tools.substrate_product_similarity import check_data as subprod_check

# ---------------------------------------------------------------------------
# Discovery: each expected tool registers a check; timer-tool-template does not.
# ---------------------------------------------------------------------------


def test_timer_tool_has_no_registered_check():
    """timer-tool-template intentionally has no data dependencies."""
    assert "timer-tool-template" not in CHECK_DATA


@pytest.mark.parametrize(
    "slug",
    [
        "reaction-similarity",
        "substrate-product-similarity",
        "sequence-similarity",
        "sequence-structure-similarity",
        "funce",
    ],
)
def test_data_consuming_tools_have_registered_check(slug):
    assert slug in CHECK_DATA
    assert callable(CHECK_DATA[slug])


# ---------------------------------------------------------------------------
# CSV-directory checks: parametrized over the two identical-shaped reaction
# tools.  Sequence-similarity has its own section below — it checks the
# columns inside the file, not just that a file is there.
# ---------------------------------------------------------------------------

_REACTION_CHECKS = [(reaction_check, "REACTIONS_DIR"), (subprod_check, "REACTIONS_DIR")]


@pytest.mark.parametrize(("module", "path_attr"), _REACTION_CHECKS)
def test_csv_check_returns_label_when_dir_missing(monkeypatch, tmp_path, module, path_attr):
    monkeypatch.setattr(module, path_attr, tmp_path / "does-not-exist")
    missing = module.check_data()
    assert len(missing) == 1
    assert isinstance(missing[0], str) and missing[0]


@pytest.mark.parametrize(("module", "path_attr"), _REACTION_CHECKS)
def test_csv_check_returns_label_when_dir_empty(monkeypatch, tmp_path, module, path_attr):
    monkeypatch.setattr(module, path_attr, tmp_path)
    missing = module.check_data()
    assert len(missing) == 1


@pytest.mark.parametrize(("module", "path_attr"), _REACTION_CHECKS)
def test_csv_check_passes_when_csv_present(monkeypatch, tmp_path, module, path_attr):
    (tmp_path / "fake.csv").write_text("col\nval\n")
    monkeypatch.setattr(module, path_attr, tmp_path)
    assert module.check_data() == []


# ---------------------------------------------------------------------------
# Sequence-similarity: a file only counts once its columns check out, so this
# check reports both "no databases at all" and "this file is not one".
# ---------------------------------------------------------------------------

_SEQUENCE_DB_ROWS = "Entry,Sequence,EC number\nE1,MKTAY,1.1.1.1\n"


@pytest.fixture()
def sequences_dir_for_check(tmp_path, monkeypatch):
    """Point the scanner's ``SEQUENCES_DIR`` at an empty tmp directory and return it.

    ``check_data`` delegates to ``data_loading.scan_sequence_databases``, so the
    constant to patch lives there rather than on the check module.
    """
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", tmp_path)
    return tmp_path


def test_sequence_check_returns_label_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", tmp_path / "does-not-exist")
    missing = sequence_check.check_data()
    assert len(missing) == 1
    assert isinstance(missing[0], str) and missing[0]


def test_sequence_check_returns_label_when_dir_empty(sequences_dir_for_check):
    assert len(sequence_check.check_data()) == 1


@pytest.mark.parametrize(
    "filename",
    ["protein.csv", "enzymes.tsv"],
    ids=["csv", "tsv"],
)
def test_sequence_check_passes_for_a_compliant_database(sequences_dir_for_check, filename):
    """A CSV or a TSV with the three required columns satisfies the check."""
    body = _SEQUENCE_DB_ROWS.replace(",", "\t") if filename.endswith(".tsv") else _SEQUENCE_DB_ROWS
    (sequences_dir_for_check / filename).write_text(body)

    assert sequence_check.check_data() == []


def test_sequence_check_reports_a_file_that_is_not_a_database(sequences_dir_for_check):
    """With no usable database, both the missing-data label and the reason are returned."""
    (sequences_dir_for_check / "bad.csv").write_text("Entry,Sequence\nE1,MKTAY\n")

    missing = sequence_check.check_data()

    assert len(missing) == 2
    # First the "what you need" label, then why this particular file is not it.
    assert "EC number" in missing[0]
    assert "bad.csv" in missing[1]
    assert "EC number" in missing[1]


def test_sequence_check_still_reports_a_bad_file_beside_a_good_one(sequences_dir_for_check):
    """A usable database exists, so only the offending file is reported.

    Without this the scientist gets no explanation for why the file they
    dropped in never appears in the dropdown.
    """
    (sequences_dir_for_check / "good.csv").write_text(_SEQUENCE_DB_ROWS)
    (sequences_dir_for_check / "bad.csv").write_text("Entry,Sequence\nE1,MKTAY\n")

    missing = sequence_check.check_data()

    assert len(missing) == 1
    assert "bad.csv" in missing[0]


# ---------------------------------------------------------------------------
# Sequence-structure-similarity: two independent items.
# ---------------------------------------------------------------------------


def test_struct_check_reports_both_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", tmp_path / "missing-db")
    monkeypatch.setattr(struct_check, "FOLDSEEK_WEIGHTS_DIR", tmp_path / "missing-models")
    missing = struct_check.check_data()
    assert len(missing) == 2


def test_struct_check_reports_only_models_missing(monkeypatch, tmp_path):
    db_dir = tmp_path / "fdb"
    db_dir.mkdir()
    (db_dir / "alphafold").mkdir()
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", db_dir)
    monkeypatch.setattr(struct_check, "FOLDSEEK_WEIGHTS_DIR", tmp_path / "missing-models")
    missing = struct_check.check_data()
    assert len(missing) == 1
    assert "ProstT5" in missing[0]


def test_struct_check_reports_only_db_missing(monkeypatch, tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "weights.bin").write_bytes(b"x")
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", tmp_path / "missing-db")
    monkeypatch.setattr(struct_check, "FOLDSEEK_WEIGHTS_DIR", models_dir)
    missing = struct_check.check_data()
    assert len(missing) == 1
    assert "FoldSeek" in missing[0]


def test_struct_check_passes_when_all_present(monkeypatch, tmp_path):
    db_dir = tmp_path / "fdb"
    db_dir.mkdir()
    (db_dir / "alphafold").mkdir()
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "weights.bin").write_bytes(b"x")
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", db_dir)
    monkeypatch.setattr(struct_check, "FOLDSEEK_WEIGHTS_DIR", models_dir)
    assert struct_check.check_data() == []


def test_struct_check_ignores_hidden_entries(monkeypatch, tmp_path):
    db_dir = tmp_path / "fdb"
    db_dir.mkdir()
    (db_dir / ".DS_Store").write_text("")  # hidden file, not a real DB subdir
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / ".hidden").write_text("")
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", db_dir)
    monkeypatch.setattr(struct_check, "FOLDSEEK_WEIGHTS_DIR", models_dir)
    missing = struct_check.check_data()
    # Both should still be reported as missing — hidden entries don't count.
    assert len(missing) == 2


# ---------------------------------------------------------------------------
# Func-E: two independent items — one database pickle + the four-model ensemble.
# ---------------------------------------------------------------------------


def _write_funce_ensemble(models_dir, ec_levels, without_checkpoint=()):
    """Write the config + checkpoint pair Func-E expects for each EC level.

    Levels named in *without_checkpoint* get the config only — what a
    half-finished download leaves behind.  File contents are irrelevant: the
    check only asks whether each name exists.
    """
    models_dir.mkdir(exist_ok=True)
    for ec in ec_levels:
        stem = _CHECKPOINT_STEM.format(ec=ec)
        (models_dir / f"{stem}_conf.pkl").write_bytes(b"x")
        if ec not in without_checkpoint:
            (models_dir / f"{stem}_checkpoint.pth").write_bytes(b"x")


def test_funce_check_reports_both_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(funce_check, "SEQUENCE_EMBEDDINGS_DIR", tmp_path / "missing-db")
    monkeypatch.setattr(funce_check, "FUNCE_MODELS_DIR", tmp_path / "missing-models")
    missing = funce_check.check_data()
    assert len(missing) == 2
    # Two different items, not one of them reported twice.
    assert len(set(missing)) == 2


@pytest.mark.parametrize(
    "db_dir_state",
    ["absent", "empty", "no-pickles"],
    ids=["db-dir-absent", "db-dir-empty", "db-dir-has-no-pkl"],
)
def test_funce_check_reports_only_db_missing(monkeypatch, tmp_path, db_dir_state):
    """With the ensemble in place, only the missing database is reported.

    A directory that exists but holds no ``.pkl`` is just as unusable as no
    directory at all, so all three states read the same way.
    """
    db_dir = tmp_path / "sequence_embeddings"
    if db_dir_state != "absent":
        db_dir.mkdir()
    if db_dir_state == "no-pickles":
        (db_dir / "README.txt").write_text("download instructions, not a database")

    models_dir = tmp_path / "funce_models"
    _write_funce_ensemble(models_dir, funce_check.EC_LEVELS)
    monkeypatch.setattr(funce_check, "SEQUENCE_EMBEDDINGS_DIR", db_dir)
    monkeypatch.setattr(funce_check, "FUNCE_MODELS_DIR", models_dir)

    missing = funce_check.check_data()
    assert len(missing) == 1
    assert "sequence_embeddings" in missing[0]


@pytest.mark.parametrize(
    ("ec_levels_present", "without_checkpoint"),
    [
        ((), ()),
        (funce_check.EC_LEVELS[:-1], ()),
        (funce_check.EC_LEVELS, (funce_check.EC_LEVELS[-1],)),
    ],
    ids=["no-checkpoints-at-all", "one-ec-level-absent", "config-without-its-checkpoint"],
)
def test_funce_check_reports_a_partial_ensemble_as_missing(
    monkeypatch, tmp_path, ec_levels_present, without_checkpoint
):
    """Anything short of the complete ensemble counts as missing — by design.

    Func-E averages one model per EC level.  With a level absent it still runs,
    but predicts from a different ensemble than the results claim, so a partial
    download is reported rather than quietly used.  Reported once, not once per
    absent level.
    """
    db_dir = tmp_path / "sequence_embeddings"
    db_dir.mkdir()
    (db_dir / "pairs.pkl").write_bytes(b"x")  # only its name matters here

    models_dir = tmp_path / "funce_models"
    _write_funce_ensemble(models_dir, ec_levels_present, without_checkpoint)
    monkeypatch.setattr(funce_check, "SEQUENCE_EMBEDDINGS_DIR", db_dir)
    monkeypatch.setattr(funce_check, "FUNCE_MODELS_DIR", models_dir)

    missing = funce_check.check_data()
    assert len(missing) == 1
    assert "funce_models" in missing[0]


def test_funce_check_passes_when_all_present(monkeypatch, tmp_path):
    db_dir = tmp_path / "sequence_embeddings"
    db_dir.mkdir()
    (db_dir / "pairs.pkl").write_bytes(b"x")
    models_dir = tmp_path / "funce_models"
    _write_funce_ensemble(models_dir, funce_check.EC_LEVELS)
    monkeypatch.setattr(funce_check, "SEQUENCE_EMBEDDINGS_DIR", db_dir)
    monkeypatch.setattr(funce_check, "FUNCE_MODELS_DIR", models_dir)

    assert funce_check.check_data() == []
