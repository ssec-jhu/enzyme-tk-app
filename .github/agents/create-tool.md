# Create Tool Agent

**Trigger:** When asked to "create a new tool", "add a new algorithm", or "generate a tool scaffold".

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

## 3. UI & Modal Delegation
> [!IMPORTANT]
> If the task involves creating or modifying a `modal.py` file, you **MUST** trigger the [**Modal Creation Agent**](create-modal.md) and follow its strict layout and styling rules.

### Modal dropdowns, inputs, and form controls
- All dropdowns must use `dcc.Dropdown` (from `dash`), never `dbc.Select`.
- For all form controls (Dropdowns, Inputs, Textareas, Checkboxes, RadioItems), always add the CSS class `themed-control`.

## 4. Backend & Callbacks
- Use `get_task_scheduler()` from `enzyme_tk_app.app.backend` to obtain the singleton scheduler.
- `compute.py` must export `def run(params: dict) -> dict`.
- **Do NOT echo input parameters back in the return dict.** The system stores `params` separately from `result` at submission time. The shared `build_result_input_params(job)` helper auto-renders all `job.params` on the results page. Only return keys that are **computed outputs** or **display metadata**:
  - `_stat_cards` — summary stat cards for the results header.
  - `_params_exclude` — list of param keys to hide from the auto-rendered input parameters table.
  - `dataframe` — tabular results (`{"columns": [...], "data": [...]}`).
  - Any tool-specific computed values that `results.py` explicitly reads from `job.result`.
- For callback implementation patterns (guard clauses, decorator syntax, naming), follow the [Write-Callback Agent](write-callback.md) and examine existing tools.

## 5. Reference Material
Refer to the `timer_tool_template` folder for **folder structure and module layout** (`__init__.py`, slug naming, file roles). For callback implementation patterns, follow the [Write-Callback Agent](write-callback.md) and examine existing tools like `substrate_product_similarity`.
