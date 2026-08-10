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
- **`max_duration` (optional, seconds) is a *soft* limit**: it becomes Celery's `soft_time_limit`, so an overrun is recorded as `TIMEOUT` rather than `FAILURE`, and the hard SIGKILL lands `HARD_TIMEOUT_GRACE_SECONDS` (60 s) later so the handler can write that status. Both defaults live in `backend/celery_app.py`; set the field whenever the tool's real runtime is far from the 3600 s default in either direction (the timer template uses 600, Func-E 1800).

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
- Return a list of **human-readable labels** (one per item) when data is absent — these render as tooltip lines under a "Missing data" badge on the tool card.
- **A file that is present but unusable is reported here too**, with the reason. `sequence_similarity/check_data.py` lists every `data/sequences/` file that fails the column contract (§3b.9) — `"badfile.csv — missing columns: Sequence, EC number"` — because such a file is filtered out of the dropdown, so this card is the only place the scientist who dropped it in learns why it vanished.
- Auto-discovery in `tools/__init__.py` registers the callable into the `CHECK_DATA` dict keyed by `TOOL_DEF["slug"]`. Tools **without** this module are treated as having no data dependencies and never show a badge.
- Resolve data locations via the `Path` constants in `enzyme_tk_app.app.paths` — never hardcode paths. Add a constant there only for a directory that is shared, large, or plausibly reusable by a future tool; a path only your tool reads stays in your tool module and derives from `paths.DATA_DIR` itself (see the `paths.py` module docstring).
- Keep checks cheap and side-effect-free: `check_data()` runs at home-page render time, on every render. Existence/non-empty checks are free; a check that must open a file reads only the header (`nrows=0`) and is cached on `(path, mtime, size)` so a re-dropped database is still picked up without an app restart — that is what `scan_sequence_databases()` does. Never read a full column here. The `data_warning_badge` helper catches exceptions defensively, but a buggy check still degrades to a generic "Data check failed" badge — so keep it robust.

## 3. UI & Modal Conventions
> [!IMPORTANT]
> You cannot spawn other subagents — consult the convention files below by **reading them** (you have the `Read` tool) and applying their rules inline. Ignore each file's trailing "run verify" / after-* workflow step; run `verify` once at the end via this agent's own MANDATORY AFTER-CREATION WORKFLOW.
>
> - Creating or modifying a `modal.py` file? You **MUST** read `.claude/agents/create-modal.md` and apply its layout/styling rules (§1–10 — module docstring, section headers, `themed-control` inputs, footer, results placeholder).
> - Creating or modifying CSS in `enzyme_tk_app/app/assets/` (e.g. a tool-specific badge or status style)? You **MUST** read `.claude/agents/write-css.md` and apply its banner/section-comment and 4-space-indent conventions.

### Modal dropdowns, inputs, and form controls
- All dropdowns must use `dcc.Dropdown` (from `dash`), never `dbc.Select`.
- For all form controls **in a modal** (Dropdowns, Inputs, Textareas, Checkboxes, RadioItems), always add the CSS class `themed-control`. It is a modal-form class only — controls elsewhere use their own component class (e.g. the results-grid export scope radios use `jobs-toolbar-radios`), so do not retrofit `themed-control` onto them.

## 3b. Database-Backed Tools — Mandatory Contract
Applies to every tool that reads reference databases out of a data directory (`sequences/`,
`reactions/`, `sequence_embeddings/`, `foldseek_db/`, …). All existing database-backed tools
follow it; a new tool that diverges is a bug, not a style choice.

