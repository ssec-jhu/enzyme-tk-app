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
from dash import no_update
from dash.exceptions import PreventUpdate

# Module scope: example dropdown value -> task name.
_TASK_NAMES_BY_VALUE = {ex["value"]: ex["task_name"] for ex in _get_example_reactions()}


def populate_example_reaction(example_value):
    if not example_value:
        raise PreventUpdate  # ← no user action, skip every output

    # Every populate_example_* prefills the Task Name as its LAST output
    # (create-modal §7) — it is the one field that blocks submit.  The name
    # goes in verbatim; never prepend the tool slug.
    task_name = _TASK_NAMES_BY_VALUE.get(example_value)
    return example_value, task_name or no_update
```

**`PreventUpdate` is all-or-nothing; `no_update` is per-output.** Nothing meaningful happened →
`raise PreventUpdate` and every output is skipped. Something did happen but one output must be
left exactly as the user left it → return `no_update` *in that position* (never `None`, which
would blank the field). Above, a value that is not one of the shipped examples still fills the
textarea and only spares the Task Name; `sequence_structure_similarity`'s version does the same
for the structure-upload outputs on a sequence-only example.

**`no_update` is not the default for "this branch has nothing to say" — it means "leave what the
user left".** Where the callback is the field's author for this branch, an absent value is an
explicit *clear*, not a skip. `sequence_similarity.populate_example_sequence` splits exactly there:
a shipped example returns `ex.get("ec", [])` — `[]`, so picking a second example positively clears
the first one's filter — while a sequence the user pasted is not an example at all and returns
`no_update` for the filters and the Task Name, leaving their own settings alone. Getting this
backwards is silent: the run is filtered by a leftover the user never chose and the modal shows no
sign of it (`create-modal` §7).

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

**The `validate_*` callback checks presence, and carries no `prevent_initial_call`** — it
must fire at page load so the Run button starts *disabled* on an empty form. Validity is the
browser's job for anything it can express: `dbc.Input(type="number", min=1, max=300)` makes the
browser mark an out-of-range entry invalid and **Dash then passes `None` to the callback**, so
typing `0` or `500` disables the button through the plain presence check and never reaches the
submit callback's range message at all. Test presence with `value is not None` rather than
`bool(value)` — a bare `0` is present, just out of range — and leave the range message where it
is: it is the server-side backstop below, not UI feedback.

**A SMILES field is the exception: the browser cannot express "is this a molecule", so
`validate_*` runs the real validator and marks the field.** The callback gains two outputs
beside `disabled` — the textarea's `invalid` and the `dbc.FormFeedback`'s `children` — and a
present-but-unparseable structure disables Run *and* turns the field red with the reason
underneath. A **blank** field still only disables Run: an empty form is not yet a mistake, so it
must not be marked. All three SMILES tools share the shape:

```python
@callback(
    Output(f"id-btn-{TOOL_DEF['slug']}-submit", "disabled"),
    Output(f"id-textarea-{TOOL_DEF['slug']}-smiles", "invalid"),
    Output(f"id-feedback-{TOOL_DEF['slug']}-smiles", "children"),
    ...,
)
def validate_reaction_form(task_name, smiles, selected_databases, selected_algorithms):
    smiles_error = validate_reaction_smiles(smiles)
    # A blank field is not a mistake yet — it disables Run without turning red.
    show_error = bool(smiles and smiles.strip() and smiles_error)
    disabled = not (task_name and task_name.strip() and not smiles_error and selected_databases)
    return disabled, show_error, smiles_error if show_error else ""
```

**The textarea must carry `debounce=300`** (`create-modal` §6) — a *number* of milliseconds, so the
value is sent once the user stops typing. Validating on every keystroke puts several round-trips in
flight at once and the field ends up showing whichever verdict landed last: reproducibly, an
earlier keystroke's, so a corrected structure stays marked invalid until something else fires the
callback. `debounce=True` is not the fix — it defers to blur and can leave Run disabled under a
click that arrives first. `test_every_smiles_field_debounces` in `tests/test_tools.py` pins it.

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

**Two production guards close every submit callback, in this order**, after every field
validator and immediately before `get_task_scheduler()`:

```python
error = validate_captcha(captcha_payload, g.session_id)
if error:
    return error

