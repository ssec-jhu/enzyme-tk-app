"""Tests for per-tool ``check_data()`` callables.

Each tool that has data dependencies ships a ``check_data.py`` submodule
exporting ``check_data() -> list[str]``.  Returning a non-empty list means
some required data is missing; an empty list means the data prerequisites
are satisfied.
"""

import pytest

from enzyme_tk_app.app.tools import CHECK_DATA
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
    ],
)
def test_data_consuming_tools_have_registered_check(slug):
    assert slug in CHECK_DATA
    assert callable(CHECK_DATA[slug])


# ---------------------------------------------------------------------------
# CSV-directory checks: parametrized over the three identical-shaped tools.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "path_attr"),
    [
        (reaction_check, "REACTIONS_DIR"),
        (subprod_check, "REACTIONS_DIR"),
        (sequence_check, "SEQUENCES_DIR"),
    ],
)
def test_csv_check_returns_label_when_dir_missing(monkeypatch, tmp_path, module, path_attr):
    monkeypatch.setattr(module, path_attr, tmp_path / "does-not-exist")
    missing = module.check_data()
    assert len(missing) == 1
    assert isinstance(missing[0], str) and missing[0]


@pytest.mark.parametrize(
    ("module", "path_attr"),
    [
        (reaction_check, "REACTIONS_DIR"),
        (subprod_check, "REACTIONS_DIR"),
        (sequence_check, "SEQUENCES_DIR"),
    ],
)
def test_csv_check_returns_label_when_dir_empty(monkeypatch, tmp_path, module, path_attr):
    monkeypatch.setattr(module, path_attr, tmp_path)
    missing = module.check_data()
    assert len(missing) == 1


@pytest.mark.parametrize(
    ("module", "path_attr"),
    [
        (reaction_check, "REACTIONS_DIR"),
        (subprod_check, "REACTIONS_DIR"),
        (sequence_check, "SEQUENCES_DIR"),
    ],
)
def test_csv_check_passes_when_csv_present(monkeypatch, tmp_path, module, path_attr):
    (tmp_path / "fake.csv").write_text("col\nval\n")
    monkeypatch.setattr(module, path_attr, tmp_path)
    assert module.check_data() == []


# ---------------------------------------------------------------------------
# Sequence-structure-similarity: two independent items.
# ---------------------------------------------------------------------------


def test_struct_check_reports_both_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", tmp_path / "missing-db")
    monkeypatch.setattr(struct_check, "FOLDSEEK_MODELS_DIR", tmp_path / "missing-models")
    missing = struct_check.check_data()
    assert len(missing) == 2


def test_struct_check_reports_only_models_missing(monkeypatch, tmp_path):
    db_dir = tmp_path / "fdb"
    db_dir.mkdir()
    (db_dir / "alphafold").mkdir()
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", db_dir)
    monkeypatch.setattr(struct_check, "FOLDSEEK_MODELS_DIR", tmp_path / "missing-models")
    missing = struct_check.check_data()
    assert len(missing) == 1
    assert "ProstT5" in missing[0]


def test_struct_check_reports_only_db_missing(monkeypatch, tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "weights.bin").write_bytes(b"x")
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", tmp_path / "missing-db")
    monkeypatch.setattr(struct_check, "FOLDSEEK_MODELS_DIR", models_dir)
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
    monkeypatch.setattr(struct_check, "FOLDSEEK_MODELS_DIR", models_dir)
    assert struct_check.check_data() == []


def test_struct_check_ignores_hidden_entries(monkeypatch, tmp_path):
    db_dir = tmp_path / "fdb"
    db_dir.mkdir()
    (db_dir / ".DS_Store").write_text("")  # hidden file, not a real DB subdir
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / ".hidden").write_text("")
    monkeypatch.setattr(struct_check, "FOLDSEEK_DB_DIR", db_dir)
    monkeypatch.setattr(struct_check, "FOLDSEEK_MODELS_DIR", models_dir)
    missing = struct_check.check_data()
    # Both should still be reported as missing — hidden entries don't count.
    assert len(missing) == 2
