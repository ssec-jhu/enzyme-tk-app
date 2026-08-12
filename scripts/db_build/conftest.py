"""Shared fixtures for the scripts/db_build tests.

Both scripts here ship standalone, in a Docker image that does not have the app package
installed, so they are not importable as ``enzyme_tk_app...`` — a test loads them from disk
instead, with :func:`load_db_build_script`.

This directory is put on ``sys.path`` when this file is imported, rather than inside the
loader, because ``build_enzyme_db.py`` imports its sibling by bare name (``from download_data
import ...``).  pytest imports a directory's conftest before the test modules in it, so doing
it here means a test module could import a script at its own top level and still resolve.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

DB_BUILD_DIR = Path(__file__).parent

if str(DB_BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(DB_BUILD_DIR))


def load_db_build_script(name):
    """Load one of the scripts in this directory by path.

    Args:
        name: The module name without ``.py`` — ``"download_data"`` or ``"build_enzyme_db"``.

    Returns:
        A freshly executed module, so edits one test makes to its module-level config
        cannot leak into the next.
    """
    spec = importlib.util.spec_from_file_location(name, DB_BUILD_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def db_build_environment():
    """Unset ``ETK_DATA_DIR`` and ``HF_HOME`` for one test, then put them back as they were.

    Both scripts read the two variables when they are imported, and ``download_data`` writes
    ``HF_HOME`` back — that is how huggingface_hub is pointed at the data directory.  So a
    test that loads a script decides where the *next* one thinks the data and the model cache
    live, and the developer's own shell decides the first one, unless both ends are handled.

    Restored by hand rather than with ``monkeypatch.delenv``, which records nothing to undo
    when a variable was not set in the first place — exactly the case here — and so would let
    the ``HF_HOME`` the script writes outlive the test.
    """
    original = {name: os.environ.get(name) for name in ("ETK_DATA_DIR", "HF_HOME")}
    for name in original:
        os.environ.pop(name, None)

    yield

    for name, value in original.items():
        os.environ.pop(name, None)  # drop whatever the script left behind
        if value is not None:
            os.environ[name] = value
