"""Centralised path constants for the EnzymeTK application.

All shared data-directory paths are defined here as ``Path`` objects.
The root ``DATA_DIR`` is overridable via the ``ETK_DATA_DIR`` environment
variable, allowing Docker deployments (or local dev) to mount data at a
custom location without modifying source code.

``STRUCTURES_DIR`` is the one exception: it is always pinned to the
``structures/`` folder bundled with the source tree, because those
``.cif`` files are version-locked to the code that consumes them and ship
inside the Docker image.

Tool-specific paths that are only used within a single tool module should
**not** live here — they derive from ``DATA_DIR`` in their own file.
"""

import os
from pathlib import Path

# In-source data directory bundled with the package.  Used as the default
# for ``DATA_DIR`` and as the fixed root for "STRUCTURES_DIR``.
_SOURCE_DATA_DIR: Path = Path(__file__).parent / "data"

# Root data directory.  Defaults to the ``data/`` folder bundled with the
# source tree (sibling to this file).  Override with ``ETK_DATA_DIR`` to
# point at a user-mounted or shared volume.
DATA_DIR: Path = Path(os.environ.get("ETK_DATA_DIR", str(_SOURCE_DATA_DIR)))

# Protein sequence CSV databases.
SEQUENCES_DIR: Path = DATA_DIR / "sequences"

# Reaction CSV databases.
REACTIONS_DIR: Path = DATA_DIR / "reactions"

# Bundled protein structure files (.pdb / .cif).  Always fixed to the
# ``structures/`` folder in the source tree — never overridden by
# ``ETK_DATA_DIR``.
STRUCTURES_DIR: Path = _SOURCE_DATA_DIR / "structures"

# Pre-built FoldSeek databases (one sub-directory per database).
FOLDSEEK_DB_DIR: Path = DATA_DIR / "foldseek_db"

# FoldSeek model weights (e.g. ProstT5).  Anticipated for future tools;
# follows the same override semantics as the other external-tier paths.
FOLDSEEK_MODELS_DIR: Path = DATA_DIR / "foldseek_models"
