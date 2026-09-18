"""Download the model weights and databases the app needs, into its data directory.

Everything lands under DATA_DIR -- the same directory `docker-compose.yml` bind-mounts
read-only at /app-data -- so there is nothing to copy afterwards. Run with no arguments for
the minimal set, `--full` for everything, or name the units you want.

Each unit is idempotent: it prints what it looked for, says FOUND or NOT FOUND, and reuses
whatever is already on disk. Re-running the whole script when everything is present costs
nothing and doubles as a way to see what you have.

  prostt5    ~2 GB    foldseek_models/weights/                minimal
  unimol     ~660 MB  unimol_weights/                         minimal
  funce      ~1.35 GB funce_models/                           minimal
  reactions  ~130 MB  reactions/      (the full EnzymeMap set) --full only
  pdb        ~6.4 GB  foldseek_db/PDB/                        --full only
  afdb       ~3.9 GB  foldseek_db/AFDB_SWISSPROT/             --full only
  esm3       ~5.4 GB  .hf_cache/      (build-time only)       --full only

The minimal set is what a clone cannot ship: model weights. The large foldseek databases and
the full EnzymeMap reference are not in it because data/foldseek_db/ and data/reactions/
already carry demo sets that make those tools runnable, and ESM3 is only needed by
build_enzyme_db.py. The Func-E checkpoints and the EnzymeMap set come from this project's own
Hugging Face dataset (HUGGING_FACE_DATASET_REPO); the rest come from their upstreams.

Nothing here is gated -- no Hugging Face account, token or login is needed.

`sequences/` is the one directory with no download: it holds your own protein tables, beside
the demo set the repository ships. `report()` names it along with everything else the app
reads -- and runs after every invocation, so any run doubles as an inventory. Run in Docker
(see Dockerfile) or locally:

  python download_data.py            # minimal
  python download_data.py --full     # everything
  python download_data.py prostt5    # one unit
"""

import argparse
import csv
import gzip
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Collection
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


# ---- Hugging Face: the project's own dataset, ESM3, UniMol ----

# Everything this project publishes itself lives in one Hugging Face dataset repository, and
# nowhere else -- the Func-E checkpoints and the full EnzymeMap reference today, more later.
HUGGING_FACE_DATASET_REPO = "arianemora/enzyme-tk"


def fetch_dataset_file_from_hugging_face(filename: str, destination: Path) -> Path:
    """Download one file from the project's Hugging Face dataset into `destination`.

    Chosen over a plain URL fetch for **resume and integrity**, not for speed: an interrupted
    1.35 GB download picks up where it stopped, and the result is checked against the
    repository's hash. Measured throughput is about the same as a single-stream `curl` (~33 vs
    ~29 MB/s on the EnzymeMap CSV) -- four concurrent HTTP ranges reach ~55 MB/s, so the Xet
    chunking is not the limiter here; unauthenticated Hub rate limiting is, and a token is
    deliberately not required (see the README's "no account or token needed").

    `local_dir` keeps the bytes here rather than in the Hugging Face cache, so a large file is
    not stored twice. The `.cache/huggingface/` metadata it leaves beside the file is what makes
    resume work; it holds no payload and the app's scans ignore it (they match `*.csv`/`*.pkl`).

    Deliberately only the fetch: every caller already owns its own idea of "already here" --
    a marker file for a plain download, the eight-file list for the Func-E ensemble -- so
    folding those in would make this a parameter soup for two callers.
    """
    from huggingface_hub import hf_hub_download

    destination.mkdir(parents=True, exist_ok=True)
    return Path(
        hf_hub_download(
            repo_id=HUGGING_FACE_DATASET_REPO,
            filename=filename,
            repo_type="dataset",
            local_dir=str(destination),
        )
    )


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

# The published archive, in the project's dataset repository above. It unpacks to ~1.57 GB:
# the eight files `funce_model_files()` names, plus the `_optimizer.pkl` / `_history.pkl` from
# the same training run, which are kept because they are part of the released artifact.
FUNCE_MODELS_FILE = "data_funce.zip"


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


