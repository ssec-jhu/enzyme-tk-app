# Enzyme data prep

Get the data the app needs onto disk. Two scripts, one Docker image, no dependency on the app image:

| Script | Does |
|---|---|
| [`download_data.py`](download_data.py) | Downloads the model weights and structure databases the tools read |
| [`build_enzyme_db.py`](build_enzyme_db.py) | Turns **your own** sequence file into a FoldSeek database and an embeddings table |

Everything lands **directly in the app's data directory** — the one `docker-compose.yml` bind-mounts
read-only at `/app-data` — so there is nothing to copy afterwards. Restart the stack and the tools pick
it up on the next page load. That mount is read-only, which is why the app can never produce any of
this itself.

## What you get

### Downloaded by `download_data.py`

Every unit is idempotent: it prints what it looked for, says `FOUND` or `NOT FOUND`, and reuses whatever
is already there. Re-running when everything is present costs nothing and doubles as a way to see what
you have.

| Function | Source | Lands at | Reuse check | Size |
|---|---|---|---|---|
| `download_foldseek_db_pdb()` | `foldseek databases PDB` | `foldseek_db/PDB/PDB*` | `PDB.dbtype` | ~6.4 GB |
| `download_foldseek_db_afdb_swissprot()` | `foldseek databases Alphafold/Swiss-Prot` | `foldseek_db/AFDB_SWISSPROT/*` | `AFDB_SWISSPROT.dbtype` | ~3.9 GB |
| `download_prostt5_weights()` | `foldseek databases ProstT5` | `foldseek_models/weights/prostt5-f16.gguf` | that file | ~2 GB |
| `download_esm3_weights()` | Hugging Face `EvolutionaryScale/esm3-sm-open-v1` | `.hf_cache/` | the checkpoint in the cache | ~5.4 GB |
| `download_unimol_weights()` | Hugging Face `dptech/Uni-Mol2` | `unimol_weights/modelzoo/164M/checkpoint.pt` | that file | ~660 MB |
| `check_funce_models()` | none yet — checks and names what is missing | `funce_models/` | all 8 files | ~1.5 GB |

Nothing here is gated: **no Hugging Face account, token or login is needed.**

Two of these are not app data in the usual sense. The **ESM3** snapshot is a build-time cache only
`build_enzyme_db.py` reads — it goes in a hidden `.hf_cache/` so one mount carries it and it survives
`docker run --rm`, and an `HF_HOME` you already have wins, so a shared model cache is reused instead of
downloading 5.4 GB again. The **Func-E** ensemble has no public source yet, so its unit only checks and
names the eight files it wants, two per EC level:

```
run_easy_0-50_ESRP_{1,2,3,4}_model_1_500000_conf.pkl
run_easy_0-50_ESRP_{1,2,3,4}_model_1_500000_checkpoint.pth
```

(the `_history.pkl` and `_optimizer.pkl` files a training run leaves beside them are another ~600 MB the
app never reads, so they need not be shipped). When those checkpoints are published, that unit becomes a
download in one line.

### Checked and reported, never downloaded

| Item | Path | Comes from |
|---|---|---|
| Sequence tables | `sequences/*.{csv,tsv,csv.gz,tsv.gz}` with `Entry`, `Sequence`, `EC number` | You |
| Reaction tables | `reactions/*.csv` | You |
| Embedding pickles | `sequence_embeddings/*.pkl` | `build_enzyme_db.py` |
| Custom FoldSeek DBs | `foldseek_db/<name>/` | `build_enzyme_db.py` |

`report()` prints one line per item — all ten — as `OK` or `MISSING`, with the function name or `MANUAL`
that supplies it. It runs at the end of every `download_data.py` run, so "what do I still need?" is
answered by running the script with everything commented out:

```
============================================================
Data directory: /app-data
  OK       sequences/                 MANUAL - CSV/TSV with Entry, Sequence, EC number
  MISSING  reactions/                 MANUAL - reaction CSVs
  OK       foldseek_db/               download_foldseek_db_pdb() / _afdb_swissprot()
  ...
============================================================
```

## Run

```bash
docker build -t etk-db-build scripts/db_build
```

```bash
docker run --rm -v "$(pwd)/scripts/db_build:/app" -v "$(pwd)/enzyme_tk_app/app/data:/data" etk-db-build download_data.py
```

Drop the trailing `download_data.py` to run the builder instead — that is the image's default.

Two mounts. `/app` carries the scripts and your input file; `/data` is the app's data directory,
read-write here. Because the scripts are mounted rather than baked into the image, **commenting out a
unit or editing a CONFIG value takes effect on the next run, with no rebuild.**

To write somewhere else — a deployment disk, a scratch volume — change the second mount, or set
`ETK_DATA_DIR`. It is the same variable the app itself reads, so the two cannot drift.

## Choose what runs

Both scripts end in a `main()` that is nothing but a list of units. Comment out what you do not want:

```python
def main():
    download_foldseek_db_pdb()  # comment out to skip
    download_foldseek_db_afdb_swissprot()  # comment out to skip
    download_prostt5_weights()  # comment out to skip
    download_esm3_weights()  # comment out to skip
    download_unimol_weights()  # comment out to skip
    check_funce_models()  # comment out to skip
    # sequences/ and reactions/ are your own data; report() names them with everything else.
    report()
```

```python
def main():
    records = read_sequences(HERE / INPUT_FILE)
    print(f"Read {len(records)} sequences from {INPUT_FILE}")

    build_enzyme_db_foldseek(records)  # comment out to skip the foldseek database
    build_enzyme_db_esm3(records)  # comment out to skip the ESM3 embeddings
```

