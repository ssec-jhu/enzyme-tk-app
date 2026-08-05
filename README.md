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
| **Sequence Similarity** | High-performance pairwise and multiple sequence alignment using Smith-Waterman and BLAST algorithms | `diamond-blastp` |
| **Sequence and Structure-Based Similarity** | FoldSeek-powered similarity search using protein sequences (ProstT5) or structures (CIF/PDB). Searches across multiple databases including PDB and AlphaFold/Swiss-Prot | `foldseek`, `prostt5` |
| **Timer Tool Template** | A demo tool for testing the job scheduling backend | — |

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
Redis, pulling the same GHCR image `ci.yml` publishes on every push to
`main`. Requires `az login` and an existing `enzyme-tk-rg` resource group.

```bash
make deploy-azure
```

This runs `az deployment group create -f main.bicep`, reading four secrets
out of `.env`:

| Variable | Purpose |
|----------|---------|
| `GH_USERNAME` | GitHub username owning the PAT below |
| `GH_PAT` | GitHub PAT used by Container Apps to pull the private `ghcr.io/ssec-jhu/enzyme-tk-app` image |
| `ETK_ADMIN_TOKEN` / `ETK_SECRET_KEY` | Same admin secrets as local dev — see [Admin Secrets](#admin-secrets-env) |

### Generating `GH_PAT`

Use a **classic** PAT, not a fine-grained one:

1. [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)**.
2. Scope: `read:packages` only.
3. If `ssec-jhu` enforces SSO, click **Configure SSO** next to the new token and authorize it for the org — otherwise GHCR will still deny pulls with it.

Fine-grained PATs don't reliably work here: even with `Packages: Read`
permission, org approval, and package-level access all granted, GHCR can
still return `denied` on pull for an org-owned container package — a known
gap in GitHub's fine-grained token support. Classic PATs with
`read:packages` are the documented, reliable path (it's what `ci.yml` itself
uses via `GITHUB_TOKEN`).

To sanity-check a token before deploying:

```bash
echo "$GH_PAT" | docker login ghcr.io -u "$GH_USERNAME" --password-stdin
docker pull ghcr.io/ssec-jhu/enzyme-tk-app:main
```

If the pull succeeds locally, `make deploy-azure` will succeed too.

### Accessing the deployed app

The live app: **https://enzyme-tk-web.victoriouscliff-65afb037.eastus.azurecontainerapps.io**

This URL is stable across redeploys — the random suffix belongs to the
Container Apps *Environment* (`enzyme-tk-env`), not the individual
deployment, and `make deploy-azure` updates that environment in place rather
than recreating it. It only changes if the environment or the
`enzyme-tk-rg` resource group is deleted and recreated. To look it up
without a redeploy:

```bash
az containerapp show -g enzyme-tk-rg -n enzyme-tk-web --query properties.configuration.ingress.fqdn -o tsv
```

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
