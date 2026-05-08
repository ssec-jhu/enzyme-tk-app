# SSEC-JHU EnzymeTK Tool Suite

[![CI](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/ci.yml/badge.svg)](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/ci.yml)
[![Documentation Status](https://readthedocs.org/projects/ssec-jhu-enzyme-tk-app/badge/?version=latest)](https://ssec-jhu-enzyme-tk-app.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/ssec-jhu/enzyme-tk-app/branch/main/graph/badge.svg?token=wQvM7PcGbX)](https://codecov.io/gh/ssec-jhu/enzyme-tk-app)
[![Security](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/security.yml/badge.svg)](https://github.com/ssec-jhu/enzyme-tk-app/actions/workflows/security.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.14052740.svg)](https://doi.org/10.5281/zenodo.14052740)


![SSEC-JHU Logo](docs/_static/SSEC_logo_horiz_blue_1152x263.png)

A web application for protein engineering workflows, built with [Dash](https://dash.plotly.com/) (Plotly) and backed by [Celery](https://docs.celeryq.dev/) for asynchronous job processing. It provides a suite of bioinformatics tools that scientists can launch from the browser and monitor through a job-management dashboard.

![EnzymeTK App](enzyme_tk_app/app/assets/app.jpg)

## Available Tools

| Tool | Description | Key Libraries |
|------|-------------|---------------|
| **Reaction Similarity** | Reaction similarity search using RDKit structural reaction fingerprints | `rdkit` |
| **Substrate/Product Similarity** | Molecular similarity search using Morgan circular fingerprints with Tanimoto, Russell, and Cosine scoring | `rdkit` |
| **Sequence Similarity** | High-performance pairwise and multiple sequence alignment using Smith-Waterman and BLAST algorithms | `diamond-blastp` |
| **Sequence and Structure-Based Similarity** | FoldSeek-powered similarity search using protein sequences (ProstT5) or structures (CIF/PDB). Searches across multiple databases including PDB and AlphaFold/Swiss-Prot | `foldseek`, `prostt5` |
| **Timer Tool Template** | A demo tool for testing the job scheduling backend | — |

![Example Results](enzyme_tk_app/app/assets/example.jpg)

New tools are auto-discovered — add a sub-package under `enzyme_tk_app/app/tools/` and it appears on the home page automatically. See the [Developer Guide](docs/developer-guide.md) for the full walkthrough.

## Quickstart

```bash
git clone https://github.com/ssec-jhu/enzyme-tk-app
cd enzyme-tk-app
docker compose up --build
```

The app is available at **http://localhost:8050**. This starts the web server, Redis, and 3 Celery workers — everything needed to submit and run jobs.

```bash
docker compose up --build -d     # detached
docker compose down -v           # stop and remove volumes
```

Pull pre-built images: `docker pull ghcr.io/ssec-jhu/enzyme-tk-app:<tag>`

## Configuration

### Environment Variables

All configuration is via environment variables, set in `docker-compose.yml` for both the `web` and `worker` services:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (broker + result backend) |
| `JOB_TTL_SECONDS` | `86400` (24 h) | How long job metadata is retained in Redis |
| `JOB_OUTPUTS_PATH` | `/data/job_outputs` | Directory for large result files (> 512 KB) |
| `SHARED_VOLUME_PATH` | `/data` | Base path for the shared Docker volume |
| `MAX_RESULT_BYTES` | `524288` (512 KB) | Threshold above which results are offloaded to disk |

### Shared Volume

The `web` and `worker` containers share a named Docker volume (`data:/data`) for large result files. When a job result exceeds `MAX_RESULT_BYTES`, the worker writes the result to `JOB_OUTPUTS_PATH` on the shared volume instead of storing it inline in Redis. The web container reads from the same path when the user views results.

```yaml
# docker-compose.yml (excerpt)
volumes:
  data:            # named volume shared between web + worker

services:
  web:
    volumes:
      - data:/data
    environment:
      - SHARED_VOLUME_PATH=/data
      - JOB_OUTPUTS_PATH=/data/job_outputs

  worker:
    volumes:
      - data:/data
    environment:
      - SHARED_VOLUME_PATH=/data
      - JOB_OUTPUTS_PATH=/data/job_outputs
```

Both services **must** mount the same volume at the same path. If you change `SHARED_VOLUME_PATH`, update both services.

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
