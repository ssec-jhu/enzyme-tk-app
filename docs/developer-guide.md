# Developer Guide — Adding a New Tool

This guide walks through how to add a new tool to the EnzymeTK Tool Suite, from folder creation to results rendering. It covers the conventions you must follow, which shared components to reuse, and what custom code you write. The [Reaction Similarity](../enzyme_tk_app/app/tools/reaction_similarity/) tool is used as the running example throughout.

> **Minimal skeleton:** [`timer_tool_template/`](../enzyme_tk_app/app/tools/timer_tool_template/) is the smallest tool that still follows the *whole* shared paradigm — Task Name, example picker, all four callbacks, an AG Grid results layout — over a `compute.py` that only sleeps. Mirror it; it is the canonical reference, not a reduced special case.


## How Do I Add a New Tool?

1. **Create a folder** under `enzyme_tk_app/app/tools/` named after your slug with underscores (e.g., `reaction_similarity/` for slug `"reaction-similarity"`).
2. **Add `__init__.py`** exporting `TOOL_DEF: ToolDef` — the single source of truth for slug, title, description, icon, and display order.
3. **Add an icon constant** to `enzyme_tk_app/app/components/icons.py` (free FontAwesome only) and import it in your `TOOL_DEF`.
4. **Create `modal.py`** — build the input form using the shared modal helpers for header, section dividers, footer, and submission placeholder.
5. **Create `callbacks.py`** — wire the modal open/close, form validation, and job submission.
6. **Create `results.py`** (optional) — build a custom results layout. Read this section first to understand what the framework renders automatically, so you know which special keys to return from `compute.py`.
7. **Create `compute.py`** — implement `run(params) → dict` with your algorithm. This runs on the Celery worker. Return the special keys described in the Results section (e.g., `_stat_cards`, `dataframe`).
8. **Create `check_data.py`** (optional) — if the tool depends on bundled data (model weights, prebuilt databases, reference files), export `check_data() → list[str]` returning labels for any missing item, and for any file that is present but unusable, the reason (empty list = data OK). A non-empty list renders a "Missing data" badge on the tool card.
9. **Write `test_tools_<folder>.py`** — one test file per tool under `enzyme_tk_app/app/tests/`. See [Tests](#tests).
10. **Verify** — `tox run -e format`, then `tox`. See [Run and Verify](#run-and-verify).
11. **Done.** The tool auto-appears on the home page — no central file to edit.

If your tool reads bundled data (databases, model weights, reference files), also read [Bundled Data and Paths](#bundled-data-and-paths) before step 7.

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

**Tooltip targets are the exception to that rule** — `dbc.Tooltip` binds by `target=`, so the target needs an id with no callback of its own: `id-icon-<slug>-databases-info` from `create_modal_databases_label()`, and `id-data-warning-<slug>` from [`components/data_warning.py`](../enzyme_tk_app/app/components/data_warning.py).

**Framework-owned ids are the exception to the *slug-scoping* rule.** They are callback-bound like any other, just not by *your* callback, and they are not slug-scoped because only one tool's results render at a time: `build_ag_grid()` sets `id="id-grid-results"` on the grid and owns the ids of its CSV-export controls, which its own `download_results_csv` callback drives. Your `results.py` never sets or overrides them.

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

## File Layout

Each tool is a sub-package with up to six files:

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `check_data.py` | No | `check_data() → list[str]` | Reports missing (or present-but-unusable) bundled data; a non-empty list renders a "Missing data" badge on the tool card |

### Auto-discovery

The module `enzyme_tk_app/app/tools/__init__.py` uses `pkgutil.iter_modules()` to scan sub-packages at import time. For each sub-package it:

1. Imports `__init__.py` and reads `TOOL_DEF` (validates required keys).
2. Imports `callbacks.py` (side-effect: registers `@callback` decorators).
3. Imports `modal.py` and collects the `modal()` factory.
4. Imports `results.py` and collects `results_layout()` into `RESULTS_LAYOUTS`.
5. Imports `check_data.py` (if present) and registers `check_data()` into `CHECK_DATA`, keyed by slug.

No central registry file to edit — just create your folder and the tool appears.

## Shared Utilities — Read Before You Write

Most of what a tool needs already exists. Reach for these before writing your own; the sections below cross-reference them where they apply.

| Module | Reuse it for |
|--------|-------------|
| [`components/modal_helpers.py`](../enzyme_tk_app/app/components/modal_helpers.py) | The six modal chrome helpers — header, both section dividers, databases label, footer, submission placeholder (§2.1) |
| [`components/results_helpers.py`](../enzyme_tk_app/app/components/results_helpers.py) | `build_ag_grid()`, `shared_col_defs()`, `numeric_col_def()`, `sequence_col_def()`, and the stat-card / input-parameter renderers (§4.2) |
| [`components/icons.py`](../enzyme_tk_app/app/components/icons.py) | `ICON_TOOL_*` constants. Add yours here — free FontAwesome only — and import it in `TOOL_DEF` |
| [`utils/columns.py`](../enzyme_tk_app/app/utils/columns.py) | `COL_*` constants for every column name more than one tool touches — `COL_ENTRY`, `COL_SEQUENCE`, `COL_EC_NUMBER`, `COL_DATABASE`, `COL_TANIMOTO`, … Never hardcode a shared column string; a literal is right only when the name is one library's output contract |
| [`utils/data_loading.py`](../enzyme_tk_app/app/utils/data_loading.py) | The `get_*_database_options()` builders, `validate_db_names()`, `scan_sequence_databases()`, `sequence_db_separator()`, `load_sequence_data()`, `load_and_clean_data()`, `get_ec_numbers()`, `get_top_n_sorted_results()` (§3.4) |
| [`utils/formatting.py`](../enzyme_tk_app/app/utils/formatting.py) | `validate_top_n()` — every Top-N field calls it in the submit callback; it accepts 1–500 and returns an error message or `None`, never raises. Also `round_column_values()`, `format_duration()`, `expires_in()`, `truncate_id()` |
| [`utils/smiles_rendering.py`](../enzyme_tk_app/app/utils/smiles_rendering.py) | `smiles_to_svg_data_uri()`, `reaction_to_svg_data_uri()`, and `generate_cached_svg_uris(series, render_fn, **kwargs)` which renders each *unique* SMILES once — this is what fills an `SvgRenderer` column (§4.2) |
| [`utils/smiles_validation.py`](../enzyme_tk_app/app/utils/smiles_validation.py) | `validate_reaction_smiles()` (reactions) and `validate_smiles()` (one molecule) — an error message or `None`, like `validate_db_names()`. Every SMILES field calls one of them in **three** places: the form callback (gates Run, marks the field), the submit callback (the client gate is bypassable) and `run()` (a replayed job skips the modal). The message carries RDKit's own reason (`unclosed ring`) via `rdBase.CaptureErrorLog`, never an echo of the input. Also `split_reaction()`. rdkit is imported inside the functions, so `callbacks.py` can import this at module scope |
| [`paths.py`](../enzyme_tk_app/app/paths.py) | Every shared data-directory constant ([Bundled Data and Paths](#bundled-data-and-paths)) |
| [`tests/conftest.py`](../enzyme_tk_app/app/tests/conftest.py) | Shared fixtures and tree-walking helpers for your tests ([Tests](#tests)) |

## Bundled Data and Paths

Skip this if your tool computes from user input alone. If it reads databases, model weights, or reference files, everything below applies before you write `compute.py` or `check_data.py`.

**Every shared data directory is a constant in [`paths.py`](../enzyme_tk_app/app/paths.py)** — never build a path from `__file__` or a string literal. All of them derive from `DATA_DIR`, which is the `ETK_DATA_DIR` environment variable falling back to the bundled `enzyme_tk_app/app/data/`:

| Constant | Directory | Read by |
|----------|-----------|---------|
| `SEQUENCES_DIR` | `sequences/` | Sequence Similarity |
| `REACTIONS_DIR` | `reactions/` | Reaction and Substrate/Product Similarity |
| `STRUCTURES_DIR` | `structures/` | Sequence and Structure-Based Similarity |
| `FOLDSEEK_DB_DIR` | `foldseek_db/` | Sequence and Structure-Based Similarity |
| `FOLDSEEK_MODELS_DIR` | `foldseek_models/` | Prefix only — the parent of the constant below. Tools do not reference it directly |
| `FOLDSEEK_WEIGHTS_DIR` | `foldseek_models/weights/` | Sequence and Structure-Based Similarity |
| `SEQUENCE_EMBEDDINGS_DIR` | `sequence_embeddings/` | Func-E |
| `FUNCE_MODELS_DIR` | `funce_models/` | Func-E |
| `UNIMOL_WEIGHTS_DIR` | `unimol_weights/` | Func-E (reaction encoding). `funce/compute.py` passes it to the `Funce_rxnfp_unimol` step as `unimol_weights_dir` |

**What belongs in `paths.py` and what does not.** A path goes here when it is large, versioned independently of any single tool, or plausibly reusable by a future one. A path used only inside one tool module stays in that module and derives from `DATA_DIR` itself.

**A shared directory is named for its data, not for its reader.** `sequence_embeddings/` holds protein embedding tables — it is not `funce_db/` just because Func-E is today's only consumer, and its option builder is `get_sequence_embedding_database_options()`. `unimol_weights/` is the same case for model weights: it holds the UniMol checkpoint that Func-E's reaction encoder loads, so it is named for the model rather than `funce_unimol/`. A directory takes a tool's name only when the tool genuinely owns it: `foldseek_db/` and `foldseek_models/` (foldseek's own identifiers) and `funce_models/` (Func-E's EC checkpoints).

**The data is not in the repository.** The large sets are gitignored and `docker-compose.yml` bind-mounts the directory **read-only** at `/app-data`. Two consequences: your code may never write into `DATA_DIR`, and your tests must build their own fixture files rather than reading `data/` (see [Tests](#tests)). It is filled by [`scripts/db_build/`](../scripts/db_build/README.md): `download_data.py` downloads the public weights and structure databases, `build_enzyme_db.py` builds a FoldSeek database and an embeddings pickle from your own sequence file, and both write straight into `DATA_DIR`. Adding a directory therefore means two edits outside your tool: a row in the Data Directories table in [README](../README.md#data-directories) — link to it, don't copy it here — and the matching line in `download_data.py`'s `report()`, which duplicates every `check_data.py` because it runs in an image without this package (AGENTS.md states the contract).

**Report what is missing with `check_data.py`.** Because a directory can legitimately be absent, a tool that needs one exports `check_data() -> list[str]` returning a label per missing item; an empty list means the data is fine. Label each item the way a user will look for it on disk — `"Func-E ensemble checkpoints (data/funce_models/)"` — and include files that are present but unusable, with the reason. The badge and its tooltip are rendered by [`components/data_warning.py`](../enzyme_tk_app/app/components/data_warning.py), not by your tool. Keep the check cheap: it runs on every home-page render, so existence and non-empty checks are free, a check that must open a file reads only the header and caches on `(path, mtime, size)`, and nothing here ever reads a full column. See [funce/check_data.py](../enzyme_tk_app/app/tools/funce/check_data.py) for the simple shape and [sequence_similarity/check_data.py](../enzyme_tk_app/app/tools/sequence_similarity/check_data.py) for one that reports column-contract failures.

## 1. Tool Definition — `__init__.py`

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
| `max_duration` | `int` | No | Timeout in seconds. Defaults to `DEFAULT_MAX_DURATION` (3600) in `backend/celery_app.py`. See below |

**`max_duration` is two limits, not one.** It becomes Celery's `soft_time_limit`: when it expires the worker raises `SoftTimeLimitExceeded`, which the task catches and records as status `TIMEOUT` (not `FAILURE`). The hard kill is `max_duration + HARD_TIMEOUT_GRACE_SECONDS` (60 s), so cleanup code gets a window to run. Both constants live in `backend/celery_app.py` and are env-overridable. Set `max_duration` whenever your tool can outrun the 3600 s default in either direction — the timer template uses 600, Func-E 1800.

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

## 2. Modal Layout — `modal.py`

The modal is the input form shown when a user clicks "Launch →" on the tool card. Every modal follows the same structural pattern using shared helpers from `enzyme_tk_app.app.components.modal_helpers`.

### 2.1 What you reuse

Six shared helper functions provide the standard modal chrome:

| Helper | What it creates |
|--------|----------------|
| `create_modal_header(icon, title)` | Header bar with tool icon, title, and close button |
| `create_modal_input_section_header()` | "Input Data" section divider with flask icon |
| `create_modal_config_section_header()` | "Tool Configurations" section divider with gear icon |
| `create_modal_databases_label(slug, contents)` | The "Databases" label column plus an info icon whose tooltip is `contents` — one sentence on what those databases hold (database-backed tools only) |
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


## 3. Callbacks — `callbacks.py`

Callbacks wire the modal to the backend. Every tool — the timer template included — has the same four:

| Callback | Trigger | What it does |
|----------|---------|-------------|
| `toggle_<slug>_modal` | Launch button / Cancel button | Opens or closes the modal |
| `validate_<slug>_form` | Any form field change (**no** `prevent_initial_call`) | Enables submit once every required field has a value — omitting `prevent_initial_call` is what makes the Run button start disabled on an empty form |
| `populate_example_<type>` | Example dropdown selection | Fills the input field with demo data **and the Task Name** (the example's `task_name` verbatim, returned last) |
| `submit_<slug>_job` | Submit button / Launch button | Submits job to scheduler; clears stale results on reopen |

### 3.1 What you reuse

- **`get_task_scheduler()`** from `enzyme_tk_app.app.backend` — the singleton scheduler.
- **Launch button ID** auto-generated by `tool_cards.py`: `f"id-btn-launch-{TOOL_DEF['slug']}"` — you never create this button, you just reference its ID.
- **Session ID** via `flask.g.session_id` — anonymous UUID cookie.
- **`raise PreventUpdate`** from `dash.exceptions` — for guard clauses instead of returning empty values.

### 3.2 What you add

- **Validation logic** specific to your form fields — check **presence, not validity**. A `dbc.Input(type="number", min=…, max=…)` hands the callback `None` when the browser rejects what was typed, so an out-of-range entry already disables the button; the range check in the submit callback is the server-side backstop for a request that bypasses the UI (see the **`write-callback`** agent §4).
- **Job parameter assembly** — build the `params` dict from form `State` values.
- **Example data population** — if your tool has demo examples. Each example dict carries a `task_name` alongside its `label`/`value`, and the callback prefills the Task Name field with it verbatim so an example run is submittable in one click. Don't prepend the tool slug — the My Tasks table already shows the tool in the neighbouring column.

### 3.3 Example — the submit callback

The submit callback is the only one with a fixed shape. It is triggered by **two** buttons — Submit and Launch — because reopening the modal must clear the job ID left over from the previous submission:

```python
@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    Input(f"id-btn-launch-{TOOL_DEF['slug']}", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    State(f"id-dropdown-{TOOL_DEF['slug']}-databases", "value"),
    State(f"id-input-{TOOL_DEF['slug']}-top-n", "value"),
    prevent_initial_call=True,
)
def submit_my_tool_job(submit_clicks, launch_clicks, task_name, databases, top_n):
    """Submit a job, or clear stale results when the modal is reopened."""
    # Reopened, not submitted — wipe the previous job ID.
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""

    # Re-validate server-side even though the UI disables submit: these values
    # are browser-controlled State, and the database names become file paths.
    if not task_name or not task_name.strip():
        raise PreventUpdate

    error = validate_db_names(databases, get_sequence_database_options())
    if error:
        return error
    error = validate_top_n(top_n)
    if error:
        return error

    scheduler = get_task_scheduler()
    job_id = scheduler.submit_job(
        tool_slug=TOOL_DEF["slug"],
        # Key order mirrors the modal's field order — see §4.1.
        params={
            "task_name": task_name.strip(),
            "databases": databases,
            "top_n": int(top_n),
        },
        session_id=g.session_id,
    )
    return f"Job submitted — ID: {job_id}"
```

Three rules the skeleton encodes:

- **Validators return, they don't raise.** `validate_db_names()` and `validate_top_n()` hand back a message string, which you return straight into the submission-results div. An exception would surface as an HTTP 500 on `/_dash-update-component` instead of as text in the modal, because the app installs no Dash `on_error` handler.
- **`raise PreventUpdate`** is for "nothing to say" — a guard that should leave the DOM untouched. A user-facing problem is a returned string.
- **`params` key order is the display order** of the Input Parameters table on the results page (§4.1), so list the keys in the order the fields appear in your modal.

See [reaction_similarity/callbacks.py](../enzyme_tk_app/app/tools/reaction_similarity/callbacks.py) and [funce/callbacks.py](../enzyme_tk_app/app/tools/funce/callbacks.py) for the full implementations.

### 3.4 Database-backed tools — the shared contract

Every tool that reads reference databases from the data directory follows the same contract. Do not invent a per-tool variant. Read [Bundled Data and Paths](#bundled-data-and-paths) first — it covers where those directories come from and how a missing one is reported.

| Layer | Rule |
|-------|------|
| `modal.py` | One `dcc.Dropdown` with `multi=True`, id `f"id-dropdown-{TOOL_DEF['slug']}-databases"` (plural), **every option pre-selected** — the broadest search is the default. Each option's `label` and `value` are both the exact name on disk — the full filename, extension included, or the folder name for FoldSeek (see *Database naming* below). The label column is `create_modal_databases_label(TOOL_DEF["slug"], contents)`, so every tool's "Databases" field carries an info icon whose tooltip is one sentence on what those databases hold (columns or payload, not selection mechanics). |
| `callbacks.py` | The submit callback validates the selection with `validate_db_names(names, options)` from `enzyme_tk_app.app.utils.data_loading` before it reaches `params`, passing the tool's own `get_*_database_options()` list as *options*. |
| `compute.py` | `params["databases"]` is a `list[str]`. Load each one, tag its rows with the `database` column (`COL_DATABASE`, value `csv_path.name` — the full filename, no prettifying), and `pd.concat` them into **one** reference set so ranking is global rather than per-database. |
| `compute.py` | A database that cannot be used is **skipped**, not fatal — collect its name and keep going. "Cannot be used" is missing or unreadable, and for `data/sequences/` also "no longer meets the column contract" (deleted or edited between submission and execution). Raise only when *every* selection failed; an empty grid would otherwise be indistinguishable from a legitimate "no hits found". |
| `compute.py` | Report the outcome in `_stat_cards`: a **Databases Searched** count, plus a **Databases Skipped** card naming the failures when there are any (as the sanitised `safe_name` — the full filename, so `bad.txt` reads `bad.txt`, and the same names go into the all-failed error message). Never a single `Database` card holding a filename. |
| `results.py` | Include the `database` column in the grid so a hit's origin is visible: `{"field": col.COL_DATABASE, "headerName": "Database", "width": 140}`. The column is required; the label is not — Func-E uses the same `col.COL_DATABASE` field but labels it with the raw column name (see §4.2, *Header labels*). |
| Dependent dropdowns | Anything derived from the selection (e.g. the EC-number filter) offers the **union** across the selected files and clears its own value when the selection changes. |

`validate_db_names(names, options)` is the single validator for all of them — names arrive from the browser and become filesystem paths, so they are checked at that trust boundary even though the UI only ever offers legitimate options. It **verifies without modifying**: an invalid name is rejected, never repaired.

The check is **membership in *options*** — the very list the tool's `get_*_database_options()` builder just produced, of which only each dict's `value` is read:

```python
error = validate_db_names(databases, get_sequence_database_options())
if error:
    return error
```

An exact allowlist is stronger than the pattern match it replaced: there is no traversal to match, no second extension to smuggle, and a database the builder filtered out — a `data/sequences/` file that fails the column contract below, say — is rejected here for free with no extra code. Build the options inside the callback rather than caching them at import time, so a database added or removed on disk takes effect immediately.

Following `validate_top_n`, it returns an error message (or `None` when valid) for an empty selection (`"At least one database must be selected."`), a bare string handed in instead of a list (a `multi=False` leftover: `"Expected a list of database names, got a single name: …"`), or any name the tool does not currently offer (`"Unknown database: 'x'"`) — return that message straight into the modal's submission-results div. It never raises: the value is a browser-controlled `State`, and since the app installs no Dash `on_error` handler an exception would surface as an HTTP 500 on `/_dash-update-component` instead of as a message in the modal.

**What makes a file a database — `data/sequences/` only.** A file there is a sequence database when **both** hold: its extension is one of `SEQUENCE_DB_SUFFIXES` (`.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`) **and** its header carries every one of `REQUIRED_SEQUENCE_COLUMNS` — `Entry`, `Sequence`, `EC number`. Everything else in the file is **metadata the app never enumerates**: it is not validated, not listed anywhere, and rides through the search into the results grid untouched. `scan_sequence_databases()` in [`utils/data_loading.py`](../enzyme_tk_app/app/utils/data_loading.py) is the one scan behind both consumers — `get_sequence_database_options()` takes its names, `sequence_similarity/check_data.py` takes its `problems` lines (`badfile.csv — missing columns: Sequence, EC number`). A non-compliant file is therefore **not offered in the dropdown at all**, and the home-page "Missing data" tooltip is where it and its missing columns are named; a file that vanished with no explanation would be worse than one flagged. `compute.run()` re-derives the usable set itself — the worker reads `params` out of Redis, so it trusts no submit-time check — and skips a name that is no longer in it, which is the same skip-and-name / all-bad-raises policy as every other database-backed tool. The delimiter comes from `sequence_db_separator(path)` (the extension decides; pandas handles `.gz` itself), and both the header read and the EC-column scan are cached on `(path, mtime, size)`, because `populate_ec_options` has no `prevent_initial_call` and defaults to every database selected — it runs in the web process on every page load. This contract applies to `data/sequences/` only: `reactions/`, `sequence_embeddings/`, and `foldseek_db/` are unchanged. `sequence_embeddings/` is the deliberate contrast — a pickle has no header-only read, so `get_sequence_embedding_database_options()` lists names without checking columns and Func-E's `_load_databases` skips and names a malformed one at run time instead. Note the directory is named for its data, not its reader: it holds protein embedding tables, and Func-E is only the first tool to want them.

**Database naming — one spelling everywhere.** A database is named on screen **exactly as it is named in `data/`, extension included**: `Funce_pairs.pkl` shows as `Funce_pairs.pkl`, the FoldSeek folder `AFDB_SWISSPROT` as `AFDB_SWISSPROT` (a directory, so it has no extension to show). The canonical statement of the rule is the module docstring of [`utils/data_loading.py`](../enzyme_tk_app/app/utils/data_loading.py). Do not prettify and do not strip the suffix — no database name is put through `.replace("_", " ").title()` or `.stem` anywhere in `enzyme_tk_app/`, and adding either back is a regression (`results_helpers._pretty_label` title-cases *parameter keys*, i.e. the row label, never the database name in its value). The rule covers the dropdown `label`, the `COL_DATABASE` value, the **Databases Skipped** card and the all-failed error message, and the Input Parameters row (`build_result_input_params` stringifies the list as-is, so it reads `['protein.csv', 'Funce_pairs.pkl']` — brackets and quotes like every other multi-select param, with the filenames verbatim inside them). Option `label` and `value` are therefore identical; the `value` has to keep its extension because that is the string `validate_db_names` matches against the option list and what becomes a file path, which is why the suffix is never stripped for display either.

> **One deliberate exception:** the FoldSeek results grid. Its `database` column comes from the `enzymetk` library, not from this app — `FoldSeekDatabase` is a `str, Enum` whose values must match the names foldseek itself uses, and `AFDB_SWISSPROT = "Alphafold/Swiss-Prot"`. So that one folder reads `Alphafold/Swiss-Prot` in that one grid column, while `PDB` / `CUSTOM` / `CUSTOM2` read as their folder names. The tool's dropdown label, stat cards, and Input Parameters row all follow the rule above. Do not "fix" this by rewriting library output.


## 4. Results Page — `results.py`

The results page is what users see when they click "View Results" on a completed job. The framework provides a lot of UI for free — your `results_layout()` function only handles the tool-specific visualisation.

> **Why results before compute?** Understanding what the framework auto-renders tells you which special keys your `compute.py` should return (e.g., `_stat_cards`, `dataframe`). Read this section first, then write your `run()` function to supply those keys.

### 4.1 What the framework gives you for free

These are rendered automatically by `my_tasks_view_results.py` — you do NOT build these in your `results.py`:

| Component | Source | What it shows |
|-----------|--------|---------------|
| **Job info header** | `_build_job_info_header()` | Tool name, status badge, submitted/completed timestamps, duration, expiry |
| **Stat cards** | `_build_job_info_header()` | The framework always renders **Duration** and **Expires In** cards first, then appends any tool-defined `_stat_cards` items from your compute return dict. |
| **Input parameters table** | `build_result_input_params()` | Auto-rendered from `job.params`, one row per key **in insertion order** — so the `params` dict in your submit callback must list keys in the same order the fields appear in your `modal.py`. SMILES values get inline structure previews — and that preview image is also what the results grid's compare lightbox shows as the **query** panel (§4.2); list values (`databases`, `algorithms`, the filters) keep their repr, e.g. `['protein.csv', 'Funce_pairs.pkl']`. Use `_params_exclude` to hide internal keys. |
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
| `build_ag_grid(column_defs, df_payload)` | Standardized AG Grid with pagination (20 rows/page), Balham theme, tooltips, copy/paste, and column filtering — **plus the shared CSV-export toolbar above it**. Returns an `html.Div` wrapping both, not a bare `dag.AgGrid`. |
| `build_stat_card(value, label)` | One stat card in the shared `jobs-stat-card` style. You rarely call it — the results-page header renders your `_stat_cards` for you, merging them into its own strip alongside Duration and Expires In. |
| `build_result_input_params(job)` | Auto-renders submitted parameters. Called by the framework, not by your code. |

#### AG Grid column rules

| Column type | `autoHeight` | `filter` | `sortable` | Notes |
|-------------|-------------|----------|------------|-------|
| Short text / number | — | `True` or `agNumberColumnFilter` | `True` | Default — fastest rendering |
| SVG / image | `True` | `False` | `False` | Row expands to fit image. Set `cellRenderer: "SvgRenderer"` and `cellRendererParams: {"smilesField": <the row's SMILES column>}` (captions the image in the compare lightbox below); fill the column in `compute.py` with `generate_cached_svg_uris(df[smiles_col], reaction_to_svg_data_uri, height=200)` from `utils/smiles_rendering.py`, which renders each unique SMILES once. Keep the `height=200` — the lightbox's stacking threshold is calibrated to that canvas (below) |
| Long text (wrap) | `True` | `True` | `True` | Add `cellClass: "cell-wrap-dash-ag-grid"` |

**Performance note:** Only enable `autoHeight` on columns that truly need it. Fixed-height rows render significantly faster.

**CSV export comes with the grid.** `build_ag_grid()` renders a "Download CSV" button and a Filtered/Unfiltered scope selector above the table, so **do not add a per-tool download button** — Filtered exports the rows left by the column filters in the current sort order, Unfiltered exports every row, and the file is named `enzymetk-<job_id[:6]>-<scope>.csv` (the same 6-char task prefix the My Tasks table shows). Two consequences for your column defs: any column with `cellRenderer: "SvgRenderer"` is left **out** of the CSV (each cell is a ~20 KB base64 data URI), so keep the source SMILES in a text column if the image must be reproducible from the download; and only one results grid may exist per page, because the grid and toolbar use static IDs (see the `create-ag-grid` agent for the two-grid upgrade path).

**Clicking an image compares it against the query.** `SvgRenderer` opens a full-screen lightbox holding the job's query structure and the clicked row's, each labelled and captioned with its SMILES — side by side for a compact structure, stacked query-over-result for a wide one (see below) — the backdrop, the `×` and Escape close it, a click inside the panels does not (SMILES stay selectable). Only one thing is yours to wire: `cellRendererParams: {"smilesField": ...}` on the SVG column, naming the row column that holds *that* structure's SMILES; `props.data` is the whole row, so it need not be a visible column, and omitting it costs only the caption. The **query** panel needs no wiring at all — `_openSvgOverlay` reads it out of the page, looking up `img.jobs-params-preview` (the preview `build_result_input_params()` already renders for any `smiles` param, §4.1) and taking its SMILES from `data-smiles`. Those two anchors are `QUERY_PREVIEW_CLASS` / `QUERY_SMILES_ATTR` in `results_helpers.py`; rename either and `assets/dashAgGridComponentFunctions.js` must change in the same edit — `test_query_preview_anchors_match_the_compare_lightbox` pins both sides. Two caveats: draw your result images on the **same canvas as the query preview** (`_render_smiles_preview()` uses `width=500, height=300` for a molecule and `height=200` for a reaction, matching what the two tools pass to `generate_cached_svg_uris`) or the panels sit at different stroke weights — and, since orientation is measured off the images themselves, in a layout chosen by whichever of the two is wider; and a tool with no query image — no `smiles` param, or RDKit could not draw it — simply falls back to the single-image overlay.

**Wide structures stack instead of sitting side by side.** Orientation is read off the image, not the viewport: `_stackWideImages()` adds `.svg-compare-stacked` to the wrapper as soon as one panel's `naturalWidth / naturalHeight` clears `_STACK_ASPECT_RATIO = 2.5`, putting QUERY above RESULT and widening each from ~46vw to ~88vw — at 1400x900 a reaction goes from 644 px wide to 1232 px, while `substrate_product_similarity`'s molecules stay side by side at 532 px. The two canvases the app draws fall either side of that number: a molecule is 500x300 (**1.67**), a reaction is `max(400, n_templates * 250)` x 200, so even the narrowest real one — one reactant, one product, 750x200 — is **3.75** (a 2x2 reaction, 1250x200, is 6.25). **The threshold therefore depends on the 200 px reaction height both call sites pass:** draw reactions taller and a 1→1 reaction drops below 2.5 and silently stops stacking. `test_stack_threshold_separates_reactions_from_molecules` in `test_smiles_rendering.py` re-renders both canvases and asserts `molecule < threshold < reaction` against the constant it reads out of the JS source, so if you change a canvas size, re-measure and move the constant in the same edit. Narrow viewports remain CSS's job — the `@media (max-width: 768px)` block in `09-ag-grid.css` stacks everything below tablet, because the JS never adds the class for a 1.67 molecule.

**Write every column out in full:** `_get_column_defs()` is the one place a reader can see what the table contains, so every column gets its own visible line with its field name spelled out literally — never a loop, comprehension, or f-string that builds `field` from another list. `build_ag_grid()` renders only fields that have a def, so a generated name both hides the column at the call site and silently drops any column the generating list fails to name (no error, no log). Share *rules* freely — `numeric_col_def`, `sequence_col_def`, `shared_col_defs()`, and `col.COL_*` from `utils/columns.py` for anything cross-tool (`col.COL_ENTRY`, `col.COL_DATABASE`, `col.COL_SEQUENCE`) — but spell out *identity*. A bare literal is right only when the name is one library's output contract, as Func-E's `enzymetk`-named `Funce_*` columns are.

**Then append the remainder when the payload's columns are not knowable.** `_get_column_defs()` is the *styled* layer — widths, decimals, the sequence truncation class — not necessarily the full column list. Where the data can carry columns this app never enumerates, `results_layout()` adds a bare def for each one the curated list does not name:

```python
defs = _get_column_defs()
known = {d["field"] for d in defs}
defs += [{"field": c, "headerName": c} for c in df_payload["columns"] if c not in known]
```

Nothing is synthesised here — the names are read from the payload — so an unexpected column shows up unstyled instead of vanishing. Two tools need it, and both do it identically: `tools/funce/results.py` (a newer `enzymetk` may emit new `Funce_*` columns) and `tools/sequence_similarity/results.py` (a sequence database only has to carry `Entry`, `Sequence` and `EC number`; a real `enzymes.tsv` search brings 17 more — `Organism`, `Protein names`, `Catalytic activity`, `Cofactor`, …). Curated defs lead, the appended tail comes last; if you extend the curated list, leave the append in place.

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
│  │  AUTO · export toolbar from build_ag_grid()       │  │
│  │  [ Download CSV ]   (•) Filtered                  │  │
│  │                     ( ) Unfiltered                │  │
│  │                                                   │  │
│  │  Example: AG Grid (or any custom visualisation)   │  │
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


## 5. Compute — `compute.py`

This module exports `run(params: dict) -> dict`. It runs on the Celery worker — not in the web process. The `params` dict contains the form fields submitted by the callback.

### 5.1 Return dict conventions

Your `run()` function returns a plain dict. The framework recognises several special keys that drive the auto-rendered UI described in the Results section above:

| Key | Type | Required | Purpose |
|-----|------|----------|---------|
| `_stat_cards` | `list[dict]` | No | Summary cards rendered in the results header. Each item: `{"label": "...", "value": "..."}`. The framework already provides **Duration** and **Expires In** cards automatically — do not duplicate them here. |
| `_params_exclude` | `list[str]` | No | Parameter keys to hide from the auto-rendered input table. The results section automatically puts all input params in the results page. |
| `dataframe` | `dict` | No | Tabular results: `{"columns": [...], "data": [{...}, ...]}` for AG Grid display |

**Do NOT echo input parameters** in the return dict. The framework stores `params` separately and auto-renders them via `build_result_input_params()`.

**The return value must be JSON-serialisable — all of it.** The worker `json.dumps` the whole dict and writes it to `JOB_OUTPUTS_PATH/<job_id>/` on the shared Docker volume, keeping only a pointer in Redis (`_store_result` in [`backend/tasks.py`](../enzyme_tk_app/app/backend/tasks.py)), so size is not a concern — a large `dataframe` is fine. Type is: that dump passes no `default=`, so a numpy scalar or an ndarray in a cell raises at persist time and the finished job is recorded as **FAILURE** with nothing to show for the compute that already succeeded. Convert or drop such columns before returning — this is why `funce/compute.py` strips its embedding columns (`DROPPED_COLS`).

**Your tool's own invariants go in this module's docstring.** `AGENTS.md` and the `create-tool` agent carry the contracts that bind *every* tool; a rule about how *your* algorithm turns a user's input into numbers belongs beside the code that does it, where nobody editing that code can miss it — and a rule about a tool that is later retired does not linger in a shared file reading as a live constraint on new ones. [`funce/compute.py`](../enzyme_tk_app/app/tools/funce/compute.py) is the worked example: its docstring records why every selected database must be scored in one call, why the app never downloads a checkpoint, and how a dot-joined reaction side is reduced. Pin whatever a reader could get wrong with a test in `test_tools_<name>.py`.

### 5.2 Example — Reaction Similarity compute

See [reaction_similarity/compute.py](../enzyme_tk_app/app/tools/reaction_similarity/compute.py) for the full implementation.


## Tests

One file per tool, named for the tool: `enzyme_tk_app/app/tests/test_tools_<name>.py`. Five of the six use the folder name verbatim (`test_tools_sequence_similarity.py`); `timer_tool_template/` shortens to `test_tools_timer.py`. Route the work through the **`write-tests`** agent — its workflow runs `verify` and then `review-tests` for you.

### What to pin

| Target | What the test asserts |
|--------|----------------------|
| Column defs | The exact field list `_get_column_defs()` produces, written out as a literal `EXPECTED_FIELDS`. This list is the contract between your grid and your compute output — a diff here should be readable by a reviewer |
| Compute — databases | One unreadable selection is skipped and named in the **Databases Skipped** card; *every* selection unreadable raises. Both halves matter (§3.4) |
| Compute — stat cards | The labels and values in `_stat_cards`, since the results header renders them verbatim |
| Compute — serialisability | That the returned dict survives `json.dumps` (§5.1). A tool that returns a numpy type passes every other test and then fails the job at persist time |
| Callbacks | Each branch of the validation callback, that `toggle_` opens on launch and closes on cancel, that submit clears stale results on reopen, and that submit returns the validator's message rather than raising. For `populate_example_*`, unpack the tuple (Task Name last) and pin the `no_update` branch — a value that is not a shipped example fills the input but leaves the Task Name alone. That every example prefills a name is checked for all tools at once by `test_every_example_prefills_a_task_name` in `test_tools.py`, so don't repeat it per tool |
| Modal | That `modal()` returns a `dbc.Modal` carrying the expected id |

### Shared helpers in `conftest.py`

| Helper | Use |
|--------|-----|
| `make_job(params=…, result=…, **overrides)` | Builds a `JobInfo` so you can call `results_layout(job)` directly. Override `status=JobStatus.FAILURE` and the like |
| `find_components(tree, html.Img)` | Walks a Dash component tree and returns every node of a type — how you assert on rendered layouts |
| `get_text(component)` | Concatenates the text content of a tree, for asserting on messages |
| `offered_databases(*names)` | Builds the dropdown option list `validate_db_names()` expects, so a callback test doesn't need real files |
| `make_reaction_df(reactions)` | A minimal DataFrame with the `id` / `unmapped` columns |
| `reactions_dir`, `sequences_dir`, `sequence_csv` | Fixtures that copy the 20-row test CSVs into `tmp_path` |
| `csv_molecules`, `csv_molecules_known_scores` | Substrate/product SMILES parsed out of the 20-row reaction CSV — the second carries hardcoded expected scores for regression tests |
| `fake_redis`, `task_scheduler_celery_service`, `write_job_into_fake_redis` | Backend tests against `fakeredis` — no real Redis, no Celery, no network |

### Two rules that are easy to get wrong

**Never read `data/` from a test.** The real databases and checkpoints are gitignored, so a test that reads them passes only on a machine that happens to have them and fails in CI. Write the fixture files your test needs into `tmp_path` and monkeypatch the path constant at it. Patch it **where it was imported**, not in `paths.py` — the importing module bound its own name at import time:

```python
monkeypatch.setattr("enzyme_tk_app.app.tools.funce.compute.SEQUENCE_EMBEDDINGS_DIR", db_dir)
monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.SEQUENCES_DIR", patched_dir)
```

Every existing compute test does this.

**Keep `compute.py` cheap to import.** Heavy dependencies (`torch`, `enzymetk`, foldseek) are imported *inside* `run()`, not at module scope, so a test file can import `compute` for its helpers and constants without pulling in a gigabyte of libraries. Tests that do exercise `run()` install stand-in modules in `sys.modules` for the duration of one test.

## Run and Verify

1. **`tox run -e format`** — formats, sorts imports, and removes unused ones (F401). If an import exists for its side effect, mark it `# noqa: F401` with a reason. It also formats Python blocks inside `.md` files, so keep every snippet in `AGENTS.md` or `.claude/agents/` a valid statement — `docs/` is excluded from ruff, so snippets in *this* file are neither formatted nor linted.
2. **`tox`** — the default envlist: `check-style`, `check-security`, `format`, `test`, `test-docker-dependent`, `build-docs`, `build-dist`. The Docker-dependent env fails harmlessly when no daemon is running. Both commands together are the **`verify`** agent, which every code-generating change ends with.
3. **`verify-ui`** — if the change is visible in a browser (`pages/`, `components/`, `tools/*/modal.py`, `tools/*/results.py`, `assets/*.css`, `assets/*.js`), also run this skill against the running app. `verify` proves the code is clean; only `verify-ui` proves the button works. Never hand the manual check back to the user.
4. **`sync-docs`** — the last step. It audits `AGENTS.md`, `README.md`, and the agent sources against what you changed.

The app runs in Docker — see [README → Quickstart](../README.md#quickstart).

```bash
docker compose up --build
```

**A new dependency is not just a badge.** The `libraries` field in `TOOL_DEF` renders monospace badges on the tool card and installs nothing; list what actually runs in the worker at query time, not what produced the bundled data offline (Func-E lists `torch`, `rxnfp`, `unimol` — its reaction encoder runs those three — but not the ESM3 that embedded the protein database). A new Python package goes in `requirements/prd.txt`; system packages and binaries go through the **`edit-dockerfile`** agent, which covers the `linux/amd64` + `linux/arm64` rules. The one exception is a package needing per-package pip flags, which a requirements file cannot express — `rxnfp` is installed in the `Dockerfile` with `--no-deps` because its metadata hard-pins 2020 releases. Pin it there just as tightly, and note it in the requirements file that would otherwise have held it.

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