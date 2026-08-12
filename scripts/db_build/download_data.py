"""Download the model weights and databases the app needs, into its data directory.

Everything lands under DATA_DIR -- the same directory `docker-compose.yml` bind-mounts
read-only at /app-data -- so there is nothing to copy afterwards. Pick what you want by
commenting out lines in `main()` at the bottom; every unit is a function of its own.

Each unit is idempotent: it prints what it looked for, says FOUND or NOT FOUND, and reuses
whatever is already on disk. Re-running the whole script when everything is present costs
nothing and doubles as a way to see what you have.

  1. download_foldseek_db_pdb()             ~6.4 GB  foldseek_db/PDB/
  2. download_foldseek_db_afdb_swissprot()  ~3.9 GB  foldseek_db/AFDB_SWISSPROT/
  3. download_prostt5_weights()             ~2 GB    foldseek_models/weights/
  4. download_esm3_weights()                ~5.4 GB  .hf_cache/       (build-time only)
  5. download_unimol_weights()              ~660 MB  unimol_weights/
  6. check_funce_models()                   ~1.5 GB  funce_models/    (no public source yet)

Nothing here is gated -- no Hugging Face account, token or login is needed.

`sequences/` and `reactions/` hold your own data and are not downloaded; `report()` names
them along with everything else. Run in Docker (see Dockerfile) or locally:
python download_data.py
"""

import csv
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The same environment variable the app reads (enzyme_tk_app/app/paths.py), so a deployment
# that already sets it needs no edit here; the Dockerfile sets it to the mount. Falling back
# to the repo's own data directory means a host run needs no edit either.
DATA_DIR = Path(os.environ.get("ETK_DATA_DIR") or HERE.parents[1] / "enzyme_tk_app" / "app" / "data")

# The ESM3 snapshot: a build-time cache only build_enzyme_db.py reads, never the app. It
# defaults inside DATA_DIR so one mount carries it and it survives `docker run --rm`, and it is
# hidden so it cannot be mistaken for app data. An HF_HOME already set wins, so a machine with
# a shared model cache reuses it rather than downloading 5.4 GB again -- and reading it back
# out is what keeps the paths in the messages and in report() honest. Set at module level
# because huggingface_hub freezes its cache paths at import time, so this is the one place the
# location is decided, for this script and for build_enzyme_db.py alike.
HF_CACHE_DIR = Path(os.environ.get("HF_HOME") or DATA_DIR / ".hf_cache")
os.environ["HF_HOME"] = str(HF_CACHE_DIR)

# Mirrors enzyme_tk_app/app/paths.py. Duplicated rather than imported: this script ships
# standalone, in an image that does not have the app package installed.
SEQUENCES_DIR = DATA_DIR / "sequences"
REACTIONS_DIR = DATA_DIR / "reactions"
FOLDSEEK_DB_DIR = DATA_DIR / "foldseek_db"
FOLDSEEK_WEIGHTS_DIR = DATA_DIR / "foldseek_models" / "weights"
SEQUENCE_EMBEDDINGS_DIR = DATA_DIR / "sequence_embeddings"
FUNCE_MODELS_DIR = DATA_DIR / "funce_models"
UNIMOL_WEIGHTS_DIR = DATA_DIR / "unimol_weights"


def needs_download(label: str, marker: Path, size: str) -> bool:
    """Print the lookup and return True when `marker` is absent, so the caller downloads.

    Every unit checks one file rather than the folder holding it: an interrupted download
    leaves the folder behind, which would read as "found" right up until something tried to
    open what is not in it.
    """
    print(f"{label}: looking for {marker}")
    if marker.exists():
        print(f"{label}: FOUND - reusing, nothing to download")
        return False
    print(f"{label}: NOT FOUND - downloading {size} (one time only)")
    return True


# ---- foldseek: structure databases and the ProstT5 weights ----

PROSTT5_WEIGHTS_FILE = "prostt5-f16.gguf"