def _extract_archive(archive: Path, destination: Path) -> None:
    """Unpack a .tar.gz or .zip into `destination`, flattening any chain of wrapping directories.

    Archive members are a trust boundary: a crafted entry named `../../etc/x` or `/etc/x` would
    otherwise write outside the data directory. tarfile's "data" filter refuses those (and
    device nodes, setuid bits and links out of the tree); zipfile has no such filter, so the
    same rule is applied by hand.
    """
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as staging:
        staged = Path(staging)
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.namelist():
                    if Path(member).is_absolute() or ".." in Path(member).parts:
                        sys.exit(
                            f"ERROR: refusing to extract {member!r} from {archive.name} - path escapes {destination}."
                        )
                bundle.extractall(staged)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(staged, filter="data")

        # A release archive wraps its payload in folders, and not always just one: the published
        # Func-E zip nests three deep (`data/Funce/models/`). Descend the whole single-directory
        # chain, because the files are wanted at the top of funce_models/ -- that is the one path
        # Func-E's check_data looks in. Stopping after one level would leave them a directory or
        # two down, where nothing would find them.
        root = staged
        while True:
            entries = list(root.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                root = entries[0]
                continue
            break
        for item in root.iterdir():
            target = destination / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))


def download_funce_models() -> None:
    """Func-E ensemble -> data/funce_models/ (~1.35 GB archive, ~1.57 GB unpacked).

    The presence check is the eight files `funce_model_files()` names rather than the archive,
    because the archive is deleted after unpacking and the eight files are what the app looks
    for. A partial ensemble counts as missing, not as most of an answer: Func-E loads one model
    per EC level, so an incomplete set still runs and silently changes every prediction.
    """
    required = funce_model_files()
    print(f"Func-E ensemble: looking for {len(required)} files under {FUNCE_MODELS_DIR}")
    missing = [path for path in required if not path.exists()]
    if not missing:
        print("Func-E ensemble: FOUND - reusing, nothing to download")
        return

    print("Func-E ensemble: NOT FOUND - downloading ~1.35 GB (one time only)")
    # Not a TemporaryDirectory: that is removed on the way out, which would throw away a partial
    # download and make resuming impossible. A dotted name so the app's *.pkl scans never see it.
    staging = FUNCE_MODELS_DIR / ".download"
    archive = fetch_dataset_file_from_hugging_face(FUNCE_MODELS_FILE, staging)
    _extract_archive(archive, FUNCE_MODELS_DIR)

    # Confirmed rather than assumed, for the same reason foldseek_databases() re-checks its
    # marker: an archive that unpacked cleanly but held the wrong layout must not read as done.
    still_missing = [path for path in required if not path.exists()]
    if still_missing:
        # The archive is deliberately left in `staging`: it downloaded fine, so re-fetching
        # 1.35 GB would be punishing the wrong step, and the next run reuses it.
        sys.exit(
            f"ERROR: archive unpacked but {len(still_missing)} file(s) are still missing:\n"
            + "\n".join(f"    {path}" for path in still_missing)
        )

    shutil.rmtree(staging, ignore_errors=True)  # only once the ensemble is provably complete
    print(f"  downloaded to {FUNCE_MODELS_DIR}")


# ---- reactions: the full EnzymeMap reference ----

REACTIONS_FILE = "enzymemap_v2_brenda2023_reactions.csv"


def download_reactions() -> None:
    """Full EnzymeMap reference -> data/reactions/ (~130 MB).

    Not in the minimal set: `reactions/enzymemap_demo_set.csv` ships in the repository and
    already makes both reaction tools runnable, which is the same reason the large FoldSeek
    databases are `--full` only. This is the whole 62,896-reaction set for real work.
    """
    marker = REACTIONS_DIR / REACTIONS_FILE
    if not needs_download("EnzymeMap reactions", marker, "~130 MB"):
        return

    fetch_dataset_file_from_hugging_face(REACTIONS_FILE, REACTIONS_DIR)
    if not marker.exists():
        sys.exit(f"ERROR: {REACTIONS_FILE} downloaded but {marker} is not there.")
    print(f"  downloaded to {marker}")


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


