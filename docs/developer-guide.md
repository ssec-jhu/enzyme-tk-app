# Developer Guide — Adding a New Tool

This guide walks through how to add a new tool to the EnzymeTK Tool Suite, from folder creation to results rendering. It covers the conventions you must follow, which shared components to reuse, and what custom code you write. The [Reaction Similarity](../enzyme_tk_app/app/tools/reaction_similarity/) tool is used as the running example throughout.

> **Minimal skeleton:** For the simplest possible tool with no custom UI, see [`timer_tool_template/`](../enzyme_tk_app/app/tools/timer_tool_template/).


## How Do I Add a New Tool?

1. **Create a folder** under `enzyme_tk_app/app/tools/` named after your slug with underscores (e.g., `reaction_similarity/` for slug `"reaction-similarity"`).
2. **Add `__init__.py`** exporting `TOOL_DEF: ToolDef` — the single source of truth for slug, title, description, icon, and display order.
3. **Add an icon constant** to `enzyme_tk_app/app/components/icons.py` (free FontAwesome only) and import it in your `TOOL_DEF`.
4. **Create `modal.py`** — build the input form using the shared modal helpers for header, section dividers, footer, and submission placeholder.
5. **Create `callbacks.py`** — wire the modal open/close, form validation, and job submission.
6. **Create `results.py`** (optional) — build a custom results layout. Read this section first to understand what the framework renders automatically, so you know which special keys to return from `compute.py`.
7. **Create `compute.py`** — implement `run(params) → dict` with your algorithm. This runs on the Celery worker. Return the special keys described in the Results section (e.g., `_stat_cards`, `dataframe`).
8. **Create `check_data.py`** (optional) — if the tool depends on bundled data (model weights, prebuilt databases, reference files), export `check_data() → list[str]` returning labels for any missing items (empty list = data OK). A non-empty list renders a "Missing data" badge on the tool card.
9. **Run `tox -e format && tox`** to format and validate.
10. **Done.** The tool auto-appears on the home page — no central file to edit.

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
- **Ruff** for formatting and linting — run `tox -e format` to auto-format.

## File Layout

Each tool is a sub-package with up to six files:

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `check_data.py` | No | `check_data() → list[str]` | Reports missing bundled data; a non-empty list renders a "Missing data" badge on the tool card |

### Auto-discovery

The module `enzyme_tk_app/app/tools/__init__.py` uses `pkgutil.iter_modules()` to scan sub-packages at import time. For each sub-package it:

1. Imports `__init__.py` and reads `TOOL_DEF` (validates required keys).
2. Imports `callbacks.py` (side-effect: registers `@callback` decorators).
3. Imports `modal.py` and collects the `modal()` factory.
4. Imports `results.py` and collects `results_layout()` into `RESULTS_LAYOUTS`.
5. Imports `check_data.py` (if present) and registers `check_data()` into `CHECK_DATA`, keyed by slug.

No central registry file to edit — just create your folder and the tool appears.

### 1. Tool Definition — `__init__.py`

`TOOL_DEF` is the single source of truth for your tool's identity. Import it in every other file in your tool package — never hardcode the slug, title, or icon.

### 1.1 `ToolDef` fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | `str` | Yes | URL-safe identifier, hyphens not underscores (e.g., `"reaction-similarity"`) |
| `title` | `str` | Yes | Human-readable name (e.g., `"Reaction Similarity"`) |
| `desc` | `str` | Yes | 1–2 sentence description for the tool card |
| `icon` | `str` | Yes | FontAwesome class string from `icons.py` |
| `order` | `int` | Yes | Display position — lower numbers appear first |
| `libraries` | `list[str]` | No | Package names shown as badges (e.g., `["rdkit"]`) |
| `max_duration` | `int` | No | Timeout in seconds (default: 3600) |

### 1.2 Example — Reaction Similarity

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

---

### 2. Modal Layout — `modal.py`

The modal is the input form shown when a user clicks "Launch →" on the tool card. Every modal follows the same structural pattern using shared helpers from `enzyme_tk_app.app.components.modal_helpers`.

### 2.1 What you reuse

Five shared helper functions provide the standard modal chrome:

| Helper | What it creates |
|--------|----------------|
| `create_modal_header(icon, title)` | Header bar with tool icon, title, and close button |
| `create_modal_input_section_header()` | "Input Data" section divider with flask icon |
| `create_modal_config_section_header()` | "Tool Configurations" section divider with gear icon |
| `create_modal_footer(slug)` | Cancel (outline) + Run (primary) buttons with correct IDs |
| `create_modal_submission_results(slug)` | Placeholder div for job-ID confirmation or validation errors |

