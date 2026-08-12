# foldseek DB builder

Build a foldseek database from a CSV of protein sequences. Standalone — its own Docker
image with its own `foldseek`, no dependency on the app. It reads an ID column and an
amino-acid sequence column from the CSV and runs foldseek's ProstT5 pipeline to produce a
reusable database. No structure/PDB files needed — ProstT5 predicts structure from sequence.

## Run

```bash
docker build -t foldseek-db-build scripts/foldseek_db_build
docker run -v "$(pwd)/scripts/foldseek_db_build/output:/app/output" foldseek-db-build
```

The DB lands on the host at `scripts/foldseek_db_build/output/foldseek_db/<name>/<name>`
(`<name>` = the CSV filename, or `DB_NAME`). The `-v` mount is what carries the DB — and the
downloaded ProstT5 weights — back out of the container to the host.

The first run downloads the ProstT5 weights (~2 GB) into `output/foldseek_models/weights/`;
later runs reuse them.

## Configure

Edit the CONFIG block at the top of [`build_db.py`](build_db.py):

- `CSV_PATH` — CSV to build from, relative to the script. One ships in this folder:
  **`protein_5.csv`** (5-sequence sample — use it for a quick test)
- `ID_COLUMN` / `SEQUENCE_COLUMN` — the ID and amino-acid columns (default `Entry` / `Sequence`).
- `DB_NAME` — output DB name; blank ⇒ the CSV filename stem.
- `OUTPUT_DIR` — where the DB and downloaded weights go (default `output`).
- `WEIGHTS_DIR` — path to existing ProstT5 weights; blank ⇒ download into `OUTPUT_DIR`.
- `FORCE` — `True` rebuilds even if the DB already exists.

To use your own CSV: drop it in this folder and point `CSV_PATH` at it, then rebuild — the
[`Dockerfile`](Dockerfile) bakes in every `*.csv` here, so no Dockerfile edit is needed.

