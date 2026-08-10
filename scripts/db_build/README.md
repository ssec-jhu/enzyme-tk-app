# Enzyme DB builder

Turn one file of protein sequences into the two enzyme databases the app's tools read. Standalone —
its own Docker image with its own `foldseek`, no dependency on the app image.

| Produces | Copy to | Read by |
|---|---|---|
| `output/foldseek_db/<name>/<name>*` | `enzyme_tk_app/app/data/foldseek_db/` | Sequence-Structure Similarity |
| `output/sequence_embeddings/<name>.pkl` | `enzyme_tk_app/app/data/sequence_embeddings/` | Func-E |

The data directory is bind-mounted **read-only** into the containers, so the app can never generate
these itself. This is how you rebuild one you have lost, or add one for a new sequence file.

Input is a **CSV or TSV, plain or gzipped**, with an `Entry` column and a `Sequence` column — the same
contract the app applies to `data/sequences/`. Every other column is ignored, so the full 17-column
`enzymes.tsv` works as-is. `enzymes_sample_10.tsv` ships here as a 10-sequence sample: use it for a first run.

## Run

```bash
docker build -t etk-db-build scripts/db_build
```

```bash
docker run --rm -v "$(pwd)/scripts/db_build:/app" etk-db-build
```

That one mount carries everything: the script, your input file, and `output/` — which is how the
results and the downloaded weights reach the host. Because the script is mounted rather than baked
into the image, **editing the CONFIG block or commenting out a step takes effect on the next run, with
no rebuild.**

Choose which artifacts to build by commenting out lines in `main()` at the bottom of
[`build_enzyme_db.py`](build_enzyme_db.py):

```python
def main():
    records = read_sequences(HERE / INPUT_FILE)
    print(f"Read {len(records)} sequences from {INPUT_FILE}")

    build_enzyme_db_foldseek(records)  # comment out to skip the foldseek database
    build_enzyme_db_esm3(records)  # comment out to skip the ESM3 embeddings
```

Both steps resume. The FoldSeek database is skipped when it already exists (`FORCE = True` rebuilds
it), and the embeddings pickle is topped up rather than recreated — so adding sequences to an input
file costs only the new sequences, and a run you interrupt picks up where it stopped.

## Configure

Edit the CONFIG block at the top of [`build_enzyme_db.py`](build_enzyme_db.py):

| Setting | Default | Meaning |
|---|---|---|
| `INPUT_FILE` | `enzymes_sample_10.tsv` | CSV/TSV of sequences (`.gz` fine), relative to this folder |
| `OUTPUT_DIR` | `output` | Where both artifacts and the downloaded weights land |
| `PROSTT5_WEIGHTS_DIR` | `""` | Existing ProstT5 weights directory; blank downloads into `OUTPUT_DIR` |
| `LIMIT` | `0` | `0` = every sequence; `>0` = first N only, for a quick test |
| `DEVICE` | `""` | ESM3 only: `""` = auto (GPU if present), or `"cpu"` / `"cuda"` |
| `FORCE` | `False` | Rebuild the FoldSeek database even if it already exists |

To use your own file, drop it in this folder and point `INPUT_FILE` at it. Both artifacts are named
after it, with the suffixes removed: `enzymes.tsv.gz` builds `enzymes/` and `enzymes.pkl`.

## Model weights

Each artifact needs one model. Both download once into `output/` and are reused after that, so keep
the mount and the second run costs nothing.

- **ProstT5, ~2 GB** — FoldSeek uses it to predict structure from sequence, which is why no PDB or
  CIF files are involved. **If you already have these weights**, move them into `output/` once and the
  default config finds them, instead of downloading 2 GB again. Both of these hold a copy:

  ```bash
  mkdir -p scripts/db_build/output/foldseek_models && cp -r enzyme_tk_app/app/data/foldseek_models/weights scripts/db_build/output/foldseek_models/
  ```

  `PROSTT5_WEIGHTS_DIR` is for weights kept somewhere else. Note that when running in Docker the path
  has to resolve *inside the container*, so it must point at something under the mount — a relative
  path such as `../foldseek_db_build/...` reaches outside `/app` and will not be found. Either move
  the weights in as above, or mount their directory yourself and give the absolute container path.