### 2.2 What you add

Your custom code goes inside two `html.Div(className="bg-light p-3 rounded mb-3")` sections:

**Section 1 — Input Data:** The primary inputs for your tool (task name, SMILES input, file upload, sequence textarea, etc.). Use `dbc.Row`/`dbc.Col` for label ↔ control alignment.

**Section 2 — Tool Configurations:** Optional tuning parameters (algorithm selectors, database pickers, result limits, etc.).

### 2.3 Example — Reaction Similarity modal structure

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
                    children=
                    [

                        # ✦ REUSED — shared section header
                        create_modal_input_section_header(),

                        # CUSTOM ROW — Task Name input
                        dbc.Row([
                            dbc.Col(dbc.Label("Task Name", className="col-form-label fw-bold"), width=3),
                            dbc.Col(dbc.Input(
                                id=f"id-input-{TOOL_DEF['slug']}-task-name",
                                type="text",
                                className="themed-control",
                            ), width=9),
                        ], className="mb-2", align="center"),

                        # CUSTOM ROW — inouts need to be set by user
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
                    children=
                    [
                        # ✦ REUSED — shared section header
                        create_modal_config_section_header(),

                        # CUSTOM — Other inputs needed for the tool with defaults set
                        dbc.Row([...], className="mb-2", align="center"),
                        
                        ...

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


### 3. Callbacks — `callbacks.py`

Callbacks wire the modal to the backend. Most tools need four callbacks:

| Callback | Trigger | What it does |
|----------|---------|-------------|
| `toggle_<slug>_modal` | Launch button / Cancel button | Opens or closes the modal |
| `validate_<slug>_form` | Any form field change | Enables/disables submit based on validation |
| `populate_example_<type>` | Example dropdown selection | Fills the input field with demo data |
| `submit_<slug>_job` | Submit button / Launch button | Submits job to scheduler; clears stale results on reopen |

### 3.1 What you reuse

- **`get_task_scheduler()`** from `enzyme_tk_app.app.backend` — the singleton scheduler.
- **Launch button ID** auto-generated by `tool_cards.py`: `f"id-btn-launch-{TOOL_DEF['slug']}"` — you never create this button, you just reference its ID.
- **Session ID** via `flask.g.session_id` — anonymous UUID cookie.
- **`raise PreventUpdate`** from `dash.exceptions` — for guard clauses instead of returning empty values.

### 3.2 What you add

- **Validation logic** specific to your form fields.
- **Job parameter assembly** — build the `params` dict from form `State` values.
- **Example data population** — if your tool has demo examples.

### 3.3 Example — Reaction Similarity callbacks


See [reaction_similarity/callbacks.py](../enzyme_tk_app/app/tools/reaction_similarity/callbacks.py) for the implementation.

### 3.4 Database-backed tools — the shared contract

Every tool that reads reference databases from the data directory follows the same contract. Do not invent a per-tool variant.

| Layer | Rule |
|-------|------|
| `modal.py` | One `dcc.Dropdown` with `multi=True`, id `f"id-dropdown-{TOOL_DEF['slug']}-databases"` (plural), **every option pre-selected** — the broadest search is the default. |
| `callbacks.py` | The submit callback validates the selection with `validate_db_names(names, suffix)` from `enzyme_tk_app.app.utils.data_loading` before it reaches `params`. |
| `compute.py` | `params["databases"]` is a `list[str]`. Load each one, tag its rows with the `database` column (`COL_DATABASE`), and `pd.concat` them into **one** reference set so ranking is global rather than per-database. |
| `compute.py` | An unreadable database is **skipped**, not fatal — collect its name and keep going. Raise only when *every* selection failed; an empty grid would otherwise be indistinguishable from a legitimate "no hits found". |
| `compute.py` | Report the outcome in `_stat_cards`: a **Databases Searched** count, plus a **Databases Skipped** card naming the failures when there are any. Never a single `Database` card holding a filename. |
| `results.py` | Include the `database` column in the grid so a hit's origin is visible: `{"field": col.COL_DATABASE, "headerName": "Database", "width": 140}`. The column is required; the label is not — Func-E uses the same `col.COL_DATABASE` field but labels it with the raw column name (see §4.2, *Header labels*). |
| Dependent dropdowns | Anything derived from the selection (e.g. the EC-number filter) offers the **union** across the selected files and clears its own value when the selection changes. |

`validate_db_names(names, suffix=None)` is the single validator for all of them — names arrive from the browser and become filesystem paths, so they are checked at that trust boundary even though the UI only ever offers legitimate options. It **verifies without modifying**: an invalid name is rejected, never repaired. Following `validate_top_n`, it returns an error message (or `None` when valid) for an empty selection or a name that is not a bare `[0-9A-Za-z_-]+` plus the optional suffix (`".csv"`, `".pkl"`, or `None` for directory-style FoldSeek databases) — return that message straight into the modal's submission-results div. It *raises* `TypeError` if handed a bare string instead of a list, since that is a programming error (a `multi=False` dropdown) rather than bad user input.


### 4. Results Page — `results.py`

The results page is what users see when they click "View Results" on a completed job. The framework provides a lot of UI for free — your `results_layout()` function only handles the tool-specific visualisation.

> **Why results before compute?** Understanding what the framework auto-renders tells you which special keys your `compute.py` should return (e.g., `_stat_cards`, `dataframe`). Read this section first, then write your `run()` function to supply those keys.

### 4.1 What the framework gives you for free

These are rendered automatically by `my_tasks_view_results.py` — you do NOT build these in your `results.py`:

| Component | Source | What it shows |
|-----------|--------|---------------|
| **Job info header** | `_build_job_info_header()` | Tool name, status badge, submitted/completed timestamps, duration, expiry |
| **Stat cards** | `_build_job_info_header()` | The framework always renders **Duration** and **Expires In** cards first, then appends any tool-defined `_stat_cards` items from your compute return dict. |
| **Input parameters table** | `build_result_input_params()` | Auto-rendered from `job.params`. SMILES values get inline structure previews. Use `_params_exclude` to hide internal keys. |
| **Status-dependent rendering** | Framework | PENDING/STARTED: progress banner with auto-refresh. FAILURE/REVOKED/TIMEOUT: error details. SUCCESS: your `results_layout()` is called. |

### 4.2 What you add

Your `results_layout(job: JobInfo) -> html.Div` function receives the completed job and renders the tool-specific content — typically an AG Grid table:

1. **Define columns** — prepend tool-specific columns (e.g., SVG images), then append shared columns via `shared_col_defs()`.
2. **Build the grid** — call `build_ag_grid(column_defs, df_payload)`.
3. **Handle empty results** — return a message if no data.

#### Shared helpers from `results_helpers.py`

| Helper | What it provides |
|--------|-----------------|
| `shared_col_defs()` | 25+ pre-defined column definitions for similarity scores, database metadata, and molecular descriptors. Only columns present in your data are displayed. |
| `sequence_col_def(field, width=300, header=None)` | The column def for an amino-acid sequence column — truncated to one line with the full sequence on hover. Always use it instead of hand-rolling a `cellStyle`. |
| `numeric_col_def(field, header=None, width=None, decimals=None, exponential=False)` | The column def for a numeric column. Always applies `agNumberColumnFilter`; formatting is opt-in — omit `decimals` for integers, `decimals=4` for fractions, `decimals=2` for percentages, `exponential=True` for e-values. Pick from the data, not by habit. |
| `build_ag_grid(column_defs, df_payload)` | Standardized AG Grid with pagination (20 rows/page), Balham theme, tooltips, copy/paste, and column filtering. |
| `build_result_stat_cards(job)` | Renders stat cards from `_stat_cards` in your compute result. Called by the framework, not by your code. |
| `build_result_input_params(job)` | Auto-renders submitted parameters. Called by the framework, not by your code. |

#### AG Grid column rules

| Column type | `autoHeight` | `filter` | `sortable` | Notes |
|-------------|-------------|----------|------------|-------|
| Short text / number | — | `True` or `agNumberColumnFilter` | `True` | Default — fastest rendering |
| SVG / image | `True` | `False` | `False` | Row expands to fit image |
| Long text (wrap) | `True` | `True` | `True` | Add `cellClass: "cell-wrap-dash-ag-grid"` |

**Performance note:** Only enable `autoHeight` on columns that truly need it. Fixed-height rows render significantly faster.

**Write every column out in full:** `_get_column_defs()` is the one place a reader can see what the table contains, so every column gets its own visible line with its field name spelled out literally — never a loop, comprehension, or f-string that builds `field` from another list. `build_ag_grid()` renders only fields that have a def, so a generated name both hides the column at the call site and silently drops any column the generating list fails to name (no error, no log). Share *rules* freely — `numeric_col_def`, `sequence_col_def`, `shared_col_defs()`, and `col.COL_*` from `utils/columns.py` for anything cross-tool (`col.COL_ENTRY`, `col.COL_DATABASE`, `col.COL_SEQUENCE`) — but spell out *identity*. A bare literal is right only when the name is one library's output contract, as Func-E's `enzymetk`-named `Funce_*` columns are. As a safety net, `tools/funce/results.py` also appends a bare `{"field": c, "headerName": c}` for any payload column its explicit list does not name, so a column added by a newer `enzymetk` appears unstyled rather than vanishing.

**Header labels:** `headerName` is optional — omit it and AG Grid humanises the field name; the `header=` argument of `numeric_col_def` / `sequence_col_def` sets it. Most tools pass a friendly label (`"Alignment Length"`), and new tools should. **Func-E is a deliberate exception:** `tools/funce/results.py` sets every `headerName` to its own `field`, so its headers are the raw enzymetk column names (`Funce_prediction`, `Funce_substrates_MolWt_mean`, `database`) — a number must be traceable to the exact enzymetk column, and humanisation misreports these names (`Funce_substrates_MolWt_mean` → "Funce_substrates Mol Wt_mean"). `enzyme_tk_app/app/tests/test_tools_funce.py` guards it; do not copy the pattern to other tools.

### 4.3 Result page layout schematic

The diagram below shows the full results page from top to bottom. Sections marked **AUTO** are rendered automatically — you don't touch them. The section marked **YOUR CODE** is where your `results_layout()` output is inserted.

```
┌─────────────────────────────────────────────────────────┐
│  AUTO  ·  Job Info Header                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Tool icon + title     Status badge (SUCCESS, …)   │  │
│  │ Submitted: 2025-01-15 10:32   Duration: 12.4s     │  │
│  │ Completed: 2025-01-15 10:33   Expires:  24h       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  AUTO  ·  Stat Cards  (from _stat_cards)                │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────┐  │
│  │  Label 1   │ │  Label 2   │ │  Label 3   │ │  …   │  │
│  │  value 1   │ │  value 2   │ │  value 3   │ │  …   │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────┘  │
│                                                         │
│  AUTO  ·  Input Parameters Table  (from params)         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Input 1        │ value from params dict           │  │
│  │ Input 2        │ value from params dict           │  │
│  │ Input 3        │ value from params dict           │  │
│  │ …              │ …                                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ - - - ─ ─ ─ ─ ─ ─ ─ ─ │
│                                                         │
│  YOUR OUTPUT from results_layout(job) output            │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Example: G Grid (or any custom visualisation)    │  │
│  │  ┌─────────┬──────────┬──────────┬────────────┐   │  │
│  │  │ Rxn SVG │ Tanimoto │ Database │ …columns   │   │  │
│  │  ├─────────┼──────────┼──────────┼────────────┤   │  │
│  │  │  [img]  │  0.95    │  rhea    │  …         │   │  │
│  │  │  [img]  │  0.87    │  brenda  │  …         │   │  │
│  │  └─────────┴──────────┴──────────┴────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 4.4 Example — Reaction Similarity results

See [reaction_similarity/results.py](../enzyme_tk_app/app/tools/reaction_similarity/results.py) for the full implementation. Note how minimal this file is — the framework handles stat cards, input parameters, and job metadata. Your code only defines the tool-specific columns and builds the grid.


### 5. Compute — `compute.py`

This module exports `run(params: dict) -> dict`. It runs on the Celery worker — not in the web process. The `params` dict contains the form fields submitted by the callback.

### 5.1 Return dict conventions

Your `run()` function returns a plain dict. The framework recognises several special keys that drive the auto-rendered UI described in the Results section above:

| Key | Type | Required | Purpose |
|-----|------|----------|---------|
| `_stat_cards` | `list[dict]` | No | Summary cards rendered in the results header. Each item: `{"label": "...", "value": "..."}`. The framework already provides **Duration** and **Expires In** cards automatically — do not duplicate them here. |
| `_params_exclude` | `list[str]` | No | Parameter keys to hide from the auto-rendered input table. The results section automatically puts all input params in the results page. |
| `dataframe` | `dict` | No | Tabular results: `{"columns": [...], "data": [{...}, ...]}` for AG Grid display |

**Do NOT echo input parameters** in the return dict. The framework stores `params` separately and auto-renders them via `build_result_input_params()`.

### 5.2 Example — Reaction Similarity compute

See [reaction_similarity/compute.py](../enzyme_tk_app/app/tools/reaction_similarity/compute.py) for the full implementation.


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
| `ETK_ADMIN_TOKEN` / `ETK_SECRET_KEY` | Same admin secrets as local dev — see [Admin Secrets](../README.md#admin-secrets-env) |

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
Azure Files share, mounted read-only at `/app-data` on web and worker. Files
must be uploaded directly to the share; they are not part of the container
image. The local `data/<subdir>/` path maps to the same `<subdir>/` path on
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