# Deployment Guide — Running EnzymeTK for Other People

Everything an operator needs: services, secrets, environment variables, TLS, volumes,
capacity, image builds, and Azure. For running the app on your own machine see the
[README](../README.md); for changing the code see the [Developer Guide](developer-guide.md).

## Architecture

`docker-compose.yml` orchestrates four services — `web`, `worker`, and `beat` all run the
same image built from the project `Dockerfile`; `redis` pulls stock `redis:7-alpine`:

| Service | Replicas | Ports | Role |
|---------|----------|-------|------|
| `web` | 1 | `8050:8050` | Dash UI + job submission. `gunicorn ... --workers 2 --threads 4` (`Dockerfile` `CMD`, `EXPOSE 8050`) |
| `redis` | 1 | `6380:6379` | Celery broker + result backend, and the job-metadata store. Mapped off 6379 so it cannot clash with a local Redis |
| `worker` | 3 | — | Celery workers that run the tools. The only service that needs a GPU |
| `beat` | 1 | — | Celery scheduler. Fires the periodic orphan-output sweep and nothing else, so it needs no volume |

```
                    ┌──────────────┐
    browser ──────► │  web :8050   │ ◄── admin + production env vars
                    └──┬────────┬──┘
                       │        │
              job:<id> │        │ /job-outputs  ┌─────────────────┐
                       ▼        └──────────────►│  job-outputs    │
                  ┌─────────┐                   │ (named volume)  │
                  │  redis  │                   └─────────────────┘
                  │  :6380  │                            ▲
                  └────┬────┘                            │
                       │  broker                         │ writes results + logs
          ┌────────────┴────────────┐                    │
          ▼                         ▼                    │
    ┌──────────┐              ┌──────────┐               │
    │  beat    │              │ worker×3 │───────────────┘
    │ (sweep)  │              └────┬─────┘
    └──────────┘                   │ read-only
                                   ▼
                          /app-data (ETK_DATA_DIR)
```

`web` mounts the same read-only `/app-data` as `worker` — it builds the tool cards and the
database dropdowns from it, so a `web` without the mount shows every tool as "Missing data".
Only `worker` is drawn above, to keep the diagram legible.

`beat` must stay at a **single replica** — two schedulers means the sweep fires twice.

## Admin Secrets (`.env`)

The hidden `/admin` dashboard is gated by two secrets that live in a gitignored
`.env` file at the repository root. Generate it with fresh random values:

```bash
./scripts/generate-env.sh
```

This writes `.env` from [`scripts/template.env`](../scripts/template.env) with a random
`ETK_ADMIN_TOKEN` (the login token) and `ETK_SECRET_KEY` (used to sign the admin session
cookie). Re-run the script to rotate the secrets — it prompts before overwriting an existing
`.env`. **Never commit `.env`.** If the secrets are left unset, the admin login fails closed
and the dashboard is unreachable.

The same script sets the production switch, so a deployment is one command:

```bash
./scripts/generate-env.sh --production
```

That uncomments `APP_IN_PRODUCTION_MODE=true`; `--local` turns it back off. A **plain rerun
preserves whatever the existing `.env` had**, so rotating secrets on a live deployment cannot
silently drop it back to local defaults — and the script prints the resulting mode either way.
This only affects Docker Compose: `main.bicep` hardcodes the switch on for Azure.

The security model behind these two secrets — cookie flags, the sliding idle timeout, the auth
flow — is documented in [Admin Login](admin-login.md).

## Environment Variables