error = validate_active_job_limit(g.session_id)
if error:
    return error
```

Both come last because a malformed submit should show *its own* field error rather than a
capacity message — or a "tick the box" message — that tells the user nothing about the typo
they made. Both return a message or `None` like every validator above them, and both are
no-ops unless the deployment set `APP_IN_PRODUCTION_MODE`.

The **captcha goes first of the two**: it costs no Redis round trip, so an unverified caller
never gets the cap's O(N) session-set read for free. Its payload arrives as the **last**
`State` and therefore the **last** parameter, and it needs an Args line in the docstring like
any other:

```python
@callback(
    Output(f"id-div-{TOOL_DEF['slug']}-results", "children"),
    Input(f"id-btn-{TOOL_DEF['slug']}-submit", "n_clicks"),
    State(f"id-input-{TOOL_DEF['slug']}-task-name", "value"),
    # Last State, last parameter: the solved proof of work. The Store is rendered
    # for every tool by create_modal_footer() — you never declare it yourself.
    State(f"id-store-{TOOL_DEF['slug']}-captcha", "data"),
    prevent_initial_call=True,
)
def submit_my_tool_job(submit_clicks, task_name, captcha_payload): ...
```

The proof is signed over the session id, so it cannot be retargeted at another session — which
is what makes discarding the session cookie cost a solve instead of nothing, and why the cap
below it is worth more than it used to be. `test_every_tool_enforces_the_active_job_limit` and
`test_every_tool_verifies_the_captcha` fail any tool whose `callbacks.py` omits either import,
and `test_every_modal_carries_a_captcha_store` fails a modal missing the Store; the behavioural
tests in `test_tools_timer.py` are what catch a guard placed *after* `submit_job` or in the
wrong order, which an import walk cannot see.

**Both outcomes are shared blocks — never return a bare message.** `id-div-<slug>-results` is
a plain slot with no styling of its own, so a string returned into it renders with no box, no
colour and no icon. Wrap every validator's message, and build the success row from the helper:

```python
    error = validate_top_n(top_n)
    if error:
        return build_submission_error(error)

    ...

    n_dbs = len(databases) if databases else 0
    detail = f"{n_dbs} database(s) · top {top_n}"
    return build_submission_success(job_id, detail)
```

Every validator here returns a message or `None` and is wrapped the same way — the pattern is
`if error: return build_submission_error(error)`, not `return error`. The clear-on-reopen
branch is the one exception and stays `return ""` (§3 — an intentional DOM write): an empty
slot renders nothing at all. `test_submit_success_links_to_my_tasks` and
`test_submit_error_returns_the_shared_error_row` in `test_tools_timer.py` pin both shapes,
which the `test_every_tool_links_to_my_tasks_on_success` import walk cannot see.

**Database names are the canonical case.** They come from the browser and become filesystem
paths, so they go through the one shared validator — never a per-tool regex. The second
argument is the tool's **own option list**, the same builder the modal calls:

```python
from enzyme_tk_app.app.utils.data_loading import get_sequence_database_options, validate_db_names

# Database names become file paths on the backend.  Checked against what the
# dropdown currently offers — get_reaction_database_options /
# get_sequence_embedding_database_options / get_foldseek_database_options
# for the others.
error = validate_db_names(databases, get_sequence_database_options())
if error:
    return error
