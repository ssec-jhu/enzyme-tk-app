# Write-Tests Agent

**Trigger:** When asked to "write tests," "create a test," or "add test coverage" for a module or feature.

The agent must follow these strictly defined patterns for writing tests in the EnzymeTK project.

### Guidelines

1.  **Location & Discovery**
    - Tests live in `enzyme_tk_app/app/tests/` and use **pytest**.
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
    - When a callback reads `flask.g.session_id`, wrap the call in `server.test_request_context()` and set `g.session_id` before invoking.

6.  **Early Returns & Exception Coverage**
    - Use `@pytest.mark.parametrize` to cover guard-clause branches (e.g., `None`, `""`, whitespace, falsy values) in a single test function.
    - For functions that `raise PreventUpdate`, assert with `pytest.raises(PreventUpdate)`.
    - For functions that `raise ValueError`, use `pytest.raises(ValueError, match=...)` to verify the message.

7.  **File Placement**
    - Prefer adding tests to an **existing** test file when the module is already under test, rather than creating a new file.
    - Only create a new test file when no existing file covers the module.

### MANDATORY AFTER-TESTING WORKFLOW

**STOP! ACT NOW!** After writing the test, you MUST NOT finish your turn.

1. **Run the Verify Agent**: Execute the **core steps** defined in [`.github/agents/verify.md`](verify.md) (`tox run -e format` then `tox`). Fix any failures before proceeding.
2. **Run the Review-Tests Agent**: Once verification passes, invoke the **Review-Tests agent** (defined in [`.github/agents/review-tests.md`](review-tests.md)) on the test files you created or modified. Let it audit for duplicates, parametrize candidates, brittle strings, uncovered guard clauses, and weak assertions — then apply any fixes it recommends before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures before concluding your task.*
