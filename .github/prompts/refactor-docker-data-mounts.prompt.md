# Docker & Data-Mount Refactor — Plan

## Goal

Cleanly separate **bundled data** (small, baked into the image, never overridden)
from **external data** (large, mounted from host or cloud, fully overridable),
and split the Compose configuration into a **dev** stack that works
out-of-the-box and a **prod** stack with a single environment file driving
all production knobs.

This document is the source-of-truth plan; treat it as the prompt for the
refactor. No code changes have been made yet.

---

## 1. Problems with the current setup

1. **Two confused `data` directories:**
   - In-tree `enzyme_tk_app/app/data/` (contains `structures/*.cif`, tracked
     in git, copied into the image via `COPY . .`).
   - Repo-root `./data/` (the bind-mount source for `app-data` in
     `docker-compose.yml`, mounted to `/data` inside the container).

   `paths.py` defaults `DATA_DIR` to the in-tree dir, but inside Docker the
   environment variable `ETK_DATA_DIR=/data` redirects everything —
   including `STRUCTURES_DIR` — to the host bind-mount. So the bundled CIFs
   under `enzyme_tk_app/app/data/structures/` are unreachable inside the
   container unless the user *also* copies them into their host data dir.

2. **`STRUCTURES_DIR` is entangled with overridable paths.** A user who
   points `ETK_DATA_DIR_HOST=~/Desktop/etk-data` at a foldseek DB folder
   silently loses access to the bundled structures.

3. **No `docker-compose.prod.yml`.** The header of the current compose file
   claims it is "DEV" and references a prod overlay that does not exist.

4. **No `.env.example`** to guide newcomers; users must read the YAML
   comments to discover `ETK_DATA_DIR_HOST`.

5. **Big files (`foldseek_db/`, `foldseek_models/`) live under the in-tree
   `data/` dir.** They are gitignored and dockerignored, but the *layout*
   invites accidental baking-in if anyone moves files around.

---

## 2. Two-tier data model

| Tier | Contents | Location | Override? |
|---|---|---|---|
| **Bundled** (small, baked into image) | `structures/*.cif` | `enzyme_tk_app/app/data/structures/` (source tree, copied by `COPY . .`) | **Never** — fixed at image build time |
| **External** (large, host-mounted) | `sequences/*.csv`, `reactions/*.csv`, `foldseek_db/<db>/`, `foldseek_models/` | Defaults to `enzyme_tk_app/app/data/` (source tree) when running outside Docker; redirected to a host bind-mount at `/data` (read-only) inside Docker via `ETK_DATA_DIR=/data` | **Yes** — via `ETK_DATA_DIR_HOST` env var on host, `ETK_DATA_DIR` env var inside container |

A single root — `DATA_DIR` — governs all external-tier paths.
`STRUCTURES_DIR` is the **one exception** that is always pinned to the
in-source `structures/` folder regardless of `ETK_DATA_DIR`, because
those `.cif` files are version-locked to the code that consumes them and
are bundled inside the image.

Future cloud deployments (S3 / GCS / Azure Blob) replace the bind mount
with a CSI driver or a sidecar that syncs the bucket to `/data`; the
application code is unaffected.

### Expected layout of the external data directory

```
${ETK_DATA_DIR_HOST}/
├── sequences/
│   └── *.csv
├── reactions/
│   └── *.csv
├── foldseek_db/
│   └── <db_name>/...
└── foldseek_models/
    └── ...
```

`structures/` is **never** placed here — it lives in the image.

---

## 3. Code change: `paths.py`

Keep a **single** `DATA_DIR` (overridable) and pin `STRUCTURES_DIR` to
the in-source folder as the lone exception.

```python
# enzyme_tk_app/app/paths.py
import os
from pathlib import Path

# In-source data directory bundled with the package.  Used as the default
# for DATA_DIR and as the fixed root for STRUCTURES_DIR.
_SOURCE_DATA_DIR: Path = Path(__file__).parent / "data"

# Root data directory.  Defaults to the bundled `data/` dir so running
# outside Docker (`python -m enzyme_tk_app.app.app`) works with zero env
# vars.  Inside Docker we set ETK_DATA_DIR=/data to redirect to the host
# bind mount.
DATA_DIR: Path = Path(os.environ.get("ETK_DATA_DIR", str(_SOURCE_DATA_DIR)))

SEQUENCES_DIR:       Path = DATA_DIR / "sequences"
REACTIONS_DIR:       Path = DATA_DIR / "reactions"
FOLDSEEK_DB_DIR:     Path = DATA_DIR / "foldseek_db"
FOLDSEEK_MODELS_DIR: Path = DATA_DIR / "foldseek_models"  # new (anticipated)

# Bundled .cif files — always pinned to the source tree, never overridden
# by ETK_DATA_DIR.
STRUCTURES_DIR: Path = _SOURCE_DATA_DIR / "structures"
```

