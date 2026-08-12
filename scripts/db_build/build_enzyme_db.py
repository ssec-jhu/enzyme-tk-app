"""Build enzyme databases for the app from one file of protein sequences.

Two artifacts, from the same input, either or both (see `main()` at the bottom):

  <data>/foldseek_db/<name>/<name>*       -> the Sequence-Structure Similarity tool
  <data>/sequence_embeddings/<name>.pkl   -> the Func-E tool

Both are written straight into the app's data directory (DATA_DIR, from download_data.py),
so there is nothing to copy afterwards -- restart the stack and the tools pick them up.

Input is a CSV or TSV, plain or gzipped, with an `Entry` and a `Sequence` column -- the same
contract the app applies to data/sequences/. Every other column is ignored.

Each artifact needs one model: foldseek's ProstT5 predicts structure from sequence, so no PDB
files are needed, and ESM3-open produces the 1536-d `esm3_mean` column Func-E consumes. Both
are downloaded by `python download_data.py`; this script only checks for them and stops with
that command if one is missing.

Both steps are resumable. The foldseek DB is skipped when it already exists; the embeddings
pickle is topped up, so adding sequences to an input file costs only the new sequences. There
is no maximum sequence length to set -- how long a protein can be is a property of this
machine's memory, so the embedding runs in a child process, shortest sequences first, and any
protein too large to hold is named and skipped rather than killing the run.

Run in Docker (see Dockerfile) or locally: python build_enzyme_db.py
"""

import csv
import gzip
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The sibling script owns where everything lives, so DATA_DIR is defined once. Importing it
# also sets HF_HOME, which has to happen before huggingface_hub is imported anywhere.
from download_data import (
    FOLDSEEK_DB_DIR,
    FOLDSEEK_WEIGHTS_DIR,
    HF_CACHE_DIR,
    PROSTT5_WEIGHTS_FILE,
    SEQUENCE_EMBEDDINGS_DIR,
    esm3_is_cached,
    require_foldseek,
)

# ---- CONFIG: edit these ----
INPUT_FILE = "enzymes_sample_10.tsv"  # CSV/TSV of sequences (.gz ok), relative to this file
LIMIT = 0  # 0 = every sequence; >0 = first N only (quick test)
DEVICE = ""  # ESM3 only: "" = auto (GPU if present), or "cpu" / "cuda"
FORCE = False  # True = rebuild the foldseek DB even if it already exists

HERE = Path(__file__).resolve().parent

# The two input columns, and the exact three columns the app's Func-E tool requires of
# an embeddings pickle. Metadata columns are dropped rather than carried: the full
# enzymes.tsv has 17, and the extra 14 would only make the pickle bigger.
ID_COLUMN = "Entry"
SEQUENCE_COLUMN = "Sequence"
PICKLE_COLUMNS = [ID_COLUMN, SEQUENCE_COLUMN, "esm3_mean"]


