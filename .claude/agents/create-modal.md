---
name: create-modal
description: Use PROACTIVELY when modifying, designing, generating, or restyling a frontend tool modal (e.g. modal.py) in the EnzymeTK app.
tools: Read, Write, Edit, Grep, Glob, Bash
---

# Modal Creation Agent

When creating a new tool modal (e.g., in `enzyme_tk_app/app/tools/<tool_name>/modal.py`), follow this standardized layout structure to ensure a consistent, clean, and functional aesthetic across the entire application workspace.

## 1. Module Docstring Convention
Every `modal.py` must start with a detailed docstring that includes:
- A one-line summary of what the modal is for.
- A **Layout rules** section listing the six structural rules — copy the example below verbatim.
- A **Key conventions** section listing ID conventions, shared helpers, and control class requirements.

Example:
```python
"""Modal layout for the <Tool Name> tool — description.

This modal appears when the user clicks the Launch button on the <Tool Name>
tool card. It collects <brief description of inputs>.

Layout rules  (see the create-modal subagent)
------------------------------------------------------
1. Top-level: ``dbc.Modal(size="lg", centered=True)``.
2. ``dbc.ModalBody`` gets ``className="p-4"``.
3. Each logical section is wrapped in
   ``html.Div(className="bg-light p-3 rounded mb-3")``.
4. Shared helpers from ``modal_helpers`` handle all repeated
   boilerplate — header, section headers, footer, and results
   placeholder.
5. Inputs use ``dbc.Row`` / ``dbc.Col`` for label ↔ control alignment.
6. All interactive controls get ``className="... themed-control"`` for
   dark-mode-aware styling.

Key conventions
---------------
- All component IDs are f-strings of ``TOOL_DEF["slug"]`` — never
  hardcode the slug string.
- The modal ID **must** be ``f"id-modal-{TOOL_DEF['slug']}"``.
- Use shared helpers for modal structure:
  - ``create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"])``
  - ``create_modal_input_section_header()``
  - ``create_modal_config_section_header()``
  - ``create_modal_databases_label(TOOL_DEF["slug"], contents)``
  - ``create_modal_submission_results(TOOL_DEF["slug"])``
  - ``create_modal_footer(TOOL_DEF["slug"])``
- Use ``dcc.Dropdown`` (not ``dbc.Select``) for dropdowns.
- Use ``themed-control`` on every form control (Input, Dropdown,
  RadioItems, Checkbox, Textarea).
"""
```

## 2. Inline Comment Convention
All modals must include structured block-separator comments to clearly delineate each section of the modal. These comments serve as landmarks for developers and AI agents navigating the code.

### Required comment blocks (in order):
```python
return dbc.Modal(
    # Modal ID follows the convention: id-modal-<slug>
    id=f"id-modal-{TOOL_DEF['slug']}",
    ...
    children=[
        # ------------------------------------------------
        # MODAL Header: MUST ADD using the shared helper for consistent styling.
        # ------------------------------------------------
        create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),
        # ------------------------------------------------
        # MODAL BODY
        # ------------------------------------------------
        dbc.ModalBody(
            className="p-4",
            children=[
                # ------------------------------------------------
                # Section 1: Input Data
                # ------------------------------------------------
                html.Div(
                    className="bg-light p-3 rounded mb-3",
                    children=[
                        # INPUT DATA HEADER:
                        # MUST ADD the section header using the shared helper
                        create_modal_input_section_header(),
                        # MODAL INPUTS GO HERE — describe what this tool collects.
                        # The ID pattern for inputs is:
                        # id-<component-type>-<slug>-<name>
                        # where <component-type> is input, dropdown, radio, check, etc.
                        # and <name> is a descriptive name for the input's purpose.
                        ...
                    ],
                ),
                # ------------------------------------------------
                # Section 2: Tool Configuration
                # ------------------------------------------------
                html.Div(
                    className="bg-light p-3 rounded mb-2",
                    children=[
                        # CONFIGURATION HEADER:
                        # MUST ADD the section header using the shared helper
                        create_modal_config_section_header(),
                        # MODAL CONFIGURATION INPUTS GO HERE
                        # Describe the config options for this tool.
                        ...
                    ],
                ),
                # ------------------------------------------------
                # Section 3: MUST ADD Status / job ID placeholder
                # ------------------------------------------------
                # This div is populated by the submit callback with
                # a job-ID confirmation message or a validation error.
                create_modal_submission_results(TOOL_DEF["slug"]),
            ],
        ),
        # ------------------------------------------------
        # Footer:  Cancel (outline) + Submit (primary) — standard for all modals.
        # ------------------------------------------------
        create_modal_footer(TOOL_DEF["slug"]),
    ],
)
```