def require_foldseek() -> None:
    """Exit unless the foldseek binary is on PATH -- it is the downloader, not just the builder."""
    if shutil.which("foldseek") is None:
        sys.exit("ERROR: `foldseek` not found on PATH - run inside the Docker image or install foldseek.")


def foldseek_databases(name: str, destination: Path, marker: Path) -> None:
    """Run `foldseek databases <name>` and confirm the file it should have left behind."""
    require_foldseek()
    marker.parent.mkdir(parents=True, exist_ok=True)
    # foldseek's scratch directory, kept beside the destination rather than in /tmp: it holds
    # the whole archive mid-download, which is several GB the container's /tmp may not have.
    with tempfile.TemporaryDirectory(dir=marker.parent) as tmp:
        subprocess.run(["foldseek", "databases", name, str(destination), tmp], check=True)
    # Confirmed rather than assumed: foldseek exiting 0 without leaving the file here would
    # otherwise be reported as a successful download and fail much later, inside a search.
    if not marker.exists():
        sys.exit(f"ERROR: foldseek reported success but {marker} is not there.")
    print(f"  downloaded to {marker.parent}")


def download_foldseek_db(folder: str, foldseek_name: str, size: str) -> None:
    """Download one of foldseek's own structure databases into data/foldseek_db/<folder>/.

    Args:
        folder: The directory name, which is also the name the app shows and the
            ``FoldSeekDatabase`` enum member enzymetk maps it to.
        foldseek_name: What ``foldseek databases`` accepts, which is not always the same
            string -- AFDB_SWISSPROT is downloaded as "Alphafold/Swiss-Prot".
        size: Download size, for the message only.
    """
    prefix = FOLDSEEK_DB_DIR / folder / folder
    marker = Path(f"{prefix}.dbtype")
    if needs_download(f"FoldSeek {folder} database", marker, size):
        foldseek_databases(foldseek_name, prefix, marker)


def download_foldseek_db_pdb() -> None:
    """The PDB structure database -> data/foldseek_db/PDB/ (~6.4 GB)."""
    download_foldseek_db("PDB", "PDB", "~6.4 GB")


def download_foldseek_db_afdb_swissprot() -> None:
    """The AlphaFold/Swiss-Prot structure database -> data/foldseek_db/AFDB_SWISSPROT/ (~3.9 GB)."""
    download_foldseek_db("AFDB_SWISSPROT", "Alphafold/Swiss-Prot", "~3.9 GB")


def download_prostt5_weights() -> None:
    """ProstT5 -> data/foldseek_models/weights/ (~2 GB).

    FoldSeek predicts structure from sequence with it, which is why building a database from
    a sequence file needs no PDB or CIF files at all.
    """
    marker = FOLDSEEK_WEIGHTS_DIR / PROSTT5_WEIGHTS_FILE
    if needs_download("ProstT5 weights", marker, "~2 GB"):
        # The destination is the directory itself here, not a database prefix.
        foldseek_databases("ProstT5", FOLDSEEK_WEIGHTS_DIR, marker)


# ---- Hugging Face: ESM3, UniMol ----

ESM3_REPO = "EvolutionaryScale/esm3-sm-open-v1"
ESM3_WEIGHTS_FILE = "data/weights/esm3_sm_open_v1.pth"  # the checkpoint ESM3.from_pretrained loads

UNIMOL_REPO = "dptech/Uni-Mol2"
# Not ours to choose: unimol_tools resolves this as MODEL_CONFIG_V2["weight"]["164m"] under
# whatever weights_dir it is handed, and Func-E hands it data/unimol_weights/.
UNIMOL_CHECKPOINT = "modelzoo/164M/checkpoint.pt"