```

Membership in that list is the whole check (only each option's `value` is read), which is
why nothing else is needed: an exact allowlist has no traversal to match and no second
extension to smuggle, and a name the builder filtered out — a `data/sequences/` file that
fails the column contract, say — is rejected as `Unknown database: 'x'` for free. Build the
options fresh in the callback rather than caching them at import time, so a database added
or removed on disk is reflected immediately.

It returns a message rather than raising, exactly like `validate_top_n` — so the two
validations read identically and sit next to each other. That includes a bare string instead
of a list (a `multi=False` leftover): the value is a browser-controlled `State`, so raising
would surface as an HTTP 500 on `/_dash-update-component` rather than as a message in the
modal, since the app installs no Dash `on_error` handler.

`validate_db_names` already reports an empty selection, so do not also test `not databases`
in the `PreventUpdate` guard above — that would swallow the message the user should see. This
applies to every message-returning validator that handles its own empty case: all three SMILES
tools call `validate_reaction_smiles(smiles)` / `validate_smiles(smiles)` the same way, so their
`PreventUpdate` guards test only the task name (and algorithms/role) and deliberately leave the
SMILES alone.

**A structure is validated in three places, and all three are load-bearing.** The form callback
gates the Run button, the submit callback repeats the check because the client gate is
bypassable, and `run()` repeats it again because a replayed job never touches the modal. They
share one definition of "valid" — `utils/smiles_validation.py` — so they cannot drift.

Importing that module into `callbacks.py` at module scope is safe **only** because it imports
rdkit inside its functions; a module-level heavy import there would load rdkit into the web
process on every boot. The same discipline is what lets `utils/smiles_rendering.py` be imported
anywhere. (Do not put a shared validator in a tool's `compute.py` — `validate_reaction_smiles`
lived in `funce/compute.py` until Reaction Similarity needed it too.)

### 5. Two Callbacks Writing One Property — `allow_duplicate`

Dash rejects two callbacks with the same `Output` unless the later ones declare
`Output(..., "value", allow_duplicate=True)` (and carry `prevent_initial_call=True`). The flag
silences the error; it does **not** order the writers. Add it only when you can show the two
writers cannot race:

- **They must sit in disjoint dependency graphs.** In `sequence_similarity`, `populate_ec_options`
  and `populate_cofactor_options` own the two filter `value` properties, and
  `populate_example_sequence` writes them as a second, independent writer. Safe because nothing
  takes a filter's `value` as an `Input` and **no callback anywhere writes the Databases dropdown**,
  so picking an example cannot re-trigger the option builders.
- **Adding an `Output` can break a graph that was disjoint.** Giving that same example callback an
  `Output` on the Databases dropdown would put the option builders downstream of it: they would fire
  and clear the filter the example had just set. Reordering the `Output(...)` lines does not help —
  the second callback runs after the first has returned. Change the *graph*, not the order.
- **Prefer one owner.** `allow_duplicate` is the exception, not a way to spread writes for one
  property across callbacks. `pages/admin.py` and `pages/my_tasks.py` are the other legitimate uses:
  several distinct user actions feed one result/refresh sink, and only one can fire per interaction.

### 6. Naming & Placement

- Callback function names start with a **verb** describing the action. Every tool modal uses the same four: `toggle_*`, `populate_example_*`, `validate_*`, `submit_*`.
- Keep callbacks close to the component they modify — define them in the same file as the component that owns the `Output`.
- Always add `prevent_initial_call=True` on callbacks that should not fire at page load. `validate_*` is the standing exception (§4) — it must fire at load to disable the Run button.

### 7. Exemplars

- **All four callbacks in one short file:** See `enzyme_tk_app/app/tools/timer_tool_template/callbacks.py` — the canonical `toggle_` / `populate_example_` / `validate_` / `submit_` set, heavily commented and with no tool-specific logic in the way.
- **`PreventUpdate` usage:** See `enzyme_tk_app/app/pages/my_tasks.py` — uses `raise PreventUpdate` consistently in all action callback guard clauses.
- **Positional-arg decorator style:** See `enzyme_tk_app/app/tools/substrate_product_similarity/callbacks.py` — all `@callback` decorators use positional args, never list syntax.
- **Server-side guard + `validate_db_names`:** See `enzyme_tk_app/app/tools/substrate_product_similarity/callbacks.py` and `enzyme_tk_app/app/tools/sequence_similarity/callbacks.py`.
- **Example picker with more outputs than the input + Task Name:** See `enzyme_tk_app/app/tools/sequence_similarity/callbacks.py` — four outputs, two of them `allow_duplicate` filter dropdowns (§5), Task Name last, and the `[]`-clears / `no_update`-leaves split of §2. `sequence_structure_similarity/callbacks.py` is the simpler form: extra outputs, no duplicate owner.

---

## MANDATORY AFTER-CALLBACK WORKFLOW

After creating or modifying callback code, you **MUST** execute the **`verify`
subagent's** core steps (`tox run -e format` then `tox`). Fix any failures
before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
