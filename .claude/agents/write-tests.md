---
name: write-tests
description: Use PROACTIVELY when asked to "write tests," "create a test," or "add test coverage" for a module or feature in the EnzymeTK app.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Write-Tests Agent

The agent must follow these strictly defined patterns for writing tests in the EnzymeTK project.

### Guidelines

1.  **Location & Discovery**
    - Tests live in `enzyme_tk_app/app/tests/` and use **pytest**. The one exception is `scripts/db_build/` (`conftest.py`, `test_download_data.py`, `test_enzyme_db_build.py`): those scripts ship in their own image and are not importable as part of the app package, so their tests sit beside them — never move them into the app suite.
    - Test files should be named `test_<module_or_feature>.py` so the scope is obvious (e.g., `test_backend_config.py` tests `backend/config.py`).
    - Test functions should be named `test_*`.
    - **Resilient to change**: Tests for registries or auto-discovered components (e.g., tools, icons) must **scan the source at runtime** rather than hard-coding names or counts.

2.  **Structure & Style**
    - Write **flat test functions**, not test classes.
    - One test per distinct behavior — avoid multiple tests that verify the same thing.
    - **Use `@pytest.mark.parametrize`** when multiple tests exercise the same behavior with different inputs (e.g., boundary values, invalid input variants). Always provide descriptive `ids=`.
    - Use fixtures in `conftest.py` for shared setup (component instances, helpers like `find_components` and `get_text`).
    - Focus on testing **functionality** of components and callbacks, not implementation details.
    - **Section headers**: In larger test files, group related tests under comment banners (e.g., `# Discovery`, `# Schema`). Do **not** number the sections.

3.  **Writing for Humans**
    - **Write for scientists**: Test code should be readable by developers who are not Python experts.
    - Use descriptive variable names (e.g., `_tool_folder_names`, not `_SUBPKGS`).
    - Use plain-English docstrings and explicit loops over clever comprehensions.
    - Add inline comments that explain *why*.

4.  **Technical Requirements**
    - **Import order matters**: Always import `app` before importing any page module (e.g., `home.py`) — `dash.register_page()` requires the Dash app to be instantiated first.
    - Quality over quantity — prioritize well-written, meaningful tests over brittle or trivial ones.

