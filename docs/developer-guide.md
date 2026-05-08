# Developer Guide — Adding a New Tool

This guide walks through how to add a new tool to the EnzymeTK Tool Suite, from folder creation to results rendering. It covers the conventions you must follow, which shared components to reuse, and what custom code you write. The [Reaction Similarity](../enzyme_tk_app/app/tools/reaction_similarity/) tool is used as the running example throughout.

> **Minimal skeleton:** For the simplest possible tool with no custom UI, see [`timer_tool_template/`](../enzyme_tk_app/app/tools/timer_tool_template/).

---

## How Do I Add a New Tool?

1. **Create a folder** under `enzyme_tk_app/app/tools/` named after your slug with underscores (e.g., `reaction_similarity/` for slug `"reaction-similarity"`).
2. **Add `__init__.py`** exporting `TOOL_DEF: ToolDef` — the single source of truth for slug, title, description, icon, and display order.
3. **Add an icon constant** to `enzyme_tk_app/app/components/icons.py` (free FontAwesome only) and import it in your `TOOL_DEF`.
4. **Create `modal.py`** — build the input form using the shared modal helpers for header, section dividers, footer, and submission placeholder.
5. **Create `callbacks.py`** — wire the modal open/close, form validation, and job submission.
6. **Create `compute.py`** — implement `run(params) → dict` with your algorithm. This runs on the Celery worker.
7. **Create `results.py`** (optional) — build a custom results layout. If absent, the framework shows raw JSON.
8. **Run `tox run -e format && tox`** to format and validate.
9. **Done.** The tool auto-appears on the home page — no central file to edit.

---

## Conventions

### Folder-name rule

The folder name **must** equal `slug.replace("-", "_")`. The task dispatcher converts the slug back to a folder name using this convention.

| Slug | Folder name |
|------|-------------|
| `"reaction-similarity"` | `reaction_similarity/` |
| `"my-new-tool"` | `my_new_tool/` |

### Component ID pattern

All Dash component IDs follow the pattern `id-<component-type>-<slug>-<name>` and **must** be built from `TOOL_DEF["slug"]` — never hardcode the slug string.

| Component | ID pattern |
|-----------|------------|
| Modal | `f"id-modal-{TOOL_DEF['slug']}"` |
| Launch button (auto-generated) | `f"id-btn-launch-{TOOL_DEF['slug']}"` |
| Submit button | `f"id-btn-{TOOL_DEF['slug']}-submit"` |
| Cancel button | `f"id-btn-{TOOL_DEF['slug']}-cancel"` |
| Text inputs | `f"id-input-{TOOL_DEF['slug']}-<name>"` |
| Textareas | `f"id-textarea-{TOOL_DEF['slug']}-<name>"` |
| Dropdowns | `f"id-dropdown-{TOOL_DEF['slug']}-<name>"` |
| Results div | `f"id-div-{TOOL_DEF['slug']}-results"` |

Only assign an `id` if the component is used in a callback (`Input`, `Output`, or `State`).

### Callback naming

Callback function names start with a verb describing the action:

| Verb | Usage |
|------|-------|
| `toggle_` | Open/close a modal or panel |
| `validate_` | Enable/disable submit button based on form state |
| `populate_` | Fill a field from a selection (e.g., example data) |
| `submit_` | Submit a job to the backend scheduler |

### Code style

- **PEP 8** naming: `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for constants, `PascalCase` for classes/TypedDicts.
- **Double quotes** for all strings.
- **120 character** line length limit.
- **Ruff** for formatting and linting — run `tox run -e format` to auto-format.

---

## File Layout

Each tool is a sub-package with up to five files:

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |

---

## Tool Definition — `__init__.py`

`TOOL_DEF` is the single source of truth for your tool's identity. Import it in every other file in your tool package — never hardcode the slug, title, or icon.

### `ToolDef` fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | `str` | Yes | URL-safe identifier, hyphens not underscores (e.g., `"reaction-similarity"`) |
| `title` | `str` | Yes | Human-readable name (e.g., `"Reaction Similarity"`) |
| `desc` | `str` | Yes | 1–2 sentence description for the tool card |
| `icon` | `str` | Yes | FontAwesome class string from `icons.py` |
| `order` | `int` | Yes | Display position — lower numbers appear first |
| `libraries` | `list[str]` | No | Package names shown as badges (e.g., `["rdkit"]`) |
| `max_duration` | `int` | No | Timeout in seconds (default: 3600) |

### Example — Reaction Similarity

```python
from enzyme_tk_app.app.components.icons import ICON_TOOL_REACTION
from enzyme_tk_app.app.tools import ToolDef