`download_data.py` has no settings at all — which units run is the only choice it offers.

## Build from your own sequences

Input is a **CSV or TSV, plain or gzipped**, with an `Entry` column and a `Sequence` column — the same
contract the app applies to `data/sequences/`, minus `EC number`. Every other column is ignored, so the
full 17-column `enzymes.tsv` works as-is. `enzymes_sample_10.tsv` ships here as a 10-sequence sample:
use it for a first run.

Edit the CONFIG block at the top of [`build_enzyme_db.py`](build_enzyme_db.py):

| Setting | Default | Meaning |
|---|---|---|
| `INPUT_FILE` | `enzymes_sample_10.tsv` | CSV/TSV of sequences (`.gz` fine), relative to this folder |
| `LIMIT` | `0` | `0` = every sequence; `>0` = first N only, for a quick test |
| `DEVICE` | `""` | ESM3 only: `""` = auto (GPU if present), or `"cpu"` / `"cuda"` |
| `FORCE` | `False` | Rebuild the FoldSeek database even if it already exists |

Both artifacts are named after the input file with the suffixes removed, and a database is named on
screen exactly as it is named on disk: `enzymes.tsv.gz` builds `enzymes/` and `enzymes.pkl`, and
`enzymes.pkl` is what appears in Func-E's Databases dropdown.

Both steps resume. The FoldSeek database is skipped when it already exists (`FORCE = True` rebuilds it),
and the embeddings pickle is topped up rather than recreated — so adding sequences to an input file costs
only the new sequences, and a run you interrupt picks up where it stopped.

The builder downloads nothing. It needs ProstT5 for the database and ESM3 for the embeddings, and if
either is absent it stops and tells you to run `download_data.py`.

## ESM3 runtime and memory

The embedding step processes **one sequence at a time** — `EmbedESM3` does no batching. On CPU that is
fine for hundreds of sequences and impractical for hundreds of thousands (`enzymes.tsv` has 575,503,
roughly a month of CPU). Two consequences:

- **Start small.** Run the shipped `enzymes_sample_10.tsv` first, or set `LIMIT = 20` on your own file,
  and check the result before committing to a long run.
- **Use a GPU if you have one.** Build with a CUDA wheel and run with `--gpus all`:

  ```bash
  docker build --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124 -t etk-db-build scripts/db_build
  ```

  A GPU is worth more than the wall-clock alone suggests: `logits()` enables `autocast(bfloat16)` on
  CUDA and nowhere else, so a CPU run holds every activation in float32.

Peak memory for the ESM3 download and load is ~5.6 GB, so give Docker at least **8 GB**.

### Long proteins are skipped automatically

There is no length limit to configure. How long a protein can be is a property of **your machine's
memory**, not of ESM3 — the model itself has no maximum, since it uses rotary position encoding and
never truncates. Measured on a laptop with 13.6 GB given to Docker: the model alone occupies ~8.7 GB
resident, an 800-residue protein embeds in ~7 s, and **1,200 residues is killed**. With more memory,
more fits.

Running out of memory is a `SIGKILL` from the kernel: no exception, no traceback, nothing the script can
catch. So the embedding runs in a **child process** and the parent supervises it. Sequences are processed
**shortest first**, so everything that fits is embedded and checkpointed before anything that does not.
When the child is killed, the parent names the row and finishes cleanly:

```
  skipped BIG_1600: out of memory
Done: /app-data/sequence_embeddings/oomtest.pkl (2 sequences, 1 skipped)
Give Docker more memory to raise the ceiling; the next run picks up where this one stopped.
```

(actual output from a three-sequence test whose largest protein was 1,600 residues; where many sequences
are over the ceiling a second line reports how many were skipped without being tried)

Everything still pending at that point is at least as long as the one that failed, so it is reported
without being retried. Nothing is lost: the pickle holds every sequence that succeeded, and re-running
after giving Docker more memory picks up exactly where it stopped and embeds more of the tail.

For scale, on the full `enzymes.tsv` the sequences over 2,000 residues are 0.53% of the file and about 6%
of the total compute — and they cost nothing extra on disk, since every protein becomes the same
1536-float vector however long it is.

## Notes

- **The two scripts are one unit.** `build_enzyme_db.py` imports `DATA_DIR` and the path constants from
  `download_data.py`, so both files have to be present even for a build-only run — that is what keeps a
  single definition of where everything lives, and it is why importing the downloader is also what points
  huggingface_hub at the cache. Their tests sit here beside them (`test_download_data.py`,
  `test_enzyme_db_build.py`, `conftest.py`) rather than in the app's suite, because `scripts/` is outside
  the app package; a bare `pytest` from the repo root collects them all the same.
- `enzymetk` is installed from the `funce-updates` branch, not a pinned commit, because that is the only
  branch whose ESM3 step runs on CPU without an interactive Hugging Face login. pip and the Docker layer
  cache both key on the branch name rather than the commit it resolves to, so use `docker build
  --no-cache` to pick up newer commits from it.
- Running outside Docker works too (`python download_data.py`, `python build_enzyme_db.py`) if `foldseek`
  is on your `PATH`; with no `ETK_DATA_DIR` set, both default to this repo's own
  `enzyme_tk_app/app/data`. The ESM3 step additionally needs `torch`, `esm` and `enzymetk` installed. The
  FoldSeek-only path needs nothing but the standard library.
- The UniMol checkpoint is fetched straight from the repository `unimol_tools` itself downloads from, so
  that package — and resolving its dependencies against this image's pinned torch — is not needed here.
  Func-E names the path explicitly, which is what stops `unimol_tools` downloading its own copy into
  site-packages on every fresh container.
