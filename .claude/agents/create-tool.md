---
name: create-tool
description: Use PROACTIVELY when asked to "create a new tool", "add a new algorithm", or "generate a tool scaffold" in the EnzymeTK app.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Create Tool Agent

This agent follows the architectural guidelines for tool discovery, single-source slug invariants, and module structure in the EnzymeTK project.

## 1. Tool Structure
Tools live in self-contained sub-packages under `enzyme_tk_app/app/tools/`. Auto-discovery in `tools/__init__.py` scans sub-packages at import time — no central file to edit.

To add a tool, create a folder with:

| File | Required? | Must export | Purpose |
|------|-----------|-------------|---------|
| `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
| `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
| `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
| `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
| `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |
| `check_data.py` | No | `check_data() → list[str]` | Reports missing bundled data; non-empty list renders a "Missing data" badge on the tool card (see §2b) |

- `TOOL_DEF` requires an `order: int` field that controls the card's position in the grid.
- Import icon constants from `enzyme_tk_app.app.components.icons` and the `ToolDef` type from `enzyme_tk_app.app.tools`.

## 2. Invariants & Slug Management
### Single-source slug & title — the rename-once invariant
- **`TOOL_DEF` in `__init__.py` is the single source of truth** for a tool's slug, title, and icon.
- In `modal.py` and `callbacks.py`, import `TOOL_DEF` from the tool's own package:
  ```python
  from enzyme_tk_app.app.tools.<tool_folder> import TOOL_DEF
  ```
- **Build all slug-dependent component IDs** with f-strings from `TOOL_DEF["slug"]`:
  - Modal ID: `f"id-modal-{TOOL_DEF['slug']}"`
  - Launch button match: `f"id-btn-launch-{TOOL_DEF['slug']}"`
  - Sub-component IDs: `f"id-btn-{TOOL_DEF['slug']}-submit"`, etc.

### Folder-name invariant
- The folder name **must** equal `slug.replace("-", "_")`. If you change the slug, rename the folder to match.

## 2b. Missing-Data Badge — `check_data.py`
If a tool depends on bundled data (model weights, prebuilt databases, reference files), add an **optional** `check_data.py` exporting `check_data() -> list[str]`:
- Return an **empty list** when all data prerequisites are satisfied.
- Return a list of **human-readable labels** (one per missing item) when data is absent — these render as tooltip lines under a "Missing data" badge on the tool card.
- Auto-discovery in `tools/__init__.py` registers the callable into the `CHECK_DATA` dict keyed by `TOOL_DEF["slug"]`. Tools **without** this module are treated as having no data dependencies and never show a badge.
- Resolve data locations via the `Path` constants in `enzyme_tk_app.app.paths` — never hardcode paths. Add a new constant there if a needed path is missing.
- Keep checks cheap and side-effect-free (existence/non-empty checks): `check_data()` runs at home-page render time. The `data_warning_badge` helper catches exceptions defensively, but a buggy check still degrades to a generic "Data check failed" badge — so keep it robust.

## 3. UI & Modal Conventions
> [!IMPORTANT]
> You cannot spawn other subagents — consult the convention files below by **reading them** (you have the `Read` tool) and applying their rules inline. Ignore each file's trailing "run verify" / after-* workflow step; run `verify` once at the end via this agent's own MANDATORY AFTER-CREATION WORKFLOW.
>
> - Creating or modifying a `modal.py` file? You **MUST** read `.claude/agents/create-modal.md` and apply its layout/styling rules (§1–10 — module docstring, section headers, `themed-control` inputs, footer, results placeholder).
> - Creating or modifying CSS in `enzyme_tk_app/app/assets/` (e.g. a tool-specific badge or status style)? You **MUST** read `.claude/agents/write-css.md` and apply its banner/section-comment and 4-space-indent conventions.

### Modal dropdowns, inputs, and form controls
- All dropdowns must use `dcc.Dropdown` (from `dash`), never `dbc.Select`.
- For all form controls (Dropdowns, Inputs, Textareas, Checkboxes, RadioItems), always add the CSS class `themed-control`.

## 3b. Database-Backed Tools — Mandatory Contract
Applies to every tool that reads reference databases out of a data directory (`sequences/`,
`reactions/`, `foldseek_db/`, `funce_db/`, …). All existing database-backed tools follow it;
a new tool that diverges is a bug, not a style choice.

1. **The dropdown is multi-select.** `dcc.Dropdown(..., multi=True)`, id
   `f"id-dropdown-{TOOL_DEF['slug']}-databases"` (**plural**), with **every option
   pre-selected** — the broadest search is the default. There is no single-database tool;
   a directory that happens to hold one file still gets a multi-select.
2. **Validate with the shared validator, never a hand-rolled regex.** In the submit
   callback:
   ```python
   from enzyme_tk_app.app.utils.data_loading import validate_db_names

   error = validate_db_names(databases, ".csv")   # ".pkl", or None for FoldSeek dirs
   if error:
       return error
   ```
   It returns a message for an empty selection or any name that is not a bare
   `[0-9A-Za-z_-]+` plus the optional suffix — same contract as `validate_top_n`. It
   *raises* `TypeError` on a bare string (a single-select leftover), because that is a
   programming error rather than bad user input.
   Names come from the browser and become filesystem paths — this is the trust boundary.
3. **`params["databases"]` is a `list[str]`.** Never a `"database"` string key.
4. **Merge, do not loop-and-append per database.** Load each selection, tag its rows with
   the `database` column (`COL_DATABASE` from `utils.columns`, value
   `csv_path.stem.replace("_", " ").title()`), and `pd.concat` into one reference set so
   the ranking/top-N is global across the union, not per file.
5. **Bad database → skip, name it, continue. All bad → raise.** A single unreadable file
   must not fail the job; collect its name. But if *nothing* loaded, `raise ValueError(...)`
   — an empty grid would be indistinguishable from a legitimate "no hits found".
6. **Say so in the stat cards:** a `Databases Searched` **count**, plus a
   `Databases Skipped` card listing the failures only when there are any. Never a single
   `Database` card holding a filename.
7. **Show the origin in the results grid:** `{"field": col.COL_DATABASE, "headerName":
   "Database", "width": 140}`. The *column* is the contract; its label is not. Func-E
   (`tools/funce/results.py`) uses `col.COL_DATABASE` like every other tool — only its
   **header** differs: it sets every `headerName` to its own `field`, so the origin column
   is labelled `database`. A user-requested labelling exception, not a bug to fix.
8. **Dependent dropdowns take the union.** Anything derived from the selection (EC-number
   filter, cofactor filter) is rebuilt as the union across the selected files and clears its
   own value when the selection changes, so a stale filter is never carried over.

## 4. Backend & Callbacks
- Use `get_task_scheduler()` from `enzyme_tk_app.app.backend` to obtain the singleton scheduler.
- `compute.py` must export `def run(params: dict) -> dict`.
- **Do NOT echo input parameters back in the return dict.** The system stores `params` separately from `result` at submission time. The shared `build_result_input_params(job)` helper auto-renders all `job.params` on the results page. Only return keys that are **computed outputs** or **display metadata**:
  - `_stat_cards` — summary stat cards for the results header.
  - `_params_exclude` — list of param keys to hide from the auto-rendered input parameters table.
  - `dataframe` — tabular results (`{"columns": [...], "data": [...]}`).
  - Any tool-specific computed values that `results.py` explicitly reads from `job.result`.
- For callback implementation patterns (guard clauses, decorator syntax, naming), read and follow `.claude/agents/write-callback.md`, and examine existing tools.

## 5. Reference Material
Refer to the `timer_tool_template` folder for **folder structure and module layout** (`__init__.py`, slug naming, file roles). For callback implementation patterns, read and follow `.claude/agents/write-callback.md`, and examine existing tools like `substrate_product_similarity`.

---

## MANDATORY AFTER-CREATION WORKFLOW

After creating or modifying tool files, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