TOOL_DEF: ToolDef = {
    "slug": "reaction-similarity",
    "title": "Reaction Similarity",
    "desc": (
        "Reaction similarity search using RDKit structural reaction fingerprints "
        "with Tanimoto, Russell, and Cosine scoring."
    ),
    "icon": ICON_TOOL_REACTION,
    "order": 1,
    "libraries": ["rdkit"],
    "max_duration": 180,
}
```

### Auto-discovery

The module `enzyme_tk_app/app/tools/__init__.py` uses `pkgutil.iter_modules()` to scan sub-packages at import time. For each sub-package it:

1. Imports `__init__.py` and reads `TOOL_DEF` (validates required keys).
2. Imports `callbacks.py` (side-effect: registers `@callback` decorators).
3. Imports `modal.py` and collects the `modal()` factory.
4. Imports `results.py` and collects `results_layout()` into `RESULTS_LAYOUTS`.

No central registry file to edit — just create your folder and the tool appears.

---

## Modal Layout — `modal.py`

The modal is the input form shown when a user clicks "Launch →" on the tool card. Every modal follows the same structural pattern using shared helpers from `enzyme_tk_app.app.components.modal_helpers`.

### What you reuse

Five shared helper functions provide the standard modal chrome:

| Helper | What it creates |
|--------|----------------|
| `create_modal_header(icon, title)` | Header bar with tool icon, title, and close button |
| `create_modal_input_section_header()` | "Input Data" section divider with flask icon |
| `create_modal_config_section_header()` | "Tool Configurations" section divider with gear icon |
| `create_modal_footer(slug)` | Cancel (outline) + Run (primary) buttons with correct IDs |
| `create_modal_submission_results(slug)` | Placeholder div for job-ID confirmation or validation errors |

### What you add

Your custom code goes inside two `html.Div(className="bg-light p-3 rounded mb-3")` sections:

**Section 1 — Input Data:** The primary inputs for your tool (task name, SMILES input, file upload, sequence textarea, etc.). Use `dbc.Row`/`dbc.Col` for label ↔ control alignment.

**Section 2 — Tool Configurations:** Optional tuning parameters (algorithm selectors, database pickers, result limits, etc.).

### Structural rules

1. Top-level: `dbc.Modal(size="lg", centered=True)`
2. `dbc.ModalBody` gets `className="p-4"`
3. Each logical section: `html.Div(className="bg-light p-3 rounded mb-3")`
4. All form controls get `className="... themed-control"` for dark-mode styling
5. Dropdowns: always `dcc.Dropdown` (not `dbc.Select`)
6. Inputs use `dbc.Row`/`dbc.Col` for label ↔ control alignment

### Example — Reaction Similarity modal structure

The annotated structure below shows which parts are **reused helpers** (marked ✦) and which are **custom** to this tool:

```python
dbc.Modal(
    id=f"id-modal-{TOOL_DEF['slug']}",
    is_open=False,
    size="lg",
    centered=True,
    children=[
        # ✦ REUSED — shared header helper
        create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),

        dbc.ModalBody(
            className="p-4",
            children=[
                # --- Section 1: Input Data ---
                html.Div(
                    className="bg-light p-3 rounded mb-3",
                    children=[
                        # ✦ REUSED — shared section header
                        create_modal_input_section_header(),

                        # CUSTOM — Task Name input
                        dbc.Row([
                            dbc.Col(dbc.Label("Task Name", className="col-form-label fw-bold"), width=3),
                            dbc.Col(dbc.Input(
                                id=f"id-input-{TOOL_DEF['slug']}-task-name",
                                type="text",
                                className="themed-control",
                            ), width=9),
                        ], className="mb-2", align="center"),

                        # CUSTOM — Reaction SMILES textarea + example picker
                        dbc.Row([
                            dbc.Col(dbc.Label("Reaction SMILES", ...), width=3),
                            dbc.Col([
                                dbc.Textarea(id=f"id-textarea-{TOOL_DEF['slug']}-smiles", ...),
                                dcc.Dropdown(id=f"id-dropdown-{TOOL_DEF['slug']}-example", ...),
                            ], width=9),
                        ], className="mb-2"),
                    ],
                ),

                # --- Section 2: Tool Configurations ---
                html.Div(
                    className="bg-light p-3 rounded mb-2",
                    children=[
                        # ✦ REUSED — shared section header
                        create_modal_config_section_header(),

                        # CUSTOM — Database multi-select dropdown
                        dbc.Row([...], className="mb-2", align="center"),

                        # CUSTOM — Algorithm multi-select dropdown
                        dbc.Row([...], className="mb-2", align="center"),

                        # CUSTOM — Top N Results number input
                        dbc.Row([...], className="mb-2", align="center"),
                    ],
                ),

                # ✦ REUSED — submission results placeholder
                create_modal_submission_results(TOOL_DEF["slug"]),
            ],
        ),

        # ✦ REUSED — shared footer (Cancel + Run buttons)
        create_modal_footer(TOOL_DEF["slug"]),
    ],
)
```

See [reaction_similarity/modal.py](../enzyme_tk_app/app/tools/reaction_similarity/modal.py) for the full implementation.

---

## Callbacks — `callbacks.py`

Callbacks wire the modal to the backend. Most tools need four callbacks:

| Callback | Trigger | What it does |
|----------|---------|-------------|
| `toggle_<slug>_modal` | Launch button / Cancel button | Opens or closes the modal |
| `validate_<slug>_form` | Any form field change | Enables/disables submit based on validation |
| `populate_example_<type>` | Example dropdown selection | Fills the input field with demo data |
| `submit_<slug>_job` | Submit button / Launch button | Submits job to scheduler; clears stale results on reopen |

### What you reuse

- **`get_task_scheduler()`** from `enzyme_tk_app.app.backend` — the singleton scheduler.
- **Launch button ID** auto-generated by `tool_cards.py`: `f"id-btn-launch-{TOOL_DEF['slug']}"` — you never create this button, you just reference its ID.
- **Session ID** via `flask.g.session_id` — anonymous UUID cookie.
- **`raise PreventUpdate`** from `dash.exceptions` — for guard clauses instead of returning empty values.

### What you add

- **Validation logic** specific to your form fields.
- **Job parameter assembly** — build the `params` dict from form `State` values.
- **Example data population** — if your tool has demo examples.

### Example — Reaction Similarity callbacks

```python
from dash import Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
from flask import g

from enzyme_tk_app.app.backend import get_task_scheduler
from enzyme_tk_app.app.tools.reaction_similarity import TOOL_DEF


# 1. Toggle modal open/close
@callback(
    Output(f"id-modal-{TOOL_DEF['slug']}", "is_open"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    Input(f"id-btn-{TOOL_DEF['slug']}-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_reaction_similarity_modal(launch_clicks, cancel_clicks):
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return True
    return False


# 2. Populate SMILES textarea from example dropdown
@callback(
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-example", "value"),
    prevent_initial_call=True,
)
def populate_example_reaction(example_value):
    if example_value:
        return example_value
    raise PreventUpdate


# 3. Enable/disable submit button
@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Input(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    Input(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    Input(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
)
def validate_reaction_form(task_name, smiles, selected_databases, selected_algorithms):
    has_name = task_name and task_name.strip()
    has_smiles = smiles and smiles.strip()
    has_databases = selected_databases and len(selected_databases) > 0
    has_algorithms = selected_algorithms and len(selected_algorithms) > 0
    return not (has_name and has_smiles and has_databases and has_algorithms)


# 4. Submit job (or clear stale results on reopen)
@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    State(f"id-textarea-{TOOL_DEF['slug']}-smiles", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-algorithms", "value"),
    State(f"id-input-{TOOL_DEF['slug']}-top-n", "value"),
    prevent_initial_call=True,
)
def submit_reaction_similarity_job(submit_clicks, launch_clicks, task_name, databases, smiles, algorithms, top_n):
    # Clear stale results when the modal is freshly opened
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        params={
            "task_name": task_name.strip(),
            "databases": databases,
            "smiles": smiles.strip(),
            "algorithms": algorithms,
            "top_n": int(top_n),
        },
        session_id=g.session_id,
    )
    return f"Job submitted — ID: {job_id}"
```

See [reaction_similarity/callbacks.py](../enzyme_tk_app/app/tools/reaction_similarity/callbacks.py) for the full implementation.

---

## Compute — `compute.py`

This module exports `run(params: dict) -> dict`. It runs on the Celery worker — not in the web process. The `params` dict contains the form fields submitted by the callback.

### Return dict conventions

Your `run()` function returns a plain dict. The framework recognises several special keys:

| Key | Type | Purpose |
|-----|------|---------|
| `_stat_cards` | `list[dict]` | Summary cards rendered in the results header. Each item: `{"label": "...", "value": "..."}` |
| `_params_exclude` | `list[str]` | Parameter keys to hide from the auto-rendered input table |
| `dataframe` | `dict` | Tabular results: `{"columns": [...], "data": [{...}, ...]}` for AG Grid display |

**Do NOT echo input parameters** in the return dict. The framework stores `params` separately and auto-renders them via `build_result_input_params()`.

Large results (> 512 KB) are automatically offloaded to `JOB_OUTPUTS_PATH` — just return a plain dict.

### Example — Reaction Similarity compute (simplified)

```python
import time
import pandas as pd

from enzyme_tk_app.app.paths import REACTIONS_DIR
from enzyme_tk_app.app.utils.data_loading import load_and_clean_data, get_top_n_sorted_results


def run(params: dict) -> dict:
    databases = params["databases"]
    query_smiles = params["smiles"]
    top_n = int(params["top_n"])

    run_time_start = time.monotonic()

    # Load databases and run similarity search
    all_results = []
    total_scanned = 0
    for db_filename in databases:
        db_df = load_and_clean_data(REACTIONS_DIR / db_filename)
        total_scanned += len(db_df)
        result_df = run_similarity(db_df, query_smiles)  # your algorithm
        all_results.append(result_df)

    combined = pd.concat(all_results, ignore_index=True)
    top_results = get_top_n_sorted_results(combined, sort_col, top_n)

    run_time = round(time.monotonic() - run_time_start, 3)

    return {
        # Stat cards — rendered automatically in the results header
        "_stat_cards": [
            {"label": "Databases Searched", "value": str(len(databases))},
            {"label": "Reactions Scanned", "value": f"{total_scanned:,}"},
            {"label": "Results Returned", "value": str(len(top_results))},
            {"label": "Run Time", "value": f"{run_time}s"},
        ],
        # Tabular results — displayed in the AG Grid
        "dataframe": {
            "columns": top_results.columns.tolist(),
            "data": top_results.to_dict(orient="records"),
        },
    }
```

See [reaction_similarity/compute.py](../enzyme_tk_app/app/tools/reaction_similarity/compute.py) for the full implementation.

---

## Results Page — `results.py`

The results page is what users see when they click "View Results" on a completed job. The framework provides a lot of UI for free — your `results_layout()` function only handles the tool-specific visualisation.

### What the framework gives you for free

These are rendered automatically by `my_tasks_view_results.py` — you do NOT build these in your `results.py`:

| Component | Source | What it shows |
|-----------|--------|---------------|
| **Job info header** | `_build_job_info_header()` | Tool name, status badge, submitted/completed timestamps, duration, expiry |
| **Stat cards** | `build_result_stat_cards()` | Reads `_stat_cards` from your compute return dict — databases searched, run time, etc. |
| **Input parameters table** | `build_result_input_params()` | Auto-rendered from `job.params`. SMILES values get inline structure previews. Use `_params_exclude` to hide internal keys. |
| **Status-dependent rendering** | Framework | PENDING/STARTED: progress banner with auto-refresh. FAILURE/REVOKED/TIMEOUT: error details. SUCCESS: your `results_layout()` is called. |

### What you add

Your `results_layout(job: JobInfo) -> html.Div` function receives the completed job and renders the tool-specific content — typically an AG Grid table:

1. **Define columns** — prepend tool-specific columns (e.g., SVG images), then append shared columns via `shared_col_defs()`.
2. **Build the grid** — call `build_ag_grid(column_defs, df_payload)`.
3. **Handle empty results** — return a message if no data.

### Shared helpers from `results_helpers.py`

| Helper | What it provides |
|--------|-----------------|
| `shared_col_defs()` | 25+ pre-defined column definitions for similarity scores, database metadata, and molecular descriptors. Only columns present in your data are displayed. |
| `build_ag_grid(column_defs, df_payload)` | Standardized AG Grid with pagination (20 rows/page), Balham theme, tooltips, copy/paste, and column filtering. |
| `build_result_stat_cards(job)` | Renders stat cards from `_stat_cards` in your compute result. Called by the framework, not by your code. |
| `build_result_input_params(job)` | Auto-renders submitted parameters. Called by the framework, not by your code. |

### AG Grid column rules

| Column type | `autoHeight` | `filter` | `sortable` | Notes |
|-------------|-------------|----------|------------|-------|
| Short text / number | — | `True` or `agNumberColumnFilter` | `True` | Default — fastest rendering |
| SVG / image | `True` | `False` | `False` | Row expands to fit image |
| Long text (wrap) | `True` | `True` | `True` | Add `cellClass: "cell-wrap-dash-ag-grid"` |

**Performance note:** Only enable `autoHeight` on columns that truly need it. Fixed-height rows render significantly faster.

### Example — Reaction Similarity results

```python
from dash import html

from enzyme_tk_app.app.backend.models import JobInfo
from enzyme_tk_app.app.components.results_helpers import build_ag_grid, shared_col_defs
from enzyme_tk_app.app.utils.columns import COL_RXN_SVG


def _get_column_defs():
    """Prepend the reaction SVG column, then append all shared columns."""
    return [
        {
            "field": COL_RXN_SVG,
            "cellRenderer": "SvgRenderer",
            "width": 450,
            "autoHeight": True,      # row expands to fit the SVG
            "filter": False,
            "sortable": False,
        },
    ] + shared_col_defs()


def results_layout(job: JobInfo) -> html.Div:
    result = job.result or {}
    df_payload = result.get("dataframe")

    if not df_payload or not df_payload.get("data"):
        return html.Div(
            html.P("No similar reactions found.", style={"color": "var(--text-secondary)"}),
        )

    grid = build_ag_grid(_get_column_defs(), df_payload)
    return html.Div(children=[grid])
```

Note how minimal this file is — the framework handles stat cards, input parameters, and job metadata. Your code only defines the tool-specific columns and builds the grid.

See [reaction_similarity/results.py](../enzyme_tk_app/app/tools/reaction_similarity/results.py) for the full implementation.

---

## Request Flow

```
Home Page
  ├─ tool_grid()                     ← renders tool cards from TOOLS registry
  │   └─ "Launch →" button             id="id-btn-launch-{slug}" (auto-generated)
  └─ tool_modals()                   ← renders all tool modals

User clicks "Launch →"
  └─ toggle callback opens modal     ← your callbacks.py
  └─ User fills form and clicks Run
  └─ submit callback sends job       ← scheduler.submit_job()
  └─ compute.py run() on Celery worker

User views /my-tasks/{job_id}
  ├─ Job info header                 ← framework (automatic)
  ├─ Stat cards                      ← framework reads _stat_cards from result
  ├─ Input parameters table          ← framework reads job.params
  └─ Tool results                    ← your results_layout(job)
```

---

## Reference Implementations

| Tool | Use as... | Location |
|------|-----------|----------|
| **Reaction Similarity** | Primary real-world example — modal with sections, form validation, compute with stat cards, AG Grid with SVG rendering | [`enzyme_tk_app/app/tools/reaction_similarity/`](../enzyme_tk_app/app/tools/reaction_similarity/) |
| **Timer Tool Template** | Minimal skeleton — simplest possible tool | [`enzyme_tk_app/app/tools/timer_tool_template/`](../enzyme_tk_app/app/tools/timer_tool_template/) |
