"""Tests for the centralised path constants in ``enzyme_tk_app.app.paths``.

Verifies that:
- The default ``DATA_DIR`` resolves to the bundled ``data/`` directory.
- ``ETK_DATA_DIR`` overrides ``DATA_DIR`` and all derived subdirectories.
- All exported subdirectory constants are children of ``DATA_DIR``.
"""

import importlib
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clear_data_dir_env(monkeypatch):
    """Ensure ETK_DATA_DIR is unset so tests start from the default state."""
    # delenv raises KeyError when the variable isn't set.
    # Adding raising=False makes it a no-op in that case.
    monkeypatch.delenv("ETK_DATA_DIR", raising=False)


# ── Default paths ─────────────────────────────────────────────────────────────


def test_data_dir_defaults_to_bundled_data():
    """Without ETK_DATA_DIR, DATA_DIR should point at the source-bundled data/ folder."""
    from enzyme_tk_app.app.paths import DATA_DIR

    # The expected path is the data/ directory located two levels up from this test file.
    expected = Path(__file__).resolve().parent.parent / "data"
    assert DATA_DIR.resolve() == expected.resolve()


def test_subdirectories_are_children_of_data_dir():
    """Every overridable subdirectory constant must be directly under DATA_DIR.

    ``STRUCTURES_DIR`` is intentionally excluded -- it is pinned to the
    in-source bundled folder and does not follow ``DATA_DIR``.
    """
    from enzyme_tk_app.app.paths import (
        DATA_DIR,
        FOLDSEEK_DB_DIR,
        FOLDSEEK_MODELS_DIR,
        REACTIONS_DIR,
        SEQUENCES_DIR,
    )

    # Each subdirectory should be a direct child of DATA_DIR, not a nested path.
    for name, subdir in [
        ("SEQUENCES_DIR", SEQUENCES_DIR),
        ("REACTIONS_DIR", REACTIONS_DIR),
        ("FOLDSEEK_DB_DIR", FOLDSEEK_DB_DIR),
        ("FOLDSEEK_MODELS_DIR", FOLDSEEK_MODELS_DIR),
    ]:
        assert subdir.parent == DATA_DIR, f"{name} should be a direct child of DATA_DIR"


def test_all_exports_are_path_objects():
    """Every exported constant should be a Path instance."""
    from enzyme_tk_app.app.paths import (
        DATA_DIR,
        FOLDSEEK_DB_DIR,
        FOLDSEEK_MODELS_DIR,
        REACTIONS_DIR,
        SEQUENCES_DIR,
        STRUCTURES_DIR,
    )

    # Verify that each exported constant is an instance of Path, ensuring type consistency across the module.
    for name, obj in [
        ("DATA_DIR", DATA_DIR),
        ("SEQUENCES_DIR", SEQUENCES_DIR),
        ("REACTIONS_DIR", REACTIONS_DIR),
        ("FOLDSEEK_DB_DIR", FOLDSEEK_DB_DIR),
        ("FOLDSEEK_MODELS_DIR", FOLDSEEK_MODELS_DIR),
        ("STRUCTURES_DIR", STRUCTURES_DIR),
    ]:
        assert isinstance(obj, Path), f"{name} should be a Path, got {type(obj).__name__}"


def test_structures_dir_is_in_source_tree():
    """``STRUCTURES_DIR`` must always resolve to the in-source bundled folder."""
    from enzyme_tk_app.app.paths import STRUCTURES_DIR

    expected = Path(__file__).resolve().parent.parent / "data" / "structures"
    assert STRUCTURES_DIR.resolve() == expected.resolve()


# ── ETK_DATA_DIR override ────────────────────────────────────────────────────


def test_etk_data_dir_overrides_root_and_subdirs(tmp_path, monkeypatch):
    """When ETK_DATA_DIR is set, reloading paths should derive all constants from it."""
    import enzyme_tk_app.app.paths as paths_mod

    # Set ETK_DATA_DIR to a temporary directory and reload the paths module to apply the change.
    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path))

    # Reload the module to re-evaluate the constants with the new environment variable.
    importlib.reload(paths_mod)

    try:
        assert paths_mod.DATA_DIR == tmp_path
        assert paths_mod.SEQUENCES_DIR.parent == tmp_path
        assert paths_mod.REACTIONS_DIR.parent == tmp_path
        assert paths_mod.FOLDSEEK_DB_DIR.parent == tmp_path
        assert paths_mod.FOLDSEEK_MODELS_DIR.parent == tmp_path
    finally:
        # Restore default module state so other tests importing paths aren't affected.
        importlib.reload(paths_mod)


def test_structures_dir_ignores_etk_data_dir(tmp_path, monkeypatch):
    """``STRUCTURES_DIR`` must NOT be redirected by ``ETK_DATA_DIR``.

    The bundled ``.cif`` files are version-locked to the code that
    consumes them, so they always resolve to the in-source folder.
    """
    import enzyme_tk_app.app.paths as paths_mod

    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path))
    importlib.reload(paths_mod)

    try:
        expected = Path(paths_mod.__file__).resolve().parent / "data" / "structures"
        assert paths_mod.STRUCTURES_DIR.resolve() == expected.resolve()
        # And it must NOT be a child of the override directory.
        assert tmp_path not in paths_mod.STRUCTURES_DIR.parents
    finally:
        importlib.reload(paths_mod)