No public symbols are removed; existing callers of `DATA_DIR`,
`SEQUENCES_DIR`, `REACTIONS_DIR`, `FOLDSEEK_DB_DIR`, `STRUCTURES_DIR`
keep working unchanged. The only behavioural change is that
`STRUCTURES_DIR` no longer follows `ETK_DATA_DIR` — which is the
desired fix.

---

## 4. Compose file split

| File | Purpose | Committed? |
|---|---|---|
| `docker-compose.yml` | **Base** — common service definitions (image build, networks, internal env vars, named volumes, healthchecks). Not intended to be runnable standalone. | ✅ |
| `docker-compose.dev.yml` | **Dev overlay** — exposes ports `8050` (web) and `6380` (redis), bind-mounts the repo's `./data` directory ro to `/data`, no env file required. Zero-config: works immediately after clone. | ✅ |
| `docker-compose.prod.yml` | **Prod overlay** — restart policies, no Redis port exposure, gunicorn tuning via env, `SESSION_COOKIE_SECURE=true`, healthchecks, reads `.env.prod`. Bind-mount path is **required** (no default → fails fast if unset). | ✅ (template, no secrets) |
| `docker-compose.verify.yml` | Existing CI / smoke-test overlay (port shifts only). Unchanged. | ✅ |
| `.env.prod.example` | Template for prod with **all** knobs documented (see §6). | ✅ |
| `.env.prod` | Real prod values. Default policy: gitignored. Project may `git add -f` it later if it contains no secrets. | ❌ by default |

> **Why no `.env` for dev?** The dev overlay hard-codes `./data` as the
> bind-mount source so a fresh clone runs with **zero configuration**.
> Users who want to point dev at a data dir living elsewhere on their
> machine can still do so by editing `docker-compose.dev.yml` directly
> (one-line change) or by overlaying their own `docker-compose.local.yml`
> — but neither is required for the happy path.

### Repo-tracked `./data/` directory

The repo ships an **empty** `data/` directory at the project root,
containing only:

```
data/
├── .gitkeep
└── README.md     # tells the user to drop sequences/, reactions/,
                  # foldseek_db/, foldseek_models/ here
```

This avoids the `mkdir -p data` step entirely — the bind-mount target
always exists right after `git clone`, even if the user has no external
data yet. The directory is committed but its contents (other than
`.gitkeep` and `README.md`) are gitignored (see §5).

### Standard usage

```bash
# DEV (truly out-of-the-box)
git clone …
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# → drop your CSVs / foldseek DBs into ./data/ as needed; the container
#   sees them at /data immediately (no rebuild required, ro bind mount).

# PROD
cp .env.prod.example .env.prod
$EDITOR .env.prod             # set ETK_DATA_DIR_HOST, SECRET_KEY, …
docker compose \
  -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod \
  up -d --build

# VERIFY (existing)
docker compose -p etk-verify \
  -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.verify.yml \
  up --build -d
```

`Makefile` targets wrap each invocation:
- `make dev` → dev up (no prerequisites)
- `make dev-down` → dev down
- `make prod` → prod up (asserts `.env.prod` exists)
- `make prod-down` → prod down

---

## 5. `.dockerignore` hardening

Add explicit excludes for the external-tier subdirectories so external data
can never accidentally bake into the image, even if a developer drops files
into the in-tree `data/` folder during local work:

```
# Large external-tier data — MUST stay out of the image
enzyme_tk_app/app/data/foldseek_db/
enzyme_tk_app/app/data/foldseek_models/
enzyme_tk_app/app/data/sequences/
enzyme_tk_app/app/data/reactions/

# Repo-root host bind-mount source — never bake into the image
data/

# Env files
.env
.env.prod
.env.*.local
```

Keep `enzyme_tk_app/app/data/structures/` allowed — it's the bundled tier.

### `.gitignore` for the repo-root `data/` dir

We commit the directory itself but ignore its contents so users can drop
large files in without polluting their working tree:

```
# Repo-root host data dir — keep the folder, ignore everything inside
# except the placeholder + README.
/data/*
!/data/.gitkeep
!/data/README.md
```

---

## 6. Future-proofed prod env vars

Documented in `.env.prod.example` from day one, even when not yet wired in.
Reserving the names lets prod adopt features (cloud storage, observability,
secrets) as a config-only change rather than a Compose refactor.

```bash
# ── Application ────────────────────────────────────────────────────
SECRET_KEY=                       # Flask session signing key (REQUIRED)
SESSION_COOKIE_SECURE=true        # Force https-only cookies in prod
LOG_LEVEL=info
GUNICORN_WORKERS=4
GUNICORN_THREADS=4
WEB_REPLICAS=1
WORKER_REPLICAS=4

# ── Data ───────────────────────────────────────────────────────────
ETK_DATA_DIR_HOST=                # Host path mounted to /data (REQUIRED)
JOB_OUTPUTS_RETENTION_HOURS=24

# ── Redis ──────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=
REDIS_TLS=false

# ── Observability (reserved; no-op today) ──────────────────────────
SENTRY_DSN=
OTEL_EXPORTER_OTLP_ENDPOINT=

# ── Cloud storage (reserved; no-op today) ──────────────────────────
# Anticipates moving /data and/or /job-data to object storage.
STORAGE_BACKEND=local             # local | s3 | gcs | azure
S3_BUCKET=
S3_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
GCS_BUCKET=
GOOGLE_APPLICATION_CREDENTIALS=
AZURE_STORAGE_ACCOUNT=
AZURE_STORAGE_CONTAINER=
AZURE_STORAGE_KEY=
```

