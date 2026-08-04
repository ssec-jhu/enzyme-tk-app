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
        raise PreventUpdate  # ← no user action, skip update
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

### 4. Submit Callbacks Re-Validate Everything Server-Side

The client-side `validate_*` callback only disables the submit button — a crafted request
still reaches the submit callback with whatever payload it likes. **Every** `submit_*`
callback therefore repeats the check itself, immediately after the "clear on reopen" branch
and before any `.strip()` / indexing / path building:

```python
# Server-side validation — the client disables the submit button when
# fields are empty, but a crafted request could bypass that.
if not task_name or not task_name.strip() or not smiles or not smiles.strip() or not algorithms:
    raise PreventUpdate
```

Missing/empty required field → `raise PreventUpdate` (nothing meaningful happened).
A value that is present but *invalid* → `return` the error message string, so the user sees
it in the modal's submission-results div.

**Database names are the canonical case.** They come from the browser and become filesystem
paths, so they go through the one shared validator — never a per-tool regex:

```python
from enzyme_tk_app.app.utils.data_loading import validate_db_names

# Database names become file paths on the backend.
error = validate_db_names(databases, ".csv")  # ".pkl", or None for FoldSeek dirs
if error:
    return error
```

It returns a message rather than raising, exactly like `validate_top_n` — so the two
validations read identically and sit next to each other. That includes a bare string instead
of a list (a `multi=False` leftover): the value is a browser-controlled `State`, so raising
would surface as an HTTP 500 on `/_dash-update-component` rather than as a message in the
modal, since the app installs no Dash `on_error` handler.

`validate_db_names` already reports an empty selection, so do not also test `not databases`
in the `PreventUpdate` guard above — that would swallow the message the user should see.

### 5. Naming & Placement

- Callback function names start with a **verb** describing the action: `toggle_*`, `submit_*`, `validate_*`, `populate_*`, `sync_*`.
- Keep callbacks close to the component they modify — define them in the same file as the component that owns the `Output`.
- Always add `prevent_initial_call=True` on callbacks that should not fire at page load.

### 6. Exemplars

- **`PreventUpdate` usage:** See `enzyme_tk_app/app/pages/my_tasks.py` — uses `raise PreventUpdate` consistently in all action callback guard clauses.
- **Positional-arg decorator style:** See `enzyme_tk_app/app/tools/substrate_product_similarity/callbacks.py` — all `@callback` decorators use positional args, never list syntax.
- **Server-side guard + `validate_db_names`:** See `enzyme_tk_app/app/tools/substrate_product_similarity/callbacks.py` and `enzyme_tk_app/app/tools/sequence_similarity/callbacks.py`.

---

## MANDATORY AFTER-CALLBACK WORKFLOW

After creating or modifying callback code, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