### Additional inline comment guidelines:
- Add a brief descriptive comment above each `dbc.Row` input (e.g., `# Task Name`, `# SMILES Input — textarea with example picker dropdown`).
- When a control uses `themed-control`, add `# themed-control is required for dark-mode styling` on the first occurrence in the modal as a reminder.
- Use `# ------------------------------------------------` separator lines (48 dashes) consistently — never use shorter or longer dash lines.

## 3. Top-Level Container
Use a standard `dbc.Modal` component with `size="lg"` and `centered=True`.
Inside `dbc.ModalBody`, attach `className="p-4"`.
Use `create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"])` for the header — never inline the `dbc.ModalHeader` / `dbc.ModalTitle` boilerplate.

## 4. Section Strategy
Separate modal contents into distinct thematic sections using `html.Div` containers instead of nested cards. This avoids "card-in-a-card" boundary fatigue.

Each section wrapper should use:
```python
html.Div(
    className="bg-light p-3 rounded mb-3",  # Use mb-4 for the first section
    children=[...],
)
```

## 5. Section Headers
Use the shared factory functions from `enzyme_tk_app.app.components.modal_helpers` — **never** inline the `html.H6` boilerplate:

```python
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_databases_label,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
```

- **Section 1 header:** `create_modal_input_section_header()` — renders "Input Data" with a flask icon.
- **Section 2 header:** `create_modal_config_section_header()` — renders "Tool Configurations" with a gear icon.

## 6. Input Fields Convention
- **Labeling:** Always use `dbc.Label(..., className="col-form-label fw-bold")` inside a `dbc.Col(width=3)`.
- **Controls:** Attach the `themed-control` class to all interactable input components (e.g. `dbc.Input`, `dcc.Dropdown`, `dbc.RadioItems`). This ensures they hook correctly into the custom CSS themes or Dash 4.0 Checkbox UI structures.
- **Row layout:** Use `dbc.Row([dbc.Col(label, width=3), dbc.Col(control, width=9)], className="mb-2", align="center")` for label ↔ control alignment.
- **New CSS:** Prefer existing `className`/Bootstrap utilities and the shared theme classes. If a modal genuinely needs a new rule in `enzyme_tk_app/app/assets/`, follow the `write-css` subagent for banner/section-comment style and 4-space indentation.
- **A SMILES `dbc.Textarea` gets `debounce=300`** — a *number* of milliseconds, never `True`. Validating on every keystroke puts several callback round-trips in flight at once and the field ends up showing whichever verdict landed last, so a corrected structure stays marked invalid; `True` would defer to blur and strand Run disabled under a click. See `write-callback` §4.
- **A SMILES field carries a `dbc.FormFeedback` directly after its `dbc.Textarea`**, inside the same `dbc.Col`:

  ```python
  (dbc.FormFeedback(id=f"id-feedback-{TOOL_DEF['slug']}-smiles", type="invalid"),)
  ```

  **The position is load-bearing, not cosmetic.** Bootstrap reveals the message with `.is-invalid ~ .invalid-feedback`, a *following-sibling* selector, so a feedback placed before the textarea — or nested one level deeper, e.g. inside the "Try an example" `html.Div` — silently never shows. The `validate_*` callback writes its `children` and flips the textarea's `invalid` (see `write-callback` §4); `07-modals.css` restates the red border because `.modal-body .themed-control` ties Bootstrap's `.form-control.is-invalid` on specificity and wins on source order.