def esm3_is_cached() -> bool:
    """True when the ESM3 checkpoint is already in the Hugging Face cache.

    The import is guarded so `report()` still runs on a host with no huggingface_hub -- the
    FoldSeek-only path needs nothing but the standard library.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(ESM3_REPO, filename=ESM3_WEIGHTS_FILE), str)


def download_esm3_weights() -> None:
    """ESM3-open -> the Hugging Face cache (~5.4 GB).

    Only build_enzyme_db.py reads this, to produce the 1536-d `esm3_mean` column; the app
    never touches it. Returning early really does skip the network: ESM3.from_pretrained
    reaches data_root(), which runs its own snapshot_download, so anything missing beyond
    this checkpoint is still fetched by the constructor and a complete cache needs no request.
    """
    print(f"ESM3 weights: looking for {ESM3_REPO}/{ESM3_WEIGHTS_FILE} under {HF_CACHE_DIR}")
    if esm3_is_cached():
        print("ESM3 weights: FOUND - reusing, nothing to download")
        return

    print(f"ESM3 weights: NOT FOUND - downloading ~5.4 GB into {HF_CACHE_DIR} (one time only)")
    from huggingface_hub import snapshot_download

    print(f"  downloaded to {snapshot_download(repo_id=ESM3_REPO)}")


def download_unimol_weights() -> None:
    """UniMol v2 164M -> data/unimol_weights/modelzoo/164M/checkpoint.pt (~660 MB).

    Fetched straight from the repository unimol_tools itself downloads from, so the package
    -- and resolving its dependencies against this image's pinned torch -- is not needed here.
    Func-E names this path explicitly, which is what stops unimol_tools downloading its own
    copy into site-packages on every fresh container.
    """
    marker = UNIMOL_WEIGHTS_DIR / UNIMOL_CHECKPOINT
    if not needs_download("UniMol 164M weights", marker, "~660 MB"):
        return

    from huggingface_hub import snapshot_download

    # allow_patterns: the repo also holds the 84M, 310M, 570M and 1.1B checkpoints, and a bare
    # snapshot_download would fetch all five.
    snapshot_download(repo_id=UNIMOL_REPO, local_dir=UNIMOL_WEIGHTS_DIR, allow_patterns=UNIMOL_CHECKPOINT)
    if not marker.exists():
        sys.exit(f"ERROR: {UNIMOL_REPO} downloaded but {marker} is not there.")
    print(f"  downloaded to {marker}")


# ---- Func-E ensemble ----

FUNCE_EC_LEVELS = (1, 2, 3, 4)
FUNCE_CHECKPOINT_STEM = "run_easy_0-50_ESRP_{ec}_model_1_500000"


def funce_model_files() -> list[Path]:
    """The eight files Func-E requires: a config and a checkpoint per EC level.

    The `_history.pkl` and `_optimizer.pkl` files that sit beside them in a training run are
    another ~600 MB the app never reads, so they need not be shipped.
    """
    return [
        FUNCE_MODELS_DIR / f"{FUNCE_CHECKPOINT_STEM.format(ec=ec)}_{suffix}"
        for ec in FUNCE_EC_LEVELS
        for suffix in ("conf.pkl", "checkpoint.pth")
    ]


def check_funce_models() -> None:
    """Report the Func-E ensemble (~1.5 GB); there is no public source to download it from yet.

    A check rather than a download, and a named unit rather than a line in `report()`, because
    this is where the download goes when the checkpoints are published: one snapshot_download
    into FUNCE_MODELS_DIR, in the shape of `download_unimol_weights()` above.
    """
    required = funce_model_files()
    print(f"Func-E ensemble: looking for {len(required)} files under {FUNCE_MODELS_DIR}")
    missing = [path for path in required if not path.exists()]
    if not missing:
        print("Func-E ensemble: FOUND - reusing, nothing to download")
        return

    # A partial ensemble is treated as missing, not as most of an answer: Func-E loads one
    # model per EC level, so an incomplete set still runs and silently changes the prediction.
    print(f"Func-E ensemble: NOT FOUND - no public download yet; copy {len(missing)} file(s) in by hand:")
    for path in missing:
        print(f"    {path}")


# ---- report ----

# Mirrors utils/data_loading.py: a file in sequences/ is a sequence database only when its
# extension is one of these *and* its header carries all three columns.
SEQUENCE_DB_SUFFIXES = (".csv", ".tsv", ".csv.gz", ".tsv.gz")
REQUIRED_SEQUENCE_COLUMNS = ("Entry", "Sequence", "EC number")


def has_sequence_database() -> bool:
    """True when sequences/ holds a table carrying every one of REQUIRED_SEQUENCE_COLUMNS."""
    if not SEQUENCES_DIR.exists():
        return False
    for path in sorted(SEQUENCES_DIR.iterdir()):
        if not path.is_file() or not path.name.endswith(SEQUENCE_DB_SUFFIXES):
            continue
        name = path.name.lower()
        opener = gzip.open if name.endswith(".gz") else open
        stem = name[: -len(".gz")] if name.endswith(".gz") else name
        try:
            with opener(path, mode="rt", newline="") as handle:
                fields = csv.DictReader(handle, delimiter="\t" if stem.endswith(".tsv") else ",").fieldnames or []
        except (OSError, UnicodeDecodeError, csv.Error):
            continue  # unreadable is not a database; the app skips it and names it too
        if all(column in fields for column in REQUIRED_SEQUENCE_COLUMNS):
            return True
    return False


def has_subdirectory(path: Path) -> bool:
    """True when `path` exists and holds at least one non-hidden subdirectory."""
    return path.exists() and any(entry.is_dir() and not entry.name.startswith(".") for entry in path.iterdir())


def has_any(path: Path, pattern: str) -> bool:
    """True when `path` exists and something in it matches `pattern`."""
    return path.exists() and any(path.glob(pattern))


def report() -> None:
    """Print one line per data item the app looks for, and what supplies it.

    These checks mirror the app's own -- tools/funce/check_data.py,
    tools/sequence_structure_similarity/check_data.py, and SEQUENCE_DB_SUFFIXES /
    REQUIRED_SEQUENCE_COLUMNS in utils/data_loading.py. They are duplicated because this
    script runs in an image without the app package, so a change there is a change here:
    the two disagreeing is worse than neither existing.
    """
    items = [
        ("sequences/", has_sequence_database(), "MANUAL - CSV/TSV with Entry, Sequence, EC number"),
        ("reactions/", has_any(REACTIONS_DIR, "*.csv"), "MANUAL - reaction CSVs"),
        ("foldseek_db/", has_subdirectory(FOLDSEEK_DB_DIR), "download_foldseek_db_pdb() / _afdb_swissprot()"),
        (
            "foldseek_models/weights/",
            (FOLDSEEK_WEIGHTS_DIR / PROSTT5_WEIGHTS_FILE).exists(),
            "download_prostt5_weights()",
        ),
        ("sequence_embeddings/", has_any(SEQUENCE_EMBEDDINGS_DIR, "*.pkl"), "build_enzyme_db.py"),
        ("funce_models/", all(path.exists() for path in funce_model_files()), "MANUAL - see check_funce_models()"),
        ("unimol_weights/", (UNIMOL_WEIGHTS_DIR / UNIMOL_CHECKPOINT).exists(), "download_unimol_weights()"),
        ("ESM3 weights (build only)", esm3_is_cached(), "download_esm3_weights()"),
    ]

    print("============================================================")
    print(f"Data directory: {DATA_DIR}")
    for label, present, source in items:
        print(f"  {'OK' if present else 'MISSING':<8} {label:<26} {source}")
    print("============================================================")


def main() -> None:
    download_foldseek_db_pdb()  # comment out to skip
    download_foldseek_db_afdb_swissprot()  # comment out to skip
    download_prostt5_weights()  # comment out to skip
    download_esm3_weights()  # comment out to skip
    download_unimol_weights()  # comment out to skip
    check_funce_models()  # comment out to skip
    # sequences/ and reactions/ are your own data; report() names them with everything else.
    report()


if __name__ == "__main__":
    main()
