# Modal Creation Agent

**Trigger:** When modifying, designing, or generating new frontend tool modals (e.g., `modal.py`).

When creating a new tool modal (e.g., in `enzyme_tk_app/app/tools/<tool_name>/modal.py`), follow this standardized layout structure to ensure a consistent, clean, and functional aesthetic across the entire application workspace.

## 1. Module Docstring Convention
Every `modal.py` must start with a detailed docstring that includes:
- A one-line summary of what the modal is for.
- A **Layout rules** section listing the six structural rules (see the timer_tool_template for the canonical example).
- A **Key conventions** section listing ID conventions, shared helpers, and control class requirements.

Example:
```python
"""Modal layout for the <Tool Name> tool — description.

This modal appears when the user clicks the Launch button on the <Tool Name>
tool card. It collects <brief description of inputs>.

Layout rules  (see ``.github/agents/create-modal.md``)
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
    className="bg-light p-3 rounded mb-3", # Use mb-4 for the first section
    children=[ ... ]
)
```

## 5. Section Headers
Use the shared factory functions from `enzyme_tk_app.app.components.modal_helpers` — **never** inline the `html.H6` boilerplate:

```python
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
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

## 7. Required vs Default Sections
- **Section 1: Input Data:** Place *Task Name*, required identifiers (like SMILES or file uploads), and Demo Examples here.
- **Section 2: Tool Configurations:** Place optional tuning parameters, Algorithm selections, external Database selections, and Limits (Top-N) here in a single vertical tracking stack (avoid multi-column grids unless absolutely constrained for space).

## 8. Footer
Use `create_modal_footer(TOOL_DEF["slug"])` to generate the standard `dbc.ModalFooter` with Close (secondary outline) and Run (primary) buttons.

## 9. Results Placeholder
After the last section `html.Div` inside `dbc.ModalBody`, add:
```python
create_modal_submission_results(TOOL_DEF["slug"])
```
This empty div is populated by the submit callback with a job-ID confirmation or validation error.

## 10. Canonical Reference
The **canonical example** is `enzyme_tk_app/app/tools/timer_tool_template/modal.py`. When in doubt, mirror its structure, docstring, and commenting style exactly.