def report(selected: Collection[str] = ()) -> None:
    """Print one line per data item the app looks for, and what supplies it.

    These checks mirror the app's own -- tools/funce/check_data.py,
    tools/sequence_structure_similarity/check_data.py, and SEQUENCE_DB_SUFFIXES /
    REQUIRED_SEQUENCE_COLUMNS in utils/data_loading.py. They are duplicated because this
    script runs in an image without the app package, so a change there is a change here:
    the two disagreeing is worse than neither existing.

    What is listed is what the app needs to run, plus any *build-only* item `selected` asked
    for -- so a new unit goes in the fixed list only if a tool reads what it fetches.
    """
    items = [
        ("sequences/", has_sequence_database(), "ships a demo set; add CSV/TSV with Entry, Sequence, EC number"),
        ("reactions/", has_any(REACTIONS_DIR, "*.csv"), "ships a demo set; download_reactions() for the full set"),
        ("foldseek_db/", has_subdirectory(FOLDSEEK_DB_DIR), "ships a demo set; pdb / afdb units add more"),
        (
            "foldseek_models/weights/",
            (FOLDSEEK_WEIGHTS_DIR / PROSTT5_WEIGHTS_FILE).exists(),
            "download_prostt5_weights()",
        ),
        ("sequence_embeddings/", has_any(SEQUENCE_EMBEDDINGS_DIR, "*.pkl"), "ships a demo set; build_enzyme_db.py"),
        ("funce_models/", all(path.exists() for path in funce_model_files()), "download_funce_models()"),
        ("unimol_weights/", (UNIMOL_WEIGHTS_DIR / UNIMOL_CHECKPOINT).exists(), "download_unimol_weights()"),
    ]
    # ESM3 is not app data -- only build_enzyme_db.py reads it, and no tool is disabled without
    # it. Reporting MISSING against something the run never asked for and the app never opens is
    # how an operator learns to skim past the line that does matter, so it is listed only when
    # the esm3 unit ran -- where it doubles as that unit's post-download check.
    if "esm3" in selected:
        items.append(("ESM3 weights (build only)", esm3_is_cached(), "download_esm3_weights()"))

    print("============================================================")
    print(f"Data directory: {DATA_DIR}")
    for label, present, source in items:
        print(f"  {'OK' if present else 'MISSING':<8} {label:<26} {source}")
    print("============================================================")


# ---- units and tiers ----

UNITS = {
    "prostt5": download_prostt5_weights,
    "unimol": download_unimol_weights,
    "funce": download_funce_models,
    "reactions": download_reactions,
    "pdb": download_foldseek_db_pdb,
    "afdb": download_foldseek_db_afdb_swissprot,
    "esm3": download_esm3_weights,
}

# What a clone cannot ship: model weights. The two big foldseek reference databases and the
# full EnzymeMap set are not here because data/foldseek_db/ and data/reactions/ already carry
# demo sets that make those tools runnable, and ESM3 is only needed to build embeddings from
# your own sequences -- none of them is needed to run a tool. `--full` adds all four.
MINIMAL = ("prostt5", "unimol", "funce")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Download the model weights and databases the app needs, into its data directory.",
        epilog=(
            "default: %(prog)s              ~4.2 GB  the weights every tool needs\n"
            "         %(prog)s --full       ~20 GB   adds the PDB and AFDB/Swiss-Prot databases and ESM3\n"
            "         %(prog)s prostt5      one named unit\n"
            f"units:   {', '.join(UNITS)}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # No `choices=`: argparse renders it as a stray empty option against nargs="*", and its
    # error names the list twice. Validated below instead, which also names every unit once.
    parser.add_argument("units", nargs="*", metavar="UNIT", help="units to run (default: the minimal set)")
    parser.add_argument("--full", action="store_true", help="run every unit, including the large databases")
    args = parser.parse_args(argv)

    if args.units and args.full:
        parser.error("give either --full or a list of units, not both")
    unknown = [name for name in args.units if name not in UNITS]
    if unknown:
        parser.error(f"unknown unit(s) {', '.join(unknown)}; choose from {', '.join(UNITS)}")
    selected = list(UNITS) if args.full else (args.units or list(MINIMAL))

    # Each unit already prints what it is looking for and how big it is; what it cannot know is
    # its place in the run. A --full run is seven units and ~20 GB, so the position and the
    # elapsed time are the difference between "working" and "hung".
    print(f"Downloading {len(selected)} unit(s) into {DATA_DIR}: {', '.join(selected)}")
    for position, name in enumerate(selected, start=1):
        print()
        print("=" * 60)
        print(f"[{position}/{len(selected)}] {name}")
        print("=" * 60)
        started = time.monotonic()
        UNITS[name]()
        print(f"[{position}/{len(selected)}] {name}: done in {time.monotonic() - started:.1f}s")
    print()
    # sequences/ and reactions/ hold your own data too; report() names them with everything else.
    report(selected)


if __name__ == "__main__":
    main()
