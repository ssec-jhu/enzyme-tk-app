"""Build a foldseek database from a CSV of protein sequences.

Standalone: needs only Python 3 (stdlib) and the `foldseek` binary on PATH.
Edit the CONFIG block, then run in Docker (see Dockerfile) or locally:  python build_db.py
Output DB lands at:  <OUTPUT_DIR>/foldseek_db/<name>/<name>

Under the hood this is the same two commands enzymetk runs internally:
  1. foldseek databases ProstT5 <weights_dir> <tmp>          # one-time weights download
  2. foldseek createdb <ref.fasta> <db_prefix> --prostt5-model <weights_dir>
ProstT5 predicts structure from sequence, so no PDB/structure files are needed.
"""

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---- CONFIG: edit these ----
CSV_PATH = "protein.csv"  # CSV of sequences, relative to this file
ID_COLUMN = "Entry"  # column holding the protein ID
SEQUENCE_COLUMN = "Sequence"  # column holding the amino-acid sequence
DB_NAME = ""  # DB name; blank => use the CSV filename stem
OUTPUT_DIR = "output"  # DB (and downloaded weights, if any) go here (mount this to get them out)
WEIGHTS_DIR = ""  # path to existing ProstT5 weights dir; blank => download into OUTPUT_DIR
FORCE = False  # True = rebuild even if the DB already exists

HERE = Path(__file__).resolve().parent


def write_fasta(csv_path: Path, fasta_path: Path) -> int:
    """Write one FASTA record per non-blank sequence; return the record count."""
    count = 0
    with open(csv_path, newline="") as handle:
        reader = csv.DictReader(handle)
        if ID_COLUMN not in reader.fieldnames or SEQUENCE_COLUMN not in reader.fieldnames:
            sys.exit(f"ERROR: CSV must have columns {ID_COLUMN!r} and {SEQUENCE_COLUMN!r}; got {reader.fieldnames}")
        with open(fasta_path, "w") as fasta:
            for row in reader:
                seq = (row.get(SEQUENCE_COLUMN) or "").strip()
                seq_id = (row.get(ID_COLUMN) or "").strip()
                if not seq or not seq_id:  # skip rows missing an id or a sequence
                    continue
                fasta.write(f">{seq_id}\n{seq}\n")
                count += 1
    return count


def main() -> None:

    # ensure foldseek is available on the PATH
    if shutil.which("foldseek") is None:
        sys.exit("ERROR: `foldseek` not found on PATH - run inside the Docker image or install foldseek.")

    csv_path = HERE / CSV_PATH
    if not csv_path.exists():
        sys.exit(f"ERROR: CSV not found: {csv_path}")

    name = DB_NAME or csv_path.stem

    # WEIGHTS_DIR wins if set (absolute or relative to this file); else weights live under OUTPUT_DIR.
    weights_dir = (HERE / WEIGHTS_DIR) if WEIGHTS_DIR else HERE / OUTPUT_DIR / "foldseek_models" / "weights"
    db_prefix = HERE / OUTPUT_DIR / "foldseek_db" / name / name

    # skip building if the DB already exists and FORCE is not set
    if Path(f"{db_prefix}.index").exists() and not FORCE:
        print(f"DB already exists: {db_prefix}  (set FORCE=True to rebuild)")
        return

    weights_dir.mkdir(parents=True, exist_ok=True)
    db_prefix.parent.mkdir(parents=True, exist_ok=True)

    # ProstT5 weights: download once, then reuse from OUTPUT_DIR on every later run.
    if not (weights_dir / "prostt5-f16.gguf").exists():
        print("Downloading ProstT5 weights (one-time, hundreds of MB)...")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["foldseek", "databases", "ProstT5", str(weights_dir), tmp], check=True)

    # build the foldseek database from the CSV sequences
    with tempfile.TemporaryDirectory() as tmp:
        fasta_path = Path(tmp) / "ref.fasta"
        n = write_fasta(csv_path, fasta_path)
        if n == 0:
            sys.exit(f"ERROR: no usable sequences in {csv_path} (all rows had a blank id or sequence).")
        print(f"Building foldseek DB '{name}' from {n} sequences...")
        subprocess.run(
            ["foldseek", "createdb", str(fasta_path), str(db_prefix), "--prostt5-model", str(weights_dir)],
            check=True,
        )

    print(f"Done. DB at: {db_prefix}")


if __name__ == "__main__":
    main()
