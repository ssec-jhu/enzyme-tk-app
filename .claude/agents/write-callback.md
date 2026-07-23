---
name: write-callback
description: Use PROACTIVELY when writing, creating, or modifying Dash @callback functions in the EnzymeTK app.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Write-Callback Agent

This agent defines the mandatory patterns for all Dash callback code in the EnzymeTK project.

### 1. Decorator Syntax

- Pass `Output`, `Input`, and `State` as **positional arguments** to `@callback()`.
- **Never** wrap them in `[...]` lists — that is a legacy Dash v1 pattern.

```python
# ✅ Correct — positional args
@callback(
    Output("id-div-results", "children"),
    Input("id-btn-submit", "n_clicks"),
    Input("id-btn-launch", "n_clicks"),
    State("id-input-name", "value"),
    State("id-input-query", "value"),
    prevent_initial_call=True,
)

# ❌ Wrong — list-wrapped
@callback(
    Output("id-div-results", "children"),
    [Input("id-btn-submit", "n_clicks"), Input("id-btn-launch", "n_clicks")],
    [State("id-input-name", "value"), State("id-input-query", "value")],
    prevent_initial_call=True,
)
```

### 2. Guard Clauses — `raise PreventUpdate`

- Import: `from dash.exceptions import PreventUpdate`
- In callbacks with early-exit guard clauses (no click, falsy input, no triggered ID), use `raise PreventUpdate` instead of returning an empty string or `None`. This tells Dash to skip the update entirely, avoiding unnecessary DOM writes.

```python
from dash.exceptions import PreventUpdate

def populate_example(example_value):
    if not example_value:
        raise PreventUpdate         # ← no user action, skip update
    return example_value
```

### 3. Intentional DOM Writes Are Not Guard Clauses

Not every `return ""` is a guard clause. Some returns **intentionally** write a value to the DOM — those must stay as explicit returns. Common example: clearing stale results when a modal reopens.

```python
def submit_job(submit_clicks, launch_clicks, ...):
    # Intentional clear — actively empties the results div so the user
    # does not see a stale job ID from a previous submission.
    if ctx.triggered_id == f"id-btn-launch-{TOOL_DEF['slug']}":
        return ""                   # ← intentional DOM write, NOT a guard

    # ... rest of submission logic
```

**Rule of thumb:** if removing the return would leave stale/incorrect content visible to the user, it is an intentional write — keep `return ""`. If nothing meaningful happened (no click, missing input), `raise PreventUpdate`.

### 4. Naming & Placement

- Callback function names start with a **verb** describing the action: `toggle_*`, `submit_*`, `validate_*`, `populate_*`, `sync_*`.
- Keep callbacks close to the component they modify — define them in the same file as the component that owns the `Output`.
- Always add `prevent_initial_call=True` on callbacks that should not fire at page load.

### 5. Exemplars

- **`PreventUpdate` usage:** See `enzyme_tk_app/app/pages/my_tasks.py` — uses `raise PreventUpdate` consistently in all action callback guard clauses.
- **Positional-arg decorator style:** See `enzyme_tk_app/app/tools/substrate_product_similarity/callbacks.py` — all `@callback` decorators use positional args, never list syntax.

---

## MANDATORY AFTER-CALLBACK WORKFLOW

After creating or modifying callback code, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
