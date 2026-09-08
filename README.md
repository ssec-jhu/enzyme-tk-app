# SSEC-JHU EnzymeTK Tool Suite

[![CI](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/ci.yml/badge.svg)](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/ci.yml)
[![Documentation Status](https://readthedocs.org/projects/ssec-jhu-enzyme-tk-app/badge/?version=latest)](https://ssec-jhu-enzyme-tk-app.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/ssec-jhu/enzyme-tk-app/branch/main/graph/badge.svg?token=wQvM7PcGbX)](https://codecov.io/gh/ssec-jhu/enzyme-tk-app)
[![Security](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/security.yml/badge.svg)](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/security.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.14052740.svg)](https://doi.org/10.5281/zenodo.14052740)


![SSEC-JHU Logo](docs/_static/SSEC_logo_horiz_blue_1152x263.png)

A web application for protein engineering workflows, built with [Dash](https://dash.plotly.com/) (Plotly) and backed by [Celery](https://docs.celeryq.dev/) for asynchronous job processing. It provides a suite of bioinformatics tools that scientists can launch from the browser and monitor through a job-management dashboard.


## Available Tools

| Tool | Description | Key Libraries |
|------|-------------|---------------|
| **Reaction Similarity** | Reaction similarity search using RDKit structural reaction fingerprints | `rdkit` |
| **Substrate/Product Similarity** | Molecular similarity search using Morgan circular fingerprints with Tanimoto, Russell, and Cosine scoring | `rdkit` |
| **Sequence Similarity** | Protein sequence similarity search using DIAMOND BLASTp. Searches one or more reference sequence databases, merged into a single index so hits are ranked globally | `diamond-blastp` |
| **Sequence and Structure-Based Similarity** | FoldSeek-powered similarity search using protein sequences (ProstT5) or structures (CIF/PDB). Searches across multiple databases including PDB and AlphaFold/Swiss-Prot | `foldseek`, `prostt5` |
| **Func-E Activity Prediction** | Scores (enzyme, reaction) pairs with an ensemble of four attention models — one per EC level. Encodes the query reaction at run time and ranks a pre-encoded protein embedding database by predicted activity | `torch`, `rxnfp`, `unimol` |
| **Timer Tool Template** | A demo tool for testing the job scheduling backend | — |

> **Func-E encodes the query reaction in the worker.** Any valid reaction SMILES can be
> scored — no pre-encoded pair needed: RxnFP fingerprints the reaction and UniMol embeds its
> substrate and product, all inside `enzymetk`'s `Funce_rxnfp_unimol` step. A dot-joined
> side (`A.B>>C`) is embedded one molecule at a time and summed, so multi-substrate
> reactions work; leaving groups are still better left out. The **protein** side is
> still encoded offline — Func-E ranks only proteins already present in a
> `data/sequence_embeddings/` pickle. Encoding needs the UniMol checkpoint under
> `data/unimol_weights/`; without it the tool card shows a **"Missing data"** badge (see
> [Data Directories](#data-directories)). The app never downloads it.

![EnzymeTK App](enzyme_tk_app/app/assets/app.jpeg)


New tools are auto-discovered — add a sub-package under `enzyme_tk_app/app/tools/` and it appears on the home page automatically. See the [Developer Guide](docs/developer-guide.md) for the full walkthrough.

## Quickstart

```bash
git clone https://github.com/ssec-jhu/enzyme-tk-app
cd enzyme-tk-app
docker compose up --build
```

The app is available at **http://localhost:8050**. This starts four services — the web server, Redis, 3 Celery workers, and a single-replica Celery `beat` scheduler (runs the periodic orphan-sweep) — everything needed to submit and run jobs.

```bash
docker compose up --build -d     # detached means it will run in the background and terminal is free
docker compose down -v           # stop and remove volumes
```

Pull pre-built images: `docker pull ghcr.io/ssec-jhu/enzyme-tk-app:<tag>`

## Configuration

### Admin Secrets (`.env`)

The hidden `/admin` dashboard is gated by two secrets that live in a gitignored
`.env` file at the repository root. Generate it with fresh random values:

```bash
./scripts/generate-env.sh
```

This writes `.env` with a random `ETK_ADMIN_TOKEN` (the login token) and
`ETK_SECRET_KEY` (used to sign the admin session cookie). Re-run the script to
rotate the secrets — it prompts before overwriting an existing `.env`. **Never
commit `.env`.** If the secrets are left unset, the admin login fails closed.

### Environment Variables

All configuration is via environment variables, read by `enzyme_tk_app/app/backend/config.py`.
`docker-compose.yml` sets them **per service**, not globally: `web` and `worker` share the runtime
variables, `beat` takes only the sweep interval, and the three admin variables go to **`web` alone**
— nothing the worker runs serves `/admin`. Anything compose leaves unset falls back to the default below.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (broker + result backend) |
| `JOB_TTL_SECONDS` | `86400` (24 h) | How long job metadata is retained in Redis |
| `JOB_OUTPUTS_PATH` | `/job-outputs` | Directory for offloaded result + log files (shared volume between web + worker) |
| `CELERY_SWEEP_INTERVAL_SECONDS` | `86400` (24 h) | How often Celery beat sweeps orphaned output dirs (clamped to ≥ 1) |
| `ETK_DATA_DIR` | `enzyme_tk_app/app/data` (compose sets `/app-data`) | Root of the read-only tool data mount; every data directory below derives from it (`enzyme_tk_app/app/paths.py`) |
| `ETK_ADMIN_TOKEN` | *(empty)* | Login token for `/admin`. Empty means the login **fails closed** and the dashboard is unreachable. `web` only |
| `ETK_SECRET_KEY` | *(empty)* | Signs the admin session cookie. Required whenever `ETK_ADMIN_TOKEN` is set — the app refuses to start otherwise. Unset with no token: a random per-process key, so admins are logged out on restart. `web` only |
| `ETK_ADMIN_SESSION_TTL_SECONDS` | `300` (5 min) | Sliding idle window for an unlocked admin session. Every authenticated check slides it forward, including the dashboard's 10 s poll, so an open tab never expires. `web` only |

Both session cookies are always sent with `Secure`, `HttpOnly`, and
`SameSite=Lax` — `SESSION_COOKIE_SECURE` is not configurable. Browsers accept
`Secure` cookies over `http://localhost`, which is why local Docker works
without TLS; **serve the app over plain HTTP on any other host and both
cookies are dropped**, so every request mints a new session and users stop
seeing their own jobs. Deploy behind a TLS-terminating reverse proxy.

### Data Directories

`docker-compose.yml` bind-mounts `./enzyme_tk_app/app/data` read-only at `/app-data`
(`ETK_DATA_DIR`) for both `web` and `worker`. The large sets are **gitignored** — put them there
with [`scripts/db_build/`](scripts/db_build/README.md) before starting the stack. A tool whose
directory is missing still loads: its card shows a **"Missing data"** badge instead, and the app
does not crash.

Because the mount is read-only, nothing here can be regenerated by the running app —
[`scripts/db_build/`](scripts/db_build/README.md) fills it instead, writing **straight into this
directory**, so there is nothing to copy afterwards. Two scripts in one Docker image:
`download_data.py` fetches the public weights and structure databases (none of them gated — no
Hugging Face account, token or login), and `build_enzyme_db.py` turns **your own** sequence file
into a FoldSeek database plus an embeddings pickle. The **Supplied by** column says which. Comment
every unit out of `download_data.py` and its closing `report()` is an inventory on its own: one
`OK`/`MISSING` line per item below. It also leaves a hidden `.hf_cache/` here — the ESM3 snapshot
`build_enzyme_db.py` embeds with (~5.4 GB, build time only, never read by the app).

| Directory | Used by | Supplied by | Contents |
|-----------|---------|-------------|----------|
| `sequences/` | Sequence Similarity | You | Reference protein tables — CSV or TSV, plain or gzipped (`.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`), each with an `Entry`, `Sequence`, and `EC number` column, and each shown by its exact filename, extension included. Any other column is metadata: the app never enumerates it and passes it straight through to the results grid — except an optional `Cofactor` column, whose UniProt annotations are offered as a filter and shown in the grid as plain names (`Mg(2+); Mn(2+)`). A file missing a required column is **not** offered in the dropdown — the tool card names it and the columns it lacks instead |
| `reactions/`, `structures/` | the other similarity tools | You — the sample `structures/` ship in the repo | Reference CSVs and sample CIF/PDB files — every CSV becomes an option in the tool's database dropdown, shown by its exact filename, extension included |
| `foldseek_db/` | Sequence and Structure-Based Similarity | `download_data.py` for `PDB` (~6.4 GB) and `AFDB_SWISSPROT` (~3.9 GB); `build_enzyme_db.py` for one built from your own sequences | One subdirectory per FoldSeek database (`PDB`, `AFDB_SWISSPROT`, …), each shown by its folder name |
| `foldseek_models/weights/` | Sequence and Structure-Based Similarity | `download_data.py` | ProstT5 weights for sequence-to-structure prediction — `prostt5-f16.gguf` (~2 GB) |
| `sequence_embeddings/` | Func-E Activity Prediction | `build_enzyme_db.py` | Pre-encoded protein embedding tables — at least one `.pkl`, each with `Entry`, `Sequence` and `esm3_mean`. Named for the data rather than a tool: any tool needing protein embeddings reads these. Columns are **not** checked at discovery (a pickle has no header-only read) — a malformed one is skipped and named in the job's **Databases Skipped** card |
| `funce_models/` | Func-E Activity Prediction | Manual — no public source yet; `download_data.py` only checks and names the eight files it wants | The four EC-level checkpoints, `run_easy_0-50_ESRP_{1..4}_model_1_500000_{conf.pkl,checkpoint.pth}` (~1.5 GB total) |
| `unimol_weights/` | Func-E Activity Prediction | `download_data.py` | The UniMol v2 164M checkpoint at `modelzoo/164M/checkpoint.pt` (~660 MB), used to embed the query reaction's substrate and product. Named for the model, not for its reader. Func-E passes this directory to the `Funce_rxnfp_unimol` step as `unimol_weights_dir`. The exact checkpoint path is checked, not just the directory: the mount is read-only, so a wrong layout cannot heal itself with a download |

A Func-E job peaks around **2 GB RSS** in the worker process, with a transient RxnFP subprocess of
similar size earlier in the run — it loads its own torch and BERT, then exits before the worker
reaches its own peak — so budget roughly **3 GB per concurrent Func-E job**. A 10-candidate job
takes ~12 s of run time (~15 s wall clock), around 10 s of which is loading the RxnFP and UniMol
checkpoints: a fixed cost, flat regardless of database size. Jobs time out after 1800 s.

Every database-backed tool selects **multiple** databases at once (all of them by default)
and merges the selections into one search, so a directory holding a single file makes the
multi-select indistinguishable from a single-select. Keeping a couple of small slices
beside the full sets — e.g. 20-row slices of `sequences/protein.csv` and of the
`reactions/` EnzymeMap CSV — is the cheapest way to exercise multi-database behaviour
locally without loading the 100 MB+ originals. A database that cannot be read is skipped
and named in a **Databases Skipped** stat card; the job only fails if *every* selection is
unreadable.

### Refetching `enzymetk` (branch-tracked)

`requirements/prd.txt` installs `enzymetk` from a **branch** (`@funce-updates`), not a pinned
commit, until it has a release. Both pip and the Docker layer cache key on the branch *name*
rather than the commit it resolves to, so a plain `docker compose build` reuses whatever copy it
already has. To pick up new commits from the branch:

```bash
docker compose build --no-cache
docker compose up -d
```

This is the same situation — and the same answer — as the builder image in
[`scripts/db_build/`](scripts/db_build/README.md), which tracks the same branch.

### GPU (optional)

The image installs the **CPU** build of PyTorch by default (`ARG TORCH_INDEX_URL` in the
`Dockerfile`), so enabling a GPU takes **two** steps — both required, neither is enough alone:

1. Rebuild against the CUDA wheels:

   ```bash
   docker compose build --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
   ```

2. Uncomment the device reservation under the `worker` service's `deploy:` key in
   `docker-compose.yml`, on a `linux/amd64` host with the NVIDIA driver and
   `nvidia-container-toolkit` installed.

Func-E then picks the GPU up on its own — it selects its device with
`torch.cuda.is_available()`, so no code change is needed. PyPI ships no CUDA build of torch
for arm64, so both steps are no-ops on Apple Silicon (jobs run on CPU, reported in the job's
**Device** stat card).

### Shared Volume

The `web` and `worker` containers share a named Docker volume (`job-outputs`). Redis holds only lightweight job metadata (status, parameters, timestamps); the heavy payloads live on the volume. For every job the worker writes the job resuls and logs under `JOB_OUTPUTS_PATH/<job_id>/`, and Redis keeps only a pointer to the result. The web container reads both files from the same path when the user views results.

Cleanup happens on job delete/clear and, for anything left behind, via a periodic **Celery beat** sweep (`celery_beat_sweep_orphaned_outputs`) that removes output dirs whose Redis `job:<id>` key has expired — see the `beat` service in `docker-compose.yml`.

```yaml
# docker-compose.yml (excerpt)
volumes:
  job-outputs:        # named volume shared between web + worker

services:
  web:
    volumes:
      - job-outputs:/job-outputs
    environment:
      - JOB_OUTPUTS_PATH=${JOB_OUTPUTS_PATH:-/job-outputs}

  worker:
    volumes:
      - job-outputs:/job-outputs
    environment:
      - JOB_OUTPUTS_PATH=${JOB_OUTPUTS_PATH:-/job-outputs}
```

Both services **must** resolve `JOB_OUTPUTS_PATH` to the same path. Override via `.env` or the orchestrator's env config.


## Azure Deployment

Deploys web, worker, and beat as Azure Container Apps plus Azure Cache for
Redis via `make deploy-azure`. See the [Developer Guide](docs/developer-guide.md#azure-deployment)
for required tools, secrets, and steps.

The live app: **https://enzyme-tk-web.victoriouscliff-65afb037.eastus.azurecontainerapps.io**
## FAQ

### Where do the model weights and reference databases come from?

Run `download_data.py` from [`scripts/db_build/`](scripts/db_build/README.md) — one Docker image, no
Hugging Face account or token, everything written straight into `enzyme_tk_app/app/data/` so there is
nothing to copy afterwards. It fetches the FoldSeek `PDB` and `AFDB_SWISSPROT` databases, the ProstT5
and UniMol weights, and the ESM3 snapshot the builder below needs; `funce_models/` has no public source
yet, so it only names the files it is missing. Comment out the units you do not want — its closing
`report()` still prints `OK`/`MISSING` for every data item the app looks for.

### How do I build a FoldSeek database or an embeddings table from my own sequences?

Use `build_enzyme_db.py` from the same folder. It takes one CSV or TSV (plain or gzipped) with `Entry`
and `Sequence` columns and writes either or both artifacts directly where the tools read them — a
FoldSeek database in `data/foldseek_db/<name>/` and an ESM3 embeddings pickle at
`data/sequence_embeddings/<name>.pkl`. Drop your file in that folder, point `INPUT_FILE` at it, and run.
It **downloads nothing**: it needs ProstT5 for the database and ESM3 for the embeddings, and stops
telling you to run `download_data.py` if either is absent. See that folder's
[README](scripts/db_build/README.md) for the full steps, including the GPU build and the memory ceiling
on long proteins.

## Developers — Adding a New Tool

Tools live in self-contained sub-packages under `enzyme_tk_app/app/tools/`. Auto-discovery scans sub-packages at import time — **no central file to edit**. Create a new folder and the tool card appears on the home page automatically.

### File layout 101

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |
| `check_data.py` | No | `check_data() → list[str]` | Reports missing (or present-but-unusable) bundled data; a non-empty list renders a "Missing data" badge on the tool card |

### Full guide

For the complete walkthrough — conventions, modal layout patterns, results page structure, shared helpers, callbacks, and compute return-dict conventions — see the **[Developer Guide](docs/developer-guide.md)**.

# Testing

_Requires `pip install -r requirements/test.txt`._

## Using tox (recommended)

```bash
tox                     # run all environments (lint, security, test, docs, build)
tox -e test             # unit tests only
tox -e check-style      # ruff format + lint check
tox -e check-security   # bandit security scan
tox -e format           # auto-format and fix imports
tox -e build-docs       # build Sphinx documentation
tox -e build-dist       # build distribution package
```

CI runs these same tox environments. See [ci.yml](https://github.com/ssec-jhu/enzyme-tk-app/blob/main/.github/workflows/ci.yml).

On Linux, `tox -e test` installs PyTorch from the [CPU channel](https://download.pytorch.org/whl/cpu)
(`PIP_EXTRA_INDEX_URL` in `[testenv:test]`): `enzymetk` and `unimol_tools` leave `torch` unpinned, and
PyPI's linux wheel drags in ~2.8 GB of CUDA dependencies — more than a CI runner's free disk. No effect
on macOS, where PyPI's torch is already CPU-only; the image reaches the same result its own way (see
[GPU (optional)](#gpu-optional)). `tox -e test-docker-dependent` installs nothing locally — it runs
pytest inside the `worker` container and is skipped when Docker is not running.

![Example Results](enzyme_tk_app/app/assets/example.jpg)
