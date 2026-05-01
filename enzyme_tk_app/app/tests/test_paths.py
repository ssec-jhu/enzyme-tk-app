"""Tests for the centralised path constants in ``enzyme_tk_app.app.paths``.

Verifies that:
- The default ``DATA_DIR`` resolves to the bundled ``data/`` directory.
- ``ETK_DATA_DIR`` overrides ``DATA_DIR`` and all derived subdirectories.
- All exported subdirectory constants are children of ``DATA_DIR``.
"""

import importlib
from pathlib import Path

# ── Default paths ─────────────────────────────────────────────────────────────


def test_data_dir_defaults_to_bundled_data():
    """Without ETK_DATA_DIR, DATA_DIR should point at the source-bundled data/ folder."""
    from enzyme_tk_app.app.paths import DATA_DIR

    expected = Path(__file__).resolve().parent.parent / "data"
    assert DATA_DIR.resolve() == expected.resolve()


def test_subdirectories_are_children_of_data_dir():
    """Every exported subdirectory constant must be directly under DATA_DIR."""
    from enzyme_tk_app.app.paths import DATA_DIR, FOLDSEEK_DB_DIR, REACTIONS_DIR, SEQUENCES_DIR

    for name, subdir in [
        ("SEQUENCES_DIR", SEQUENCES_DIR),
        ("REACTIONS_DIR", REACTIONS_DIR),
        ("FOLDSEEK_DB_DIR", FOLDSEEK_DB_DIR),
    ]:
        assert subdir.parent == DATA_DIR, f"{name} should be a direct child of DATA_DIR"


def test_subdirectory_names():
    """Subdirectory constants must point at the expected folder names."""
    from enzyme_tk_app.app.paths import FOLDSEEK_DB_DIR, REACTIONS_DIR, SEQUENCES_DIR

    assert SEQUENCES_DIR.name == "sequences"
    assert REACTIONS_DIR.name == "reactions"
    assert FOLDSEEK_DB_DIR.name == "foldseek_db"


# ── ETK_DATA_DIR override ────────────────────────────────────────────────────


def test_etk_data_dir_overrides_root_and_subdirs(tmp_path, monkeypatch):
    """When ETK_DATA_DIR is set, reloading paths should derive all constants from it."""
    import enzyme_tk_app.app.paths as paths_mod

    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path))
    # Reload the module to re-evaluate the constants with the new environment variable.
    importlib.reload(paths_mod)

    try:
        assert paths_mod.DATA_DIR == tmp_path
        assert paths_mod.SEQUENCES_DIR == tmp_path / "sequences"
        assert paths_mod.REACTIONS_DIR == tmp_path / "reactions"
        assert paths_mod.FOLDSEEK_DB_DIR == tmp_path / "foldseek_db"
    finally:
        # Restore default module state regardless of assertion outcome.
        monkeypatch.delenv("ETK_DATA_DIR")
        importlib.reload(paths_mod)


# ── Module contract ───────────────────────────────────────────────────────────


def test_all_exports_are_path_objects():
    """Every exported constant should be a Path instance."""
    from enzyme_tk_app.app.paths import DATA_DIR, FOLDSEEK_DB_DIR, REACTIONS_DIR, SEQUENCES_DIR

    for name, obj in [
        ("DATA_DIR", DATA_DIR),
        ("SEQUENCES_DIR", SEQUENCES_DIR),
        ("REACTIONS_DIR", REACTIONS_DIR),
        ("FOLDSEEK_DB_DIR", FOLDSEEK_DB_DIR),
    ]:
        assert isinstance(obj, Path), f"{name} should be a Path, got {type(obj).__name__}"