`docker-compose.yml` sets them **per service**, not globally: `web` and `worker` share the
runtime variables, `beat` takes only the broker URL and the sweep interval, and the three admin
variables plus the production variable go to **`web` alone** — nothing the worker runs serves
HTTP. Anything compose leaves unset falls back to the default below.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (broker + result backend) |
| `JOB_TTL_SECONDS` | `86400` (24 h) | How long job metadata is retained in Redis |
| `JOB_OUTPUTS_PATH` | `/job-outputs` | Directory for offloaded result + log files (shared volume between web + worker) |
| `CELERY_SWEEP_INTERVAL_SECONDS` | `86400` (24 h) | How often Celery beat sweeps orphaned output dirs (clamped to ≥ 1) |
| `DEFAULT_MAX_DURATION` | `3600` (1 h) | Fallback job timeout for a tool whose `ToolDef` declares no `max_duration`. At the limit the worker raises `SoftTimeLimitExceeded` and the job is recorded `TIMEOUT` |
| `HARD_TIMEOUT_GRACE_SECONDS` | `60` | Extra seconds past a job's timeout before the hard kill, so that handler can write `TIMEOUT` to Redis first. Also part of each job's Redis TTL (`max_duration + grace + JOB_TTL_SECONDS`) |
| `ETK_DATA_DIR` | `enzyme_tk_app/app/data` (compose sets `/app-data`) | Root of the read-only tool data mount; every data directory derives from it (`enzyme_tk_app/app/paths.py`) |
| `ETK_ADMIN_TOKEN` | *(empty)* | Login token for `/admin`. Empty means the login **fails closed** and the dashboard is unreachable. `web` only |
| `ETK_SECRET_KEY` | *(empty)* | Signs the admin session cookie. Required whenever `ETK_ADMIN_TOKEN` is set — the app refuses to start otherwise. Unset with no token: a random per-process key, so admins are logged out on restart. `web` only |
| `ETK_ADMIN_SESSION_TTL_SECONDS` | `300` (5 min) | Sliding idle window for an unlocked admin session. Every authenticated check slides it forward, including the dashboard's 10 s poll, so an open tab never expires. `web` only |
| `APP_IN_PRODUCTION_MODE` | `false` | **The production switch, and the only one.** See [Production Mode](#production-mode). `web` only |

### Source files

A new variable is not necessarily a `backend/config.py` edit — they are read in four places:

| File | Reads | Reaches |
|------|-------|---------|
| `enzyme_tk_app/app/backend/config.py` | `REDIS_URL`, `JOB_TTL_SECONDS`, `JOB_OUTPUTS_PATH`, `CELERY_SWEEP_INTERVAL_SECONDS`, `ETK_ADMIN_TOKEN`, `ETK_SECRET_KEY`, `ETK_ADMIN_SESSION_TTL_SECONDS` | `web` + `worker` (+ `beat` for the broker and sweep interval). The three `ETK_ADMIN_*` values matter on `web` alone — `app.py` and `pages/admin.py` read them off `config`, not out of the environment |
| `enzyme_tk_app/app/backend/celery_app.py` | `DEFAULT_MAX_DURATION`, `HARD_TIMEOUT_GRACE_SECONDS` | `worker` (the soft/hard task limits) + `web` (`effective_ttl()` at submit time) |
| `enzyme_tk_app/app/paths.py` | `ETK_DATA_DIR` | `web` + `worker` |
| `enzyme_tk_app/app/utils/submission_limits.py` | `APP_IN_PRODUCTION_MODE` | `web` only |

A variable must stay in step across **four** places: the table above,
[`scripts/template.env`](../scripts/template.env) (what an operator actually copies),
`docker-compose.yml`, and `main.bicep`. A flag live in one deployment and missing from the
other is the failure mode this list exists to prevent.

### Production checklist

Before exposing the app to anyone but yourself:

- [ ] `./scripts/generate-env.sh --production` — sets `APP_IN_PRODUCTION_MODE=true` and fresh secrets.
- [ ] `ETK_ADMIN_TOKEN` and `ETK_SECRET_KEY` both set, both random, neither committed.
- [ ] The app is behind a **TLS-terminating reverse proxy** — see [TLS](#tls-and-reverse-proxies). Non-negotiable; plain HTTP breaks sessions outright.
- [ ] `JOB_TTL_SECONDS` and `CELERY_SWEEP_INTERVAL_SECONDS` sized for your retention policy.
- [ ] `ETK_DATA_DIR` points at a populated, read-only reference-data mount.
- [ ] Worker replica count matches available RAM — see [Capacity Planning](#capacity-planning).

## Production Mode

`APP_IN_PRODUCTION_MODE` defaults to **off**, so a downloaded checkout runs locally with no
submission limits and no code edits. Set it to `true` and one browser session may hold at most
`MAX_ACTIVE_JOBS_PER_SESSION` (3) concurrent jobs, so a bot or a runaway script cannot starve
the Celery workers.

That cap is a **constant** in `enzyme_tk_app/app/utils/submission_limits.py`, deliberately not
an environment variable — it is policy the app owns, not deployment config. Raising it is a
code edit and a review.

The cap is keyed on the anonymous session cookie, which a client can discard to mint a new
one — it stops an impatient user, a runaway script, and a naive bot, not a determined
attacker. A CAPTCHA is the intended answer for that and is not implemented yet.

`main.bicep` hardcodes the switch **on** for Azure, because nothing from `.env` reaches it —
so this variable only affects Docker Compose deployments.

## TLS and Reverse Proxies

Both session cookies are always sent with `Secure`, `HttpOnly`, and `SameSite=Lax` —
`SESSION_COOKIE_SECURE` is not configurable. Browsers accept `Secure` cookies over
`http://localhost`, which is why local Docker works without TLS; **serve the app over plain
HTTP on any other host and both cookies are dropped**, so every request mints a new session
and users stop seeing their own jobs. Deploy behind a TLS-terminating reverse proxy.

## Shared Volume

The `web` and `worker` containers share a named Docker volume (`job-outputs`). Redis holds
only lightweight job metadata (status, parameters, timestamps); the heavy payloads live on the
volume. For every job the worker writes the job results and logs under
`JOB_OUTPUTS_PATH/<job_id>/`, and Redis keeps only a pointer to the result. The web container
reads both files from the same path when the user views results.

Cleanup happens on job delete/clear and, for anything left behind, via a periodic **Celery
beat** sweep (`celery_beat_sweep_orphaned_outputs`) that removes output dirs whose Redis
`job:<id>` key has expired — see the `beat` service in `docker-compose.yml`.

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

Both services **must** resolve `JOB_OUTPUTS_PATH` to the same path. Override via `.env` or the
orchestrator's env config.

## Capacity Planning

A Func-E job peaks around **2 GB RSS** in the worker process, with a transient RxnFP
subprocess of similar size earlier in the run — it loads its own torch and BERT, then exits
before the worker reaches its own peak — so budget roughly **3 GB per concurrent Func-E job**.
With the default 3 worker replicas that is ~9 GB if all three run Func-E at once.

A 10-candidate job takes ~12 s of run time (~15 s wall clock), around 10 s of which is loading
the model checkpoints: a fixed cost, flat regardless of database size.

Timeouts are **per tool**, set as `max_duration` in each `ToolDef` — Func-E 1800 s, Sequence
and Structure-Based Similarity 3600 s, the Timer template 600 s, the two similarity tools
180 s. A tool that declares none falls back to `DEFAULT_MAX_DURATION` (3600 s).

## Building the Image

### Refetching `enzymetk` (branch-tracked)

`requirements/prd.txt` installs `enzymetk` from a **branch** (`@funce-updates`), not a pinned
commit, until it has a release. Both pip and the Docker layer cache key on the branch *name*
rather than the commit it resolves to, so a plain `docker compose build` reuses whatever copy
it already has. To pick up new commits from the branch:

```bash
docker compose build --no-cache
docker compose up -d
```

This is the same situation — and the same answer — as the builder image in
[`scripts/db_build/`](../scripts/db_build/README.md), which tracks the same branch.

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

### Pre-built images

`ci.yml` publishes an image on every push to `main`:

```bash
docker pull ghcr.io/ssec-jhu/enzyme-tk-app:<tag>
```

## Azure Deployment

`make deploy-azure` deploys web, worker, and beat as Azure Container Apps plus Azure Cache for
Redis, pulling the same GHCR image `ci.yml` publishes on every push to `main`.

### Required tools

- **Azure CLI** — `az login` before deploying.
- An existing **`enzyme-tk-rg`** resource group.
- **Docker** — only needed to sanity-check the GHCR pull below.

### Required secrets (`.env` at repo root)

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

### Deploying

```bash
make deploy-azure
```

This runs `az deployment group create -f main.bicep`, reading the four secrets above out of `.env`.

Nothing else from `.env` reaches Azure, so `main.bicep` hardcodes `APP_IN_PRODUCTION_MODE=true`
on the web container: **the deployed app always runs with the per-session job cap on**
(`MAX_ACTIVE_JOBS_PER_SESSION`, 3). Change whether it is on in `main.bicep`, not in `.env` —
and keep the flag in step with `docker-compose.yml` so a setting is not live in one deployment
and missing from the other. Changing the cap *value* is a code edit in
`utils/submission_limits.py`; CI rebuilds the image on every push to `main`, so it ships on the
next deploy without a manual build.

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

### Updating reference data files

Bundled reference data (`data/sequences/`, `data/reactions/`, etc. — see
[`paths.py`](../enzyme_tk_app/app/paths.py)) is served from the **`app-data`**
Azure Files share, mounted at `/app-data` on web and worker. Files
must be uploaded directly to the share; they are not part of the container
image.

> **Unlike Compose, the Azure mount is not read-only.** `docker-compose.yml`
> pins `:ro`; `main.bicep`'s `sharedVolumeMounts` sets no `readOnly`, so on
> Azure the share is writable by both containers. Nothing in the app writes
> there — the code treats `ETK_DATA_DIR` as read-only throughout — so this is
> a missing guardrail rather than a live bug. Add `readOnly: true` to both
> mounts to close it. The local `data/<subdir>/` path maps to the same `<subdir>/` path on
the share (e.g. `data/sequences/protein.csv` → `sequences/protein.csv`).

To add or update a file via the Azure Portal:

1. Go to the **`enzyme-tk-rg`** resource group → the storage account (kind
   `FileStorage`, name like `st<random>`).
2. **Data storage → File shares** → open **`app-data`**.
3. If the target subdirectory (`sequences`, `reactions`, ...) doesn't exist
   yet, click **+ Add directory** to create it.
4. Open that directory → **Upload** → select the local file. Uploading a
   file with the same name overwrites the existing one.

No redeploy is needed — web and worker read the share live on each request.
