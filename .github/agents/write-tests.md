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

### Verification

Before completing a test-writing task, the agent should:
- Ensure the new tests pass: `tox run -e test -- <path_to_test_file>`
- Verify formatting: `tox run -e format`