---

## 7. What stays untouched

- **Dockerfile build steps** (Diamond, FoldSeek, RDKit deps) — already
  correct and multi-arch (`linux/amd64` + `linux/arm64`). The refactor does
  not change the image contents except for the bundled-vs-external split,
  which is enforced via `.dockerignore`, not the Dockerfile.
- **`task_scheduler` / `JOB_OUTPUTS_PATH` semantics** — the `job-data`
  named volume continues to be the web↔worker shared scratch space for
  large job-result JSON files. Independent of the data-mount refactor.
- **`docker-compose.verify.yml`** — port-shift overlay still works on top
  of the new base + dev overlay.

---

## 8. Migration checklist

When implementing this plan, do the items below in order. Each step should
be a separate commit for easy review.

1. **`paths.py`** — keep a single `DATA_DIR` (overridable via
   `ETK_DATA_DIR`); pin `STRUCTURES_DIR` to the in-source folder; add
   `FOLDSEEK_MODELS_DIR`.
2. **Tests** — update / add tests covering: structures resolve from bundled
   dir even when `ETK_DATA_DIR` is set; sequences/reactions/foldseek_db
   resolve from `ETK_DATA_DIR` when set, fall back to bundled dir
   otherwise.
3. **Repo-root `data/` dir** — create `data/.gitkeep` and `data/README.md`
   (the README explains the expected sub-layout: `sequences/`, `reactions/`,
   `foldseek_db/`, `foldseek_models/`).
4. **`.gitignore`** — add the `/data/*` + `!/data/.gitkeep` +
   `!/data/README.md` block; ensure `.env`, `.env.prod`, `.env.*.local`
   are ignored.
5. **`.dockerignore`** — add the explicit external-tier excludes (incl.
   the repo-root `data/`).
6. **`docker-compose.yml`** — strip out dev-specific bits; keep only the
   base service definitions, named volumes, internal env vars.
7. **`docker-compose.dev.yml`** — new file; ports, hard-coded `./data`
   bind mount, dev-only env. No env file required.
8. **`docker-compose.prod.yml`** — new file; restart policies, healthchecks,
   prod env, no Redis port exposure, required `ETK_DATA_DIR_HOST`. Reads
   `.env.prod`.
9. **`.env.prod.example`** — full prod template with all reserved vars.
10. **`Makefile`** — `dev`, `dev-down`, `prod`, `prod-down` targets.
11. **`README.md`** — replace the existing Docker section with the
    `make dev` / `make prod` workflows.
12. **Verify Agent** — update the agent's compose invocation to use the
    new `-f docker-compose.yml -f docker-compose.dev.yml` form.
13. **Run the Verify Agent end-to-end.**

---

## 9. Key design decisions (record)

- **Bundled data is part of the image, not a volume.** Structures are
  small (KB-scale) and version-locked to the code that consumes them, so
  they belong in the image. This guarantees reproducibility and removes
  the "did the user copy the structures over?" failure mode.
- **External data is read-only inside the container** (`:ro` bind mount).
  Tools never write to `/data`. All writes go to `/job-data` (the
  `job-data` named volume). This makes it safe to point `/data` at a
  shared NFS / cloud bucket later.
- **One env file per environment, not per service.** Compose merges env
  vars from `--env-file` plus the `environment:` block. Keeping all knobs
  in one `.env.prod` (or `.env`) keeps the operator's mental model
  simple.
- **Prod compose file is committed but its env file is not** (by default).
  This lets the deployment topology evolve in version control while
  keeping secrets out of the repo. Operators with no secrets in their env
  file are free to commit it with `git add -f`.
- **Reserved env var names for cloud storage / observability** are
  documented in `.env.prod.example` from day one. Today they are no-ops;
  the day they are wired up, no Compose changes are needed.
- **Dev Compose hard-codes `./data` as the bind-mount source** (no env
  expansion, no `.env` file). The repo ships an empty `data/` directory
  (kept alive by `.gitkeep` + `README.md`) so the bind-mount target
  always exists immediately after clone — `mkdir` and `cp .env.example`
  are eliminated from the dev workflow. Users who need a different host
  path edit `docker-compose.dev.yml` directly. Prod Compose, by
  contrast, has **no default** for `ETK_DATA_DIR_HOST` — Compose will
  fail with a clear error if the env var is missing, which is the
  correct prod behaviour.
- **`structures/` stays in `enzyme_tk_app/app/data/structures/`** rather
  than moving it next to the source code (e.g. under a tool's directory).
  It is shared by multiple tools, so a single shared bundled-data dir is
  the right home — and `.dockerignore` already protects the rest of that
  dir from leaking large files into the image.
