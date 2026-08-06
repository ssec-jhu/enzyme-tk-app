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
| **Func-E Activity Prediction** | Scores (enzyme, reaction) pairs with an ensemble of four attention models — one per EC level — and ranks a pre-encoded protein database by predicted activity | `torch` |
| **Timer Tool Template** | A demo tool for testing the job scheduling backend | — |

> **Func-E is prediction-only today.** The reaction-to-fingerprint encoder is not wired up
> yet, so only the pre-encoded **DEHP → MEHP** example reaction can be scored; any other
> reaction SMILES fails with an explanatory error. `compute._encode_reaction()` in
> `enzyme_tk_app/app/tools/funce/` is the single seam to replace when RxnFP + UniMol
> encoding lands.

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

All configuration is via environment variables, set in `docker-compose.yml` for both the `web` and `worker` services:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (broker + result backend) |
| `JOB_TTL_SECONDS` | `86400` (24 h) | How long job metadata is retained in Redis |
| `JOB_OUTPUTS_PATH` | `/job-outputs` | Directory for offloaded result + log files (shared volume between web + worker) |
| `CELERY_SWEEP_INTERVAL_SECONDS` | `86400` (24 h) | How often Celery beat sweeps orphaned output dirs (clamped to ≥ 1) |
| `ETK_DATA_DIR` | `enzyme_tk_app/app/data` (compose sets `/app-data`) | Root of the read-only tool data mount; every data directory below derives from it (`enzyme_tk_app/app/paths.py`) |

### Data Directories

`docker-compose.yml` bind-mounts `./enzyme_tk_app/app/data` read-only at `/app-data`
(`ETK_DATA_DIR`) for both `web` and `worker`. The large sets are **gitignored** — download
or generate them on the host before starting the stack. A tool whose directory is missing
still loads: its card shows a **"Missing data"** badge instead, and the app does not crash.

| Directory | Used by | Contents |
|-----------|---------|----------|
| `sequences/` | Sequence Similarity | Reference protein tables — CSV or TSV, plain or gzipped (`.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`), each with an `Entry`, `Sequence`, and `EC number` column, and each shown by its exact filename, extension included. Any other column is metadata: the app never enumerates it and passes it straight through to the results grid. A file missing a required column is **not** offered in the dropdown — the tool card names it and the columns it lacks instead |
| `reactions/`, `structures/` | the other similarity tools | Reference CSVs and sample CIF/PDB files — every CSV becomes an option in the tool's database dropdown, shown by its exact filename, extension included |
| `foldseek_db/` | Sequence and Structure-Based Similarity | One subdirectory per FoldSeek database (`PDB`, `AFDB_SWISSPROT`, …), each shown by its folder name |
| `foldseek_models/weights/` | Sequence and Structure-Based Similarity | ProstT5 weights for sequence-to-structure prediction |
| `sequence_embeddings/` | Func-E Activity Prediction | Pre-encoded protein embedding tables — at least one `.pkl`, each with `Entry`, `Sequence` and `esm3_mean`. Named for the data rather than a tool: any tool needing protein embeddings reads these. Columns are **not** checked at discovery (a pickle has no header-only read) — a malformed one is skipped and named in the job's **Databases Skipped** card |
| `funce_models/` | Func-E Activity Prediction | The four EC-level checkpoints, `run_easy_0-50_ESRP_{1..4}_model_1_500000_{conf.pkl,checkpoint.pth}` (~1.5 GB total) |

A Func-E job needs ~1.1 GB RSS in the worker; the four checkpoints load in ~0.2 s warm and the job times out after 1800 s.

Every database-backed tool selects **multiple** databases at once (all of them by default)
and merges the selections into one search, so a directory holding a single file makes the
multi-select indistinguishable from a single-select. Keeping a couple of small slices
beside the full sets — e.g. 20-row slices of `sequences/protein.csv` and of the
`reactions/` EnzymeMap CSV — is the cheapest way to exercise multi-database behaviour
locally without loading the 100 MB+ originals. A database that cannot be read is skipped
and named in a **Databases Skipped** stat card; the job only fails if *every* selection is
unreadable.

### GPU (optional)

Func-E selects its device with `torch.cuda.is_available()`, so it uses a GPU automatically
once the worker container is given one — no code or requirements change. Uncomment the
device reservation under the `worker` service's `deploy:` key in `docker-compose.yml` on a
`linux/amd64` host with the NVIDIA driver and `nvidia-container-toolkit` installed. PyPI
ships no CUDA build of torch for arm64, so this is a no-op on Apple Silicon (jobs run on
CPU, reported in the job's **Device** stat card).

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

### How do I add a new FoldSeek database from my CSV file?

Use the standalone builder in [`scripts/foldseek_db_build/`](scripts/foldseek_db_build/README.md). Your CSV needs `Entry` and `Sequence` columns; drop it in that folder, point `CSV_PATH` at it, and build — see that folder's [README](scripts/foldseek_db_build/README.md) for the full steps.

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

![Example Results](enzyme_tk_app/app/assets/example.jpg)