5.  **Callback Testing**
    - Mock `ctx` by patching it at the callback's module path (e.g., `patch("enzyme_tk_app.app.tools.<slug>.callbacks.ctx")`), then set `mock_ctx.triggered_id` to the component ID that should fire.
    - Mock `get_task_scheduler` the same way and assert `submit_job` was (or was not) called.
    - **The per-session job cap is OFF for the whole suite** — `conftest.py`'s autouse `_submission_limit_off` fixture pins it, so a submit-callback test never reaches for a real scheduler just because a developer has `APP_IN_PRODUCTION_MODE` exported (`tox.ini` sets `passenv = *`). To test the cap itself, `monkeypatch.setattr(submission_limits, "PRODUCTION_MODE", True)` and patch **`enzyme_tk_app.app.utils.submission_limits.get_task_scheduler`** — the tool's `callbacks.get_task_scheduler` is a *different* binding and patching it leaves the limiter talking to real Redis. `monkeypatch.setenv` does nothing either way: the constants bind at import (the same reason `test_backend_config.py` patches `config`'s globals). See `test_submission_limits.py` and `test_submit_is_refused_at_the_active_job_limit` in `test_tools_timer.py` — the behavioural one is what catches a guard placed *after* `submit_job`, which `test_tools.py`'s import walk cannot see.
    - **The submission captcha is OFF for the whole suite too** — `conftest.py`'s autouse `_captcha_off` fixture pins it. It is a **separate** fixture from `_submission_limit_off` on purpose: `captcha.PRODUCTION_MODE` and `submission_limits.PRODUCTION_MODE` are two module-level reads of the same `APP_IN_PRODUCTION_MODE`, so patching one does nothing to the other, and without both a developer with the switch exported would see every submit-callback test fail on a missing captcha payload. To test the captcha itself, `monkeypatch.setattr(captcha, "PRODUCTION_MODE", True)` and mint a real proof with `new_challenge()` — never a hand-built payload string, which only ever proves the rejection path. Patch the constants, never `setenv`: they bind at import. See `test_captcha.py` and the three behavioural tests in `test_tools_timer.py`, which pin that the guard runs, that it sits *before* the job cap, and that a field error still wins over it.
    - **Every tool's data checks are pinned "nothing to report" for the whole suite** — `conftest.py`'s autouse `_tool_data_checks_clean` fixture, the third switch in the same family as the two above and pinned for the same reason: `validate_tool_data` is OR'd into every `validate_*` callback and is the **first** guard in every `submit_*`, so without it a developer missing the Func-E checkpoints — and CI, which downloads nothing — sees Run disabled and every submit refused for a reason unrelated to the code under test. It replaces `CHECK_DATA` / `CHECK_DATA_WARNINGS` on **`enzyme_tk_app.app.tools`**, the dicts `check_tool_data` imports *inside itself* on every call, so one patch reaches the card badge, the Run gate and the submit guard together — patching `data_warning`'s or a tool's own binding reaches none of them. To drive a check, call `conftest.patch_tool_checks(monkeypatch, slug, blocking=[...], warnings=[...])`: a list of labels, or a callable to register a check that raises, with every *other* tool left unregistered (which is what a tool with no `check_data.py` looks like). The two channels are not interchangeable — `blocking` disables Run, `warnings` never gates anything — and the split is what keeps one malformed file from switching off a working tool (`test_check_data.py`). What the user is shown is the `data/...` path lifted out of the label, **not** the label, so assert the path (`test_tools_timer.py`, `test_tool_cards.py`); a check that raises degrades to `CHECK_FAILED_MESSAGE`, which deliberately does *not* name the download script. One consequence worth knowing: a module-level `from enzyme_tk_app.app.tools import CHECK_DATA` still sees the real registry, because the fixture replaces the attribute rather than mutating the dict — that is how `test_check_data.py` asserts on discovery.
    - **Both of a submit callback's outcomes are components, so `in result` proves nothing** — it tests tuple/child membership, not substrings. Use the two `conftest.py` readers, which assert the *shape* before handing back text: `submission_error_text(result)` checks the result really is the `modal-submission-error` row (not a success, not a bare string) and returns its message, and `submitted_job_id(result)` reads the full job id out of the tooltip. **Never assert a job id against the rendered text** — the row puts it through `truncate_id()`, so `"job-rxn-123" in get_text(result)` fails while a prefix passes for the wrong reason; assert equality against `submitted_job_id(result)` instead. On the success path also pin the `/my-tasks` anchor via `find_components(result, html.A)`. See `test_submit_success_links_to_my_tasks` and `test_submit_error_returns_the_shared_error_row` in `test_tools_timer.py`; `test_tools.py`'s `test_every_tool_links_to_my_tasks_on_success` already covers the import for every tool, so do not re-assert it per tool.
    - When a callback reads `flask.g.session_id`, wrap the call in `server.test_request_context()` and set `g.session_id` before invoking.
    - **A `validate_*` test parametrizes presence.** With a `dbc.Input(type="number", min=…, max=…)` the browser rejects an out-of-range entry and Dash sends `None`, so `None` — not `500` — is what "the user typed something invalid" actually looks like to the callback. Keep one case pinning that a bare `0` is *present* (button enabled): it is unreachable through the UI, but it is what stops someone rewriting the check as `bool(value)`. See `test_validate_timer_form` in `test_tools_timer.py`.
    - **A SMILES tool's `validate_*` also parametrizes validity, and unpacks a 3-tuple** — `(disabled, invalid, message)`. Cover both halves of the split that is easy to get wrong: a *blank* field is disabled but **not** marked (`invalid is False`), while a *present-but-unparseable* one is disabled **and** marked. Assert `bool(message) is expected_invalid` so a red field always says why. Use a real structure for the valid cases — a placeholder like `"A>>B"` is not parseable and will now fail on its own merits. See `test_validate_reaction_form` in `test_tools_reaction_similarity.py`.
    - **`populate_example_*` returns a tuple with the Task Name last** — unpack it (`smiles, task_name = populate_example_reaction(...)`), never compare the return value to a bare string. Read the expected input out of the tool's own example list (`_get_example_reactions()[0]`, `EXAMPLE_REACTIONS`) rather than retyping a SMILES. **The tuple is as long as the example prefills** — two outputs for most tools, four for `sequence_similarity` (sequence, EC filter, cofactor filter, name) — so unpack every position and keep reading the name off the end; a test that unpacks a fixed two is what breaks the day a tool prefills one more field. The branch worth a per-tool test is the **`no_update`** one: a value that is not a shipped example fills the input but leaves the Task Name alone (`assert task_name is no_update`), and every other prefilled field with it. When an example *does* prefill extra fields, pin the pair the user can actually confuse: that a declared filter arrives in its dropdown, and that an example declaring none returns `[]` and not `no_update` — clearing the previous example's filter rather than carrying it (`write-callback` §2). Parametrize those over the examples' `task_name`s rather than repeating a test per example. That *every* example prefills a name is already pinned once for all tools by `test_every_example_prefills_a_task_name` in `test_tools.py` — do not re-assert it per tool. That shared test checks only that the name is a non-blank string, never its shape, so the one thing a per-tool test still pins is the *value* for a known example (`assert task_name == "glucose"`) — the exact string, with no tool-slug prefix.

6.  **Early Returns & Exception Coverage**
    - Use `@pytest.mark.parametrize` to cover guard-clause branches (e.g., `None`, `""`, whitespace, falsy values) in a single test function.
    - For functions that `raise PreventUpdate`, assert with `pytest.raises(PreventUpdate)`.
    - For functions that `raise ValueError`, use `pytest.raises(ValueError, match=...)` to verify the message.

7.  **Database-Backed Tools**
    - `params["databases"]` is a `list[str]` — never a bare string. Point the tool's data-dir constant at `tmp_path` and write the CSVs/pickles the test needs rather than relying on whatever the real data directory happens to hold. **One sanctioned exception:** the tracked data — the demo sets (`*_demo_set` under `data/`) and the example query structures in `data/structures/` — which `test_demo_data.py` uses deliberately because what ships *is* what it asserts on, and which is also the one place a test calls a tool's `run()` against a real data directory rather than a `tmp_path` fixture (each chemistry example must still come back with a full page of hits from `enzymemap_demo_set.csv`). Such a test must assert containment, never equality, since a developer machine also has the full sets in those directories. Do not "fix" it by monkeypatching the constants away.
    - **Patch the data-dir constant in `utils.data_loading` too**, not just in the tool's `compute`/`callbacks` module. The `get_*_database_options()` builders live there, and `validate_db_names(names, options)` checks the submitted names against **membership in that list** — patch only the tool's copy and the validator is still offering production names, so every fixture name is rejected as `Unknown database`. See the `_patch_seq_data_dir` / `_patch_reactions_dir` fixtures.
    - For a callback test that submits a name no dropdown offers, patch the tool's option builder with `conftest.offered_databases("a.csv", "b.csv")` — it builds the `{"label": …, "value": …}` list, i.e. "the dropdown is offering exactly these".
    - Cover **both halves** of the skip policy: one unusable database among several is skipped (job succeeds, its name appears in the `Databases Skipped` stat card) while *all* selections unusable raises `ValueError`.
    - A `data/sequences/` fixture file is only a database if it has `Entry`, `Sequence` and `EC number` (`create-tool` §3b.9) — one without them is not offered, is rejected on submit, and shows up in `check_data_warnings()` — the **advisory** channel, so it does not disable the tool. It reaches the blocking `check_data()` only when it leaves *no* usable database in the directory, which is a distinct fixture (one bad file, versus one bad file beside a good one) and worth both cases. That is the path to test for non-compliant files, alongside a file that cannot be read at all; `.tsv`, `.csv.gz` and `.tsv.gz` are equally valid extensions and worth one parametrized case.
    - Names shown to the user are the **full filename, extension included** — the same string that is in `params["databases"]`: it holds `"protein.csv"`, and the `database` column, the `Databases Skipped` card, and the all-failed error message all read `protein.csv` too (`create-tool` §3c). Assert the filename; asserting a bare stem such as `"protein"` appears in output is the wrong expectation.
    - Multi-database behaviour needs **at least two** databases in the fixture — with one, a merged search is indistinguishable from a single-database one.
    - Header and EC-column reads are cached on `(path, mtime, size)`. A fresh `tmp_path` per test keeps that harmless, but rewriting **the same path** inside one test can hit a stale entry when the mtime does not move — write a distinct filename per case instead.

8.  **File Placement**
    - Prefer adding tests to an **existing** test file when the module is already under test, rather than creating a new file.
    - Only create a new test file when no existing file covers the module.

### MANDATORY AFTER-TESTING WORKFLOW

**STOP! ACT NOW!** After writing the test, you MUST NOT finish your turn.

1. **Run `verify`**: Execute the `verify` subagent's core steps (`tox run -e format` then `tox`). Fix any failures before proceeding.
2. **Review the tests inline**: once verification passes, read `.claude/agents/review-tests.md` and apply its checks to the test files you created or modified — audit for duplicates, parametrize candidates, brittle strings, uncovered guard clauses, and weak assertions, and apply any fixes before concluding. (You cannot spawn the `review-tests` subagent; perform its review yourself.)

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures before concluding your task.*