def read_sequences(path: Path) -> list[tuple[str, str]]:
    """Read (id, sequence) pairs; blank rows and repeat ids are dropped, LIMIT applied."""
    if not path.exists():
        sys.exit(f"ERROR: input file not found: {path}")

    name = path.name.lower()
    delimiter = "\t" if name.endswith((".tsv", ".tsv.gz")) else ","
    opener = gzip.open if name.endswith(".gz") else open

    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    with opener(path, mode="rt", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = reader.fieldnames or []  # None for an empty file, so default to a list
        missing = [column for column in (ID_COLUMN, SEQUENCE_COLUMN) if column not in fields]
        if missing:
            sys.exit(f"ERROR: {path.name} is missing column(s) {missing}; its columns are {fields}")
        for row in reader:
            seq_id = (row.get(ID_COLUMN) or "").strip()
            sequence = (row.get(SEQUENCE_COLUMN) or "").strip()
            # A repeat id would mean a duplicate FASTA header and a duplicate pickle row.
            if not seq_id or not sequence or seq_id in seen:
                continue
            seen.add(seq_id)
            records.append((seq_id, sequence))
            if LIMIT and len(records) >= LIMIT:
                break

    if not records:
        sys.exit(f"ERROR: no usable sequences in {path.name} (every row had a blank id or sequence).")
    return records


def output_name() -> str:
    """Name both artifacts after the input file: enzymes.tsv.gz -> enzymes."""
    name = Path(INPUT_FILE).name
    for suffix in (".gz", ".tsv", ".csv"):  # .gz first, so a double suffix loses both
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name


# ---- foldseek database ----


def require_prostt5_weights() -> Path:
    """The ProstT5 weights directory, or exit naming the file and how to get it."""
    target = FOLDSEEK_WEIGHTS_DIR / PROSTT5_WEIGHTS_FILE
    if not target.exists():
        sys.exit(f"ERROR: ProstT5 weights not found at {target}.\n       Run: python download_data.py")
    return FOLDSEEK_WEIGHTS_DIR


def build_enzyme_db_foldseek(records: list[tuple[str, str]]) -> None:
    """Sequences -> a foldseek database at <data>/foldseek_db/<name>/<name>.

    The same command enzymetk runs internally (`foldseek createdb --prostt5-model`), which is
    why no structure files are involved.
    """
    print("============================================================")
    print(f"Starting foldseek DB build for {len(records)} sequences...")

    require_foldseek()

    name = output_name()
    db_prefix = FOLDSEEK_DB_DIR / name / name
    if Path(f"{db_prefix}.index").exists() and not FORCE:
        print(f"foldseek DB already exists: {db_prefix}  (set FORCE = True to rebuild)")
        return

    weights_dir = require_prostt5_weights()
    db_prefix.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        fasta_path = Path(tmp) / "ref.fasta"
        with open(fasta_path, "w") as fasta:  # streamed: the full enzymes.tsv is ~230 MB of FASTA
            for seq_id, sequence in records:
                fasta.write(f">{seq_id}\n{sequence}\n")
        print(f"Building foldseek DB '{name}' from {len(records)} sequences...")
        subprocess.run(
            ["foldseek", "createdb", str(fasta_path), str(db_prefix), "--prostt5-model", str(weights_dir)],
            check=True,
        )

    print(f"Done: {db_prefix}")
    print("============================================================")


# ---- ESM3 embeddings ----

CHECKPOINT_EVERY = 250  # sequences per pickle rewrite; an interrupted run loses at most this many
WORKER_FLAG = "--embed-worker"  # internal: re-runs this file as the child process holding the model


def require_esm3_weights() -> None:
    """Exit unless the ESM3 checkpoint is in the Hugging Face cache."""
    if not esm3_is_cached():
        sys.exit(f"ERROR: ESM3 weights not found in {HF_CACHE_DIR}.\n       Run: python download_data.py")


def select_pending(records: list[tuple[str, str]], done_ids: set[str]) -> list[tuple[str, str]]:
    """The (id, sequence) pairs not already embedded, shortest first.

    Shortest first is what makes an out-of-memory kill cheap: everything that fits is
    embedded before anything that does not, so a run gets as far as the host allows and the
    first failure marks the ceiling. Order in the pickle does not matter -- results are
    ranked by score and resuming keys on the id.
    """
    pending = [(seq_id, sequence) for seq_id, sequence in records if seq_id not in done_ids]
    pending.sort(key=lambda record: len(record[1]))
    return pending


def embeddings_path() -> Path:
    """Where the embeddings pickle for this input lives."""
    return SEQUENCE_EMBEDDINGS_DIR / f"{output_name()}.pkl"


def inflight_path() -> Path:
    """Marker naming the sequence currently inside the model.

    The worker writes an id here before handing it to ESM3 and clears it afterwards, so if
    the worker is killed the supervisor can name the sequence that did not fit. A dotfile, so
    it sits beside the pickle without the app's `*.pkl` scan ever seeing it.
    """
    return SEQUENCE_EMBEDDINGS_DIR / f".{output_name()}.inflight"


def ceiling_path() -> Path:
    """The length the supervisor has learned this host cannot embed.

    Written after an out-of-memory kill and read by the next worker, which then leaves those
    sequences alone. Deleted at the start of every run, so a host given more memory simply
    discovers a higher ceiling instead of inheriting yesterday's.
    """
    return SEQUENCE_EMBEDDINGS_DIR / f".{output_name()}.ceiling"


def load_embeddings(pd):
    """Read the existing pickle, or an empty frame with the right columns.

    Takes the pandas module as an argument because it is imported lazily, inside the two
    callers, so that a foldseek-only run never loads it.
    """
    out_path = embeddings_path()
    if not out_path.exists():
        return pd.DataFrame(columns=PICKLE_COLUMNS)
    done = pd.read_pickle(out_path)
    if list(done.columns) != PICKLE_COLUMNS:
        # Rather than a KeyError several lines down, in a script people leave running for days.
        sys.exit(
            f"ERROR: {out_path} has columns {list(done.columns)}, expected {PICKLE_COLUMNS}. Delete it to rebuild."
        )
    return done


def build_enzyme_db_esm3(records: list[tuple[str, str]]) -> None:
    """Sequences -> <data>/sequence_embeddings/<name>.pkl with Entry, Sequence, esm3_mean.

    Supervises a child process that owns the model. A sequence too long for the host's
    memory does not raise -- the kernel sends SIGKILL, which Python cannot catch, so the
    worker dies mid-forward with no traceback. Running it in a child turns that into a
    skipped row and a message instead of a dead run, and because a plain restart would
    retry the same sequence and die identically, an unsupervised script could never get
    past one. How long is too long is a property of this host's memory, not of ESM3, so it
    is discovered here rather than hard-coded.
    """
    import pandas as pd  # imported here so a foldseek-only run needs no heavy dependencies

    out_path = embeddings_path()
    done = load_embeddings(pd)
    pending = select_pending(records, set(done[ID_COLUMN]))
    if not pending:
        print(f"ESM3 embeddings up to date: {out_path} ({len(done)} sequences)")
        return

    require_esm3_weights()  # before the first worker, so a missing model is one message not two
    print(f"Embedding {len(pending)} sequences with ESM3 ({len(done)} already done)...")
    lengths = {seq_id: len(sequence) for seq_id, sequence in records}
    inflight, ceiling = inflight_path(), ceiling_path()
    inflight.parent.mkdir(parents=True, exist_ok=True)
    inflight.unlink(missing_ok=True)
    ceiling.unlink(missing_ok=True)  # rediscovered every run, so more memory means more embedded
    skipped = 0

    # At most two passes: one to find the ceiling, one to finish the sequences below it. The
    # second is not optional -- the worker buffers results between checkpoints, so a kill
    # discards whatever had not been written yet, and without a re-run a short input would
    # lose every embedding it had completed and never produce a pickle at all.
    for _ in range(2):
        worker = subprocess.run([sys.executable, __file__, WORKER_FLAG], check=False)
        done = load_embeddings(pd)
        if worker.returncode == 0:
            break

        culprit = inflight.read_text().strip() if inflight.exists() else ""
        inflight.unlink(missing_ok=True)
        if not culprit or culprit not in lengths:
            sys.exit(f"ERROR: the embedding worker exited with {worker.returncode} and no sequence in flight.")

        # Everything still pending is at least as long as the one that just failed, because
        # the worker takes them shortest first, so none of them will fit either.
        print(f"  skipped {culprit}: out of memory")
        ceiling.write_text(str(lengths[culprit]))
        still_pending = select_pending(records, set(done[ID_COLUMN]))
        skipped = sum(1 for seq_id, _ in still_pending if lengths[seq_id] >= lengths[culprit])
        if skipped > 1:
            print(f"  skipped {skipped - 1} longer sequences for the same reason")

    ceiling.unlink(missing_ok=True)
    print(f"Done: {out_path} ({len(done)} sequences" + (f", {skipped} skipped)" if skipped else ")"))
    if skipped:
        print("Give Docker more memory to raise the ceiling; the next run picks up where this one stopped.")


def embed_worker() -> None:
    """Child process: owns the model and embeds pending sequences, checkpointing as it goes.

    One sequence per ``execute`` call so the in-flight marker names a row rather than a
    chunk; the step embeds one at a time internally either way, so this costs nothing.
    """
    import pandas as pd

    records = read_sequences(HERE / INPUT_FILE)
    done = load_embeddings(pd)
    pending = select_pending(records, set(done[ID_COLUMN]))

    # On a second pass the supervisor has already learned what this host cannot hold; leave
    # those alone rather than being killed by them again.
    ceiling = ceiling_path()
    if ceiling.exists():
        limit = int(ceiling.read_text())
        pending = [record for record in pending if len(record[1]) < limit]
    if not pending:
        return

    from enzymetk.embedprotein_esm3_step import EmbedESM3

    # Constructed once, outside the loop: the model loads in __init__ (several GB resident),
    # so building one step per sequence would reload it every sequence.
    step = EmbedESM3(ID_COLUMN, SEQUENCE_COLUMN, device=DEVICE or None)

    out_path = embeddings_path()
    inflight = inflight_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(done) + len(pending)
    embedded: list = []

    for seq_id, sequence in pending:
        inflight.write_text(seq_id)  # written before the model sees it, cleared once it survives
        frame = step.execute(pd.DataFrame({ID_COLUMN: [seq_id], SEQUENCE_COLUMN: [sequence]}))
        embedded.append(frame[PICKLE_COLUMNS])
        inflight.unlink(missing_ok=True)
        if len(embedded) >= CHECKPOINT_EVERY:
            done = flush(pd, done, embedded, out_path)
            print(f"  checkpointed {len(done)} / {total}")

    if embedded:
        done = flush(pd, done, embedded, out_path)
        print(f"  checkpointed {len(done)} / {total}")


def flush(pd, done, embedded: list, path: Path):
    """Fold the buffered rows into the pickle and empty the buffer."""
    # The empty-frame filter keeps pandas from inferring dtypes off a 0-row frame on the first pass.
    done = pd.concat([frame for frame in (done, *embedded) if not frame.empty], ignore_index=True)
    write_pickle(done, path)
    embedded.clear()
    return done


def write_pickle(frame, path: Path) -> None:
    """Write via a temp file and rename, so a run killed mid-write cannot corrupt the pickle."""
    tmp_path = path.with_suffix(".pkl.tmp")
    frame.to_pickle(tmp_path)
    os.replace(tmp_path, path)


WEIGHTS_ONLY_FLAG = "--weights-only"  # kept only to redirect; the downloads moved to download_data.py


def weights_only_redirect() -> None:
    """Report that --weights-only has moved, and exit non-zero.

    Kept rather than deleted because the dispatch below falls through to `main()`: an
    unrecognised flag would otherwise start a full build instead of saying anything.
    """
    sys.exit(f"{WEIGHTS_ONLY_FLAG} has moved -- the downloads now live next door.\n       Run: python download_data.py")


def main() -> None:
    records = read_sequences(HERE / INPUT_FILE)
    print(f"Read {len(records)} sequences from {INPUT_FILE}")

    build_enzyme_db_foldseek(records)  # comment out to skip the foldseek database
    build_enzyme_db_esm3(records)  # comment out to skip the ESM3 embeddings


if __name__ == "__main__":
    # The worker flag is set only by build_enzyme_db_esm3 when it spawns its child; neither
    # flag is one a user types now that the downloads live in download_data.py.
    if WORKER_FLAG in sys.argv:
        embed_worker()
    elif WEIGHTS_ONLY_FLAG in sys.argv:
        weights_only_redirect()
    else:
        main()