- **ESM3-open, ~5.4 GB** — produces the 1536-d `esm3_mean` column. Downloaded anonymously from
  Hugging Face into `output/hf/`; no account or token is needed. Peak memory is ~5.6 GB, so give
  Docker at least **8 GB**.

## ESM3 runtime and memory

The embedding step processes **one sequence at a time** — `EmbedESM3` does no batching. On CPU that
is fine for hundreds of sequences and impractical for hundreds of thousands (`enzymes.tsv` has
575,503, roughly a month of CPU). Two consequences:

- **Start small.** Run the shipped `enzymes_sample_10.tsv` first, or set `LIMIT = 20` on your own file, and
  check the result before committing to a long run.
- **Use a GPU if you have one.** Build with a CUDA wheel and run with `--gpus all`:

  ```bash
  docker build --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124 -t etk-db-build scripts/db_build
  ```

  A GPU is worth more than the wall-clock alone suggests: `logits()` enables
  `autocast(bfloat16)` on CUDA and nowhere else, so a CPU run holds every activation in float32.

### Long proteins are skipped automatically

There is no length limit to configure. How long a protein can be is a property of **your machine's
memory**, not of ESM3 — the model itself has no maximum, since it uses rotary position encoding and
never truncates. Measured on a laptop with 13.6 GB given to Docker: the model alone occupies ~8.7 GB
resident, an 800-residue protein embeds in ~7 s, and **1,200 residues is killed**. With more memory,
more fits.

Running out of memory is a `SIGKILL` from the kernel: no exception, no traceback, nothing the script
can catch. So the embedding runs in a **child process** and the parent supervises it. Sequences are
processed **shortest first**, so everything that fits is embedded and checkpointed before anything
that does not. When the child is killed, the parent names the row and finishes cleanly:

```
  skipped BIG_1600: out of memory
Done: output/sequence_embeddings/oomtest.pkl (2 sequences, 1 skipped)
Give Docker more memory to raise the ceiling; the next run picks up where this one stopped.
```

(actual output from a three-sequence test whose largest protein was 1,600 residues; where many
sequences are over the ceiling a second line reports how many were skipped without being tried)

Everything still pending at that point is at least as long as the one that failed, so it is reported
without being retried. Nothing is lost: the pickle holds every sequence that succeeded, and re-running
after giving Docker more memory picks up exactly where it stopped and embeds more of the tail.

For scale, on the full `enzymes.tsv` the sequences over 2,000 residues are 0.53% of the file and
about 6% of the total compute — and they cost nothing extra on disk, since every protein becomes the
same 1536-float vector however long it is.

## Installing what you build

Copy the artifact into the app's data directory and restart the stack — the tools pick it up on the
next page load:

```bash
cp -r scripts/db_build/output/foldseek_db/enzymes_sample_10 enzyme_tk_app/app/data/foldseek_db/
```

```bash
cp scripts/db_build/output/sequence_embeddings/enzymes_sample_10.pkl enzyme_tk_app/app/data/sequence_embeddings/
```

A database is named on screen exactly as it is named on disk, extension included — `enzymes_sample_10.pkl`
appears in Func-E's Databases dropdown under that name.

## Notes

- `enzymetk` is installed from the `funce-updates` branch, not a pinned commit, because that is the
  only branch whose ESM3 step runs on CPU without an interactive Hugging Face login. pip and the
  Docker layer cache both key on the branch name rather than the commit it resolves to, so use
  `docker build --no-cache` to pick up newer commits from it.
- Running outside Docker works too (`python build_enzyme_db.py`) if `foldseek` is on your `PATH`; the
  ESM3 step additionally needs `torch`, `esm` and `enzymetk` installed. The FoldSeek-only path needs
  nothing but the Python standard library.