## 7. Required vs Default Sections
- **Section 1: Input Data:** *Task Name* is the **first row**, then the required identifiers (SMILES, sequence, file upload, a plain number — whatever the tool takes) with their Demo Examples nested under the input each one fills. Every tool has the Task Name row and every tool has it first; it is required — `validate_*` keeps the Run button disabled until it has a value (see `write-callback` §4) — and it is what labels the job in the My Tasks table and on the results page.
- **Demo Examples prefill the Task Name too:** every example dict carries a `task_name` next to its `label`/`value`, and the tool's `populate_example_*` callback returns it **verbatim** as its **last** output, into `f"id-input-{TOOL_DEF['slug']}-task-name"`. Task Name is the one field that blocks submit, so an example that leaves it blank is not runnable in one click. **Never prepend the tool slug** — the My Tasks table already has a Tool column right beside Task Name, so a prefix only repeats the neighbouring cell and, since the Task Name column has no `max-width` and the table no `table-layout: fixed`, a long name widens it and squeezes the other eight. Keep the `task_name` short and kebab-case, identifiers in their own casing (`DEHP-MEHP`, `A0A009IHW8`, `1AKI-lysozyme-structure`); it shares that column with names the user types. A selection overwrites a name the user already typed, exactly as it overwrites every other field. `test_every_example_prefills_a_task_name` in `tests/test_tools.py` walks the live dropdowns and enforces a non-blank name for every tool.
- **An example may prefill more than the input and the Task Name.** Give the example dict an optional key per extra field (Sequence Similarity's `ec` and `cofactors`, both `list[str]`, beside its `label`/`task_name`/`value`) and add one `Output` per field to `populate_example_*` — **Task Name stays last** however many there are, because `test_every_example_prefills_a_task_name` reads `populate(...)[-1]`. Four things decide whether this works:
  - **The value must be one the target control actually offers.** A `dcc.Dropdown` renders **nothing** for a value with no matching option, so a typo or a stale identifier reads as a filter that silently did not apply — indistinguishable from an unfiltered search. Options scanned off the data files (the EC and cofactor filters) mean the check is against the *data*, and the offered set is the **union** over whatever is currently selected: check each value against a database the Databases dropdown pre-selects — it pre-selects them all — and name that file in the `_get_example_*()` docstring so the next editor can re-check it. A user who deselects that database before picking the example gets the same silent no-op, which is the price of prefilling a dropdown someone else populates; keep the value in the database a default run searches so the default path is always correct.
  - **Pick a value that selects a family, not a single row.** A filter whose hits are one entry — the query itself — demonstrates nothing: the results page shows a self-match and the example looks broken. Sequence Similarity's `J9VWW9` was chosen because its EC and cofactor intersect at 189 rows; a cytochrome c peroxidase whose `1.11.1.-` ∩ `heme c` is 1 was rejected for exactly this.
  - **A field another callback already writes needs `allow_duplicate=True`** on the example's `Output` — the option builders (`populate_ec_options`, `populate_cofactor_options`) own those `value` properties, and the example is a second, independent writer. That is safe **only while the two sit in disjoint dependency graphs**: nothing takes a filter's `value` as an `Input`, and no callback anywhere writes the Databases dropdown. **Never give an example an `Output` on the Databases dropdown** — the option builders are downstream of `databases.value`, so setting it would re-fire them and clear the filter the example just set, and no reordering of `Output(...)` lines fixes that. Prefill a database selection only by making it the default in `modal()`.
  - **An example that declares no value for a field clears it (`[]`), it does not skip it (`no_update`).** Picking a second example must not carry the first one's filter into a search the user reads as unfiltered. `no_update` is for the *other* branch — a value the user pasted that is not a shipped example fills the input and leaves their own filters and task name alone (`write-callback` §2). Once an example carries more than a name, key the module-scope lookup on the whole dict (`_EXAMPLES_BY_VALUE = {ex["value"]: ex for ex in _get_example_sequences()}`) rather than on `task_name` alone.
- **Section 2: Tool Configurations:** Place optional tuning parameters, Algorithm selections, external Database selections, and Limits (Top-N) here in a single vertical tracking stack (avoid multi-column grids unless absolutely constrained for space).
- **Database selection is always multi-select:** build the label column with `create_modal_databases_label(TOOL_DEF["slug"], "<one sentence naming what the databases hold>")` — it supplies the "Databases" label, the info icon and its tooltip, so never hand-inline `dbc.Col(dbc.Label("Databases", ...), width=3)`. The sentence describes the *contents* (columns or payload, e.g. "Entry, Sequence and EC number columns, plus any metadata the file carries."), never selection mechanics. Give the dropdown `multi=True` with the id `f"id-dropdown-{TOOL_DEF['slug']}-databases"` (plural), and pre-select **every** option (`value=[opt["value"] for opt in db_options]`) — the broadest search is the default. Even a directory holding one file gets a multi-select. Build the options with the matching `get_*_database_options()` helper and never re-label them — an option's `label` and `value` are both the exact name on disk (the full filename, extension included, or the folder name for FoldSeek). See `.claude/agents/create-tool.md` §3b for the rest of the contract (validation, merging, skipped-database stat cards) and §3c for the naming rule.

## 8. Footer
Use `create_modal_footer(TOOL_DEF["slug"])` to generate the standard `dbc.ModalFooter` with Close (secondary outline) and Run (primary) buttons.

It also emits the **submission captcha** pair, and you must not hand-roll or reorder either:

- `html.Div(id=f"id-div-{slug}-captcha", className=CAPTCHA_HOLDER_CLASS)` — an empty holder, rendered **only in production mode**. `assets/12-altcha-bridge.js` finds it by that class and mounts the `<altcha-widget>` custom element into it (Dash cannot emit an arbitrary tag, and `dbc.Modal` unmounts its children into a portal, which is why a MutationObserver does the mounting rather than a clientside callback). It is a **JS mount target**, the third exception to "only give a component an id if a callback uses it". `.etk-captcha` in `07-modals.css` parks it at the left end of the footer row and maps ALTCHA's CSS custom properties onto the app's design tokens — a new footer layout must keep `margin-right: auto` working.
- `dcc.Store(id=f"id-store-{slug}-captcha")` — rendered **always, including locally**. A `State` pointing at a component that is not in the layout stops the submit callback from firing at all, which would dead-button Run for every local checkout.

Renaming the class, either id, or the challenge path means editing `assets/12-altcha-bridge.js` in the same change — it mirrors all three as constants. The submit callback reads that Store as its last `State` (`create-tool` §4, `write-callback` §4).

## 9. Results Placeholder
After the last section `html.Div` inside `dbc.ModalBody`, add:
```python
create_modal_submission_results(TOOL_DEF["slug"])
```
This empty div is populated by the submit callback with a job-ID confirmation or validation error.

## 10. Canonical Reference
The **canonical example** is `enzyme_tk_app/app/tools/timer_tool_template/modal.py`, and it is a real one — it follows every rule above with nothing tool-specific in the way: the §1 docstring in full, Task Name as the first row of Section 1, the example picker (`dcc.Dropdown` with id `f"id-dropdown-{TOOL_DEF['slug']}-example"`, `searchable=False`, under the `ICON_MODAL_EXAMPLE` + "Try an example:" `html.Small`) nested beneath the input it fills, both section headers, the results placeholder and the shared footer. When in doubt, mirror its structure, docstring, and commenting style exactly.

The single thing it cannot demonstrate is `create_modal_databases_label()` — it has no databases. Take that row from §7 and `create-tool` §3b.

---

## MANDATORY AFTER-CREATION WORKFLOW

After creating or modifying modal files, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