**Name the directory and its option builder for the data, not for your tool.** More than one
tool can read a kind of reference data, so `data/sequence_embeddings/` +
`get_sequence_embedding_database_options()` — never `funce_db/` + `get_funce_database_options()`,
which is what that pair used to be called. Model weights follow the same rule and are named for
the model: `unimol_weights/` holds the UniMol checkpoint Func-E's reaction encoder loads, not
`funce_unimol/`. A tool's name belongs on a directory only when the
tool genuinely owns it: `foldseek_db/` and `foldseek_models/` (the folder names are foldseek's
own database identifiers) and `funce_models/` (Func-E's EC-level checkpoints).

1. **The dropdown is multi-select.** `dcc.Dropdown(..., multi=True)`, id
   `f"id-dropdown-{TOOL_DEF['slug']}-databases"` (**plural**), with **every option
   pre-selected** — the broadest search is the default. There is no single-database tool;
   a directory that happens to hold one file still gets a multi-select. Its label column is
   `create_modal_databases_label(TOOL_DEF["slug"], contents)` from
   `components/modal_helpers.py` — the "Databases" label plus an info icon whose tooltip
   (`contents`) is one sentence on what this tool's databases hold, i.e. their columns or
   payload, never selection mechanics (`create-modal` §7).
2. **Validate with the shared validator, never a hand-rolled regex.** Pass the tool's own
   option list — the second argument is what the name is checked *against*:
   ```python
   from enzyme_tk_app.app.utils.data_loading import get_sequence_database_options, validate_db_names

   # get_reaction_database_options / get_sequence_embedding_database_options /
   # get_foldseek_database_options for the other tools.
   error = validate_db_names(databases, get_sequence_database_options())
   if error:
       return error
   ```
   The check is **membership in `options`** (only each dict's `value` is read), so the
   allowlist is exactly what the dropdown just offered: nothing to traverse, no second
   extension to smuggle, and a database the builder filtered out — a non-compliant
   sequence file, say (§3b.9) — is rejected for free. It returns a message for an empty
   selection, a bare string instead of a list (a single-select leftover), or any name the
   tool does not currently offer (`Unknown database: 'x'`) — same contract as
   `validate_top_n`, it never raises. The value is a browser-controlled `State`, so raising
   would surface as an HTTP 500 on `/_dash-update-component` (the app installs no Dash
   `on_error` handler).
   Names come from the browser and become filesystem paths — this is the trust boundary.
2b. **A SMILES field gets the same treatment, from `utils/smiles_validation.py`.**
   `validate_reaction_smiles(smiles)` for a reaction, `validate_smiles(smiles)` for a single
   molecule — same message-or-`None` contract, so it sits next to the two calls above and
   reads identically:
   ```python
   from enzyme_tk_app.app.utils.smiles_validation import validate_reaction_smiles

   error = validate_reaction_smiles(smiles)
   if error:
       return error
   ```
   Unlike a database name, a structure is checked in **three** places, and all three matter:
   the `validate_*` form callback (gates the Run button and marks the field — `create-modal`
   §6, `write-callback` §4), the submit callback above, and the top of `run()` (a replayed job
   never touches the modal). Never write a per-tool SMILES check: the validators are
   deliberately stricter than the parsers downstream, because `enzymetk`'s `ReactionDist`
   reads the query as SMARTS and would otherwise score `">>"` against every row and call it a
   success. Since the validator handles its own empty case, the `PreventUpdate` guard above
   must **not** also test the SMILES — that would swallow its message.
3. **`params["databases"]` is a `list[str]`.** Never a `"database"` string key.
4. **Merge, do not loop-and-append per database.** Load each selection, tag its rows with
   the `database` column (`COL_DATABASE` from `utils.columns`, value `csv_path.name` —
   see §3c, full filename, no prettifying), and `pd.concat` into one reference set so the ranking/top-N is
   global across the union, not per file.
5. **Bad database → skip, name it, continue. All bad → raise.** A single unusable file —
   missing, unreadable, or (for `data/sequences/`) no longer meeting the column contract in
   item 9 — must not fail the job; collect its name. But if *nothing* loaded,
   `raise ValueError(...)` — an empty grid would be indistinguishable from a legitimate
   "no hits found".
6. **Say so in the stat cards:** a `Databases Searched` **count**, plus a
   `Databases Skipped` card listing the failures only when there are any (append the
   sanitised `safe_name`, i.e. `Path(name).name` — the full filename, not the raw selection —
   §3c). Never a single `Database` card holding a filename.
7. **Show the origin in the results grid:** `{"field": col.COL_DATABASE, "headerName":
   "Database", "width": 140}`. The *column* is the contract; its label is not. Func-E
   (`tools/funce/results.py`) uses `col.COL_DATABASE` like every other tool — only its
   **header** differs: it sets every `headerName` to its own `field`, so the origin column
   is labelled `database`. A user-requested labelling exception, not a bug to fix.
8. **Dependent dropdowns take the union.** Anything derived from the selection (EC-number
   filter, cofactor filter) is rebuilt as the union across the selected files and clears its
   own value when the selection changes, so a stale filter is never carried over.
9. **`data/sequences/` files declare their columns; a file that does not is not a database.**
   A file there qualifies only when **both** hold: its extension is in
   `SEQUENCE_DB_SUFFIXES` (`.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`) **and** its header carries
   every one of `REQUIRED_SEQUENCE_COLUMNS` (`Entry`, `Sequence`, `EC number`). Everything
   else in the file is **metadata the app never enumerates** — it rides through the search
   into the results grid untouched (which is why that grid appends a def for whatever it was
   not told about; see `create-ag-grid` §2.6). `scan_sequence_databases()` in
   `utils/data_loading.py` is the single scan: `get_sequence_database_options()` takes its
   names, `check_data()` takes its `problems` lines
   (`"badfile.csv — missing columns: Sequence, EC number"`). A non-compliant file is
   therefore **not offered at all** and is named on the home-page card instead — silently
   omitting it would leave the scientist who dropped it in with no explanation. `compute.run()`
   re-derives the usable set itself (the worker reads `params` from Redis, so it trusts no
   submit-time check) and skips a name that is no longer in it, which is the same
   skip-and-name / all-bad-raises policy as items 5 and 6. Use
   `sequence_db_separator(path)` for the delimiter — the extension decides, and pandas
   handles `.gz` itself. **This contract is `data/sequences/` only**; `reactions/`,
   `sequence_embeddings/`, and `foldseek_db/` are unchanged. A pickle cannot be read
   header-only, so `sequence_embeddings/` deliberately validates at run time
   (item 5) rather than at discovery — checking there would deserialise every
   embedding table on every page render.

## 3c. Database Naming — One Spelling Everywhere
**A database is named on screen exactly as it is named in `data/`, extension included.**
`Funce_pairs.pkl` shows as `Funce_pairs.pkl`; the FoldSeek folder `AFDB_SWISSPROT` shows as
`AFDB_SWISSPROT` (a directory, so it has no extension to show). The canonical statement of
this rule is the module docstring of `enzyme_tk_app/app/utils/data_loading.py` — read it
before touching any of this.

- **Do not prettify and do not strip the suffix.** No `.replace("_", " ").title()`, no casing
  fixes, no abbreviation expansion, no `.stem`. A scientist must be able to match what the app
  shows against what is on disk. No database name is put through either transform anywhere in
  `enzyme_tk_app/`; adding one back is a regression. (`results_helpers._pretty_label` does
  title-case *parameter keys* — that is the row label, never the database name in its value.)
- **Where the rule applies:** the dropdown option `label` (`f.name` in the three file-based
  `get_*_database_options()` builders, `entry.name` in the FoldSeek one), the `COL_DATABASE`
  column value (`csv_path.name` / `db_path.name`), every name appended to `databases_skipped`
  (`safe_name`) and therefore the **Databases Skipped** card and the "None of the selected
  databases could be read" message, and the Input Parameters row (`build_result_input_params`
  stringifies the list as-is, so it reads `['protein.csv', 'Funce_pairs.pkl']` — brackets and
  quotes like every other multi-select param, filenames verbatim inside them).
- **`label` and `value` are identical** in the file-based builders (`{"label": f.name,
  "value": f.name}`), and in FoldSeek's too (`{"label": name, "value": name}`) — there is no
  label-vs-value distinction to reason about. The `value` has to keep its extension because it
  is the string `validate_db_names` matches against the option list and what becomes a file
  path; that is the reason the suffix is never stripped anywhere.
- **One deliberate exception — the FoldSeek results grid.** In
  `tools/sequence_structure_similarity`, the `database` column of the results grid is
  produced by the `enzymetk` library, not by this app. `FoldSeekDatabase` is a `str, Enum`
  whose values must match the names foldseek itself uses, and
  `AFDB_SWISSPROT = "Alphafold/Swiss-Prot"`. So that one folder reads `Alphafold/Swiss-Prot`
  in that one grid column, while `PDB` / `CUSTOM` / `CUSTOM2` read as their folder names. Its
  dropdown label, stat cards, and Input Parameters row all follow the rule above. **Do not
  "fix" this by rewriting library output** — the enum value is foldseek's contract.

## 4. Backend & Callbacks
- Use `get_task_scheduler()` from `enzyme_tk_app.app.backend` to obtain the singleton scheduler.
- `compute.py` must export `def run(params: dict) -> dict`.
- **The whole return dict must be JSON-serialisable.** `tasks._store_result` calls `json.dumps` on it with no `default=` before offloading it to the shared volume, so one numpy scalar or ndarray left in a `dataframe` column raises *after* the compute succeeded and the job is recorded as FAILURE. Convert or drop those columns before returning (see `funce/compute.py`'s `DROPPED_COLS`) and pin it with a `json.dumps(result)` assertion in the tool's test.
- **The `params` dict literal is the Input Parameters row order** — `build_result_input_params`
  renders `job.params` in insertion order, so list the keys in the same order the fields appear
  in `modal.py`. A key added out of order shows up out of order on the results page.
- **Do NOT echo input parameters back in the return dict.** The system stores `params` separately from `result` at submission time. The shared `build_result_input_params(job)` helper auto-renders all `job.params` on the results page. Only return keys that are **computed outputs** or **display metadata**:
  - `_stat_cards` — summary stat cards for the results header.
  - `_params_exclude` — list of param keys to hide from the auto-rendered input parameters table.
  - `dataframe` — tabular results (`{"columns": [...], "data": [...]}`).
  - Any tool-specific computed values that `results.py` explicitly reads from `job.result`.
- **An example picker prefills the Task Name.** Every example dict carries a `task_name` beside its
  `label`/`value` — in `modal.py`'s `_get_example_*()` helper, or in `__init__.py` when `compute.py`
  shares the same constants (`funce`'s `EXAMPLE_REACTIONS`) — and the tool's `populate_example_*`
  callback returns it **verbatim** as its **last** output, into
  `f"id-input-{TOOL_DEF['slug']}-task-name"`. Task Name is the one field that blocks submit, so an
  example that leaves it blank is not runnable in one click. Never prepend the tool slug — the My
  Tasks table already shows the tool in the column beside Task Name. Full contract in
  `create-modal` §7; `test_every_example_prefills_a_task_name` in `tests/test_tools.py` enforces a
  non-blank name for every tool.
- For callback implementation patterns (guard clauses, decorator syntax, naming), read and follow `.claude/agents/write-callback.md`, and examine existing tools.

## 5. Reference Material
Refer to the `timer_tool_template` folder for the **whole shape of a tool**, not just its skeleton: `__init__.py` and slug naming, file roles, a modal with the Task Name row and an example picker, all four callbacks (`toggle_` / `populate_example_` / `validate_` / `submit_`), and an AG Grid `results.py` — over a `compute.py` that only sleeps. It follows every shared convention, so mirror it and substitute your algorithm rather than treating it as a reduced special case. For callback implementation patterns, read and follow `.claude/agents/write-callback.md`; for a tool that also reads bundled databases, examine `substrate_product_similarity`.

---

## MANDATORY AFTER-CREATION WORKFLOW

After creating or modifying tool files, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
