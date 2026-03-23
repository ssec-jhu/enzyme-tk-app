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
| **Sequence and Structure-Based Similarity** | Experimental tool for sequence and structure-based similarity | `foldseek` |
| **Timer Tool Template** | A demo tool for testing the job scheduling backend | — |

New tools are auto-discovered — add a sub-package under `enzyme_tk_app/app/tools/` and it appears on the home page automatically. See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full guide.

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

##  Developers - Adding a New Tool

Tools live in self-contained sub-packages under `enzyme_tk_app/app/tools/`. Auto-discovery scans sub-packages at import time — **no central file to edit**. Create a new folder and the tool card appears on the home page automatically.

### File layout

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |

### Folder-name rule

The folder name **must** equal `slug.replace("-", "_")`. The task dispatcher converts the slug back to a folder name using this convention. If you change the slug, rename the folder to match (e.g., slug `"my-new-tool"` → folder `my_new_tool/`).

### `__init__.py` — tool definition (required)

`TOOL_DEF` is the **single source of truth** for the tool's slug, title, icon, and description. Import it everywhere — never hardcode these values.

```python
from enzyme_tk_app.app.components.icons import ICON_TOOL_TIMER
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "my-new-tool",          # URL-safe, hyphens not underscores
    "title": "My New Tool",
    "desc": "Short description of what the tool does.",
    "icon": ICON_TOOL_TIMER,        # any constant from icons.py
    "order": 10,                    # lower numbers appear first
    "libraries": ["numpy"],         # optional — shown as badges on the card
    "max_duration": 3600,           # optional — timeout in seconds (default 3600)
}
```

Icon constants are defined in `enzyme_tk_app/app/components/icons.py`. The `ToolDef` type is imported from `enzyme_tk_app.app.tools`.

### `modal.py` — input form

Returns a `dbc.Modal` with the tool's input controls. Key conventions:

- **Modal ID**: `f"id-modal-{TOOL_DEF['slug']}"`
- **All component IDs** must use f-strings from `TOOL_DEF["slug"]` — never hardcode the slug.
- **Use `TOOL_DEF["title"]`** for the modal header text.
- **Dropdowns**: always use `dcc.Dropdown` (not `dbc.Select`).
- **Form controls** (dropdowns, inputs, textareas, checkboxes, radio items): add CSS class `themed-control` for dark-mode support.

```python
import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.tools.my_new_tool import TOOL_DEF


def modal():
    return dbc.Modal(
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle(TOOL_DEF["title"])),
            dbc.ModalBody([
                dbc.Label("Duration (seconds)"),
                dbc.Input(
                    id=f"id-input-{TOOL_DEF['slug']}-duration",
                    type="number", min=1, value=5,
                    className="mb-3 themed-control",
                ),
                html.Div(id=f"id-div-{TOOL_DEF['slug']}-results"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Close", id=f"id-btn-{TOOL_DEF['slug']}-cancel",
                           color="secondary", outline=True, className="me-2"),
                dbc.Button("Submit", id=f"id-btn-{TOOL_DEF['slug']}-submit",
                           color="primary"),
            ]),
        ],
    )
```

### `callbacks.py` — Dash callbacks

Callbacks open/close the modal, sync form controls, and submit jobs. Conventions:

- Import `TOOL_DEF` from the tool's own package — use `TOOL_DEF["slug"]` in all component IDs.
- Use `TOOL_DEF["slug"]` when calling `scheduler.submit_job()`.
- The launch button ID `f"id-btn-launch-{TOOL_DEF['slug']}"` is auto-generated by `tool_cards.py`.
- Access the anonymous session via `flask.g.session_id`.

```python
from dash import Input, Output, State, callback, ctx
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.tools.my_new_tool import TOOL_DEF


@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    [Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
     Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks")],
    prevent_initial_call=True,
)
def toggle_modal(launch_clicks, cancel_clicks):
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return True
    return False


@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-duration", "value"),
    prevent_initial_call=True,
)
def submit_job(n_clicks, duration):
    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        params={"seconds": int(duration)},
        session_id=g.session_id,
    )
    return f"Job submitted — ID: {job_id}"
```

### `compute.py` — backend computation

Exports `run(params) → dict`. This function executes on the Celery worker. The `params` dict matches the form fields submitted by the callback. The returned dict must be JSON-serialisable.

```python
import time


def run(params: dict) -> dict:
    seconds = int(params["seconds"])
    time.sleep(seconds)
    return {"message": f"Completed after {seconds}s"}
```

### `results.py` — custom results page (optional)

Exports `results_layout(job) → html.Div`. If absent, the job results page shows raw JSON. The `job` argument is a `JobInfo` object whose `.result` attribute contains the dict returned by `compute.run()`.

```python
from dash import html

from enzyme_tk_app.app.backend.models import JobInfo


def results_layout(job: JobInfo) -> html.Div:
    result = job.result or {}
    return html.Div(html.P(result.get("message", "No result data.")))
```

### Component ID conventions

All Dash component IDs follow the pattern `id-<component-type>-<name>` and must be built from `TOOL_DEF["slug"]`:

| Component | ID pattern |
|-----------|------------|
| Modal | `f"id-modal-{TOOL_DEF['slug']}"` |
| Launch button (auto-generated) | `f"id-btn-launch-{TOOL_DEF['slug']}"` |
| Submit button | `f"id-btn-{TOOL_DEF['slug']}-submit"` |
| Close button | `f"id-btn-{TOOL_DEF['slug']}-cancel"` |
| Inputs | `f"id-input-{TOOL_DEF['slug']}-<name>"` |
| Dropdowns | `f"id-dropdown-{TOOL_DEF['slug']}-<name>"` |
| Results div | `f"id-div-{TOOL_DEF['slug']}-results"` |

Only assign an `id` to a component if it is used in a callback (`Input`, `Output`, or `State`).

See `enzyme_tk_app/app/tools/timer_tool_template/` for a complete working reference implementation.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (broker + result backend) |
| `JOB_TTL_SECONDS` | `86400` (24 h) | How long job metadata is retained in Redis |
| `JOB_OUTPUTS_PATH` | `/data/job_outputs` | Directory for large result files |
| `SHARED_VOLUME_PATH` | `/data` | Base path for the shared Docker volume |
| `MAX_RESULT_BYTES` | `524288` (512 KB) | Threshold above which results are offloaded to disk |

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
