"""Centralised path constants for the EnzymeTK application.

All shared data-directory paths are defined here as ``Path`` objects.
The root ``DATA_DIR`` is overridable via the ``ETK_DATA_DIR`` environment
variable, allowing Docker deployments (or local dev) to mount data at a
custom location without modifying source code.

Tool-specific paths that are only used within a single tool module should
**not** live here — they derive from ``DATA_DIR`` in their own file.
FoldSeek model assets (weights, databases) are considered shared app data
because they are large, versioned independently of any single tool, and may
be reused by future tools — so their paths are defined here.
"""

import os
from pathlib import Path

# Root data directory.  Defaults to the ``data/`` folder bundled with the
# source tree (sibling to this file).  Override with ``ETK_DATA_DIR`` to
# point at a user-mounted or shared volume.
DATA_DIR: Path = Path(os.environ.get("ETK_DATA_DIR", str(Path(__file__).parent / "data")))

# Protein sequence CSV databases.
SEQUENCES_DIR: Path = DATA_DIR / "sequences"

# Reaction CSV databases.
REACTIONS_DIR: Path = DATA_DIR / "reactions"

# Bundled protein structure files (.pdb / .cif).
STRUCTURES_DIR: Path = DATA_DIR / "structures"

# Pre-built FoldSeek databases (one sub-directory per database).
FOLDSEEK_DB_DIR: Path = DATA_DIR / "foldseek_db"

# ProstT5 model weights used by FoldSeek for sequence-based searches.
FOLDSEEK_WEIGHTS_DIR: Path = DATA_DIR / "foldseek_models" / "weights"
