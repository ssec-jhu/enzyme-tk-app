# Copilot Instructions for EnzymeTK Tool Suite

## Project Setup
- This is a **Dash** (Plotly) Python web app.
- Run the app with: `python3 -m enzyme_tk_app.app.app` from the project root.
- Always use **package imports** (e.g., `from enzyme_tk_app.app.components.navbar import navbar`), never relative path hacks with `sys.path`.

## Component IDs
- All Dash component IDs must follow the pattern: `id-<component-type>-<name>` (e.g., `id-div-nav-links`, `id-location`).
- Only assign an `id` to a component if it is used in a **callback** (`Input`, `Output`, or `State`). HTML anchor targets are an exception.

## Adding a New Tool (Algorithm)
- **All new tools MUST follow the architectural guidelines and module structure defined in the [Create Tool Agent](agents/create-tool.md).**

## Backend Architecture
- The backend task scheduling system lives in `enzyme_tk_app/app/backend/`.
- All Dash UI code programs against the `TaskScheduler` ABC — never import Celery, Redis, or backend internals in UI code.
- Use `get_task_scheduler()` from `enzyme_tk_app.app.backend` to obtain the singleton scheduler.
- Session management uses anonymous UUID cookies (`etk_session_id`). Access the session ID via `flask.g.session_id`.
- Each tool that does computation adds `compute.py` exporting `def run(params: dict) -> dict`. The `params` dict matches the form fields from the modal. The returned dict must be JSON-serialisable.
- Large results (> 512 KB) are automatically offloaded to `JOB_OUTPUTS_PATH` — tool authors just return a plain dict.
- Jobs are stored in Redis with a TTL (default 24h).
- **Redis TTL invariant — dual-key sync:** Every job has two Redis keys: a *hash* (`job:<job_id>`) and a membership entry in a *session set* (`session:<session_id>:jobs`). Whenever code refreshes, sets, or resets the TTL on the job hash it **must also refresh the TTL on the session set** (and vice-versa). If only one key's TTL is extended, the other can expire first — breaking ownership checks (`_owns_job`), job listing (`list_jobs`), or leaving orphan data. Audit both keys any time you add or modify a method that calls `expire`, `hset` on a status transition, or `delete` on either key.
- The `docker-compose.yml` orchestrates web, Redis, and worker containers with a shared volume.
- Shared constants like `TERMINAL_STATUSES` live in `models.py` — import from there, never duplicate.

## Callback Naming
- Callback functions names should start with a verb that describes the action they perform (e.g., `update`, `toggle`, `get`) then followed by a description of what they update or toggle (e.g., `update_active_link`, `toggle_dark_mode`).
- Keep callbacks close to the component they modify — define them in the same file as the component that owns the `Output`.
- In callbacks with early-exit guard clauses (e.g., no click, no triggered ID), use `raise PreventUpdate` (from `dash.exceptions`) instead of returning an empty string or `None`. This tells Dash to skip the update entirely, avoiding unnecessary DOM writes. See `my_tasks.py` for examples.
- Pass `Output`, `Input`, and `State` as **positional arguments** to `@callback()` — do not wrap them in `[...]` lists (legacy Dash v1 pattern).
- **For detailed callback authoring patterns** (guard clauses vs. intentional DOM writes, decorator syntax, naming), follow the [Write-Callback Agent](agents/write-callback.md).


## Inline Styles
- Group related styles into constants at the top of the file (e.g., `STYLE_NAVBAR`, `STYLE_FOOTER`).
- Use descriptive names for style constants that indicate where they are applied.
- Keep inline styles in the component file, but if styles are shared across similar components in the file, consider refactoring into a shared style constant so changing the style in one place will update all components that use it.

## When to Use CSS vs Inline Styles
- **Use CSS** for styles that require pseudo-classes (`:hover`, `:focus`, `::after`), media queries, animations, or are shared across multiple components/pages.
- **Use inline styles** (Python dicts) for one-off styles scoped to a single component that don't need pseudo-classes — keep the style co-located with the element it applies to.
- When converting a CSS class to inline, merge all cascading rules into one flat `STYLE_*` constant (e.g., `.badge` + `.badge-lib` → `STYLE_BADGE_LIB`).
- CSS files live in `enzyme_tk_app/app/assets/` and are split by concern with numbered prefixes (e.g., `00-variables.css`, `05-cards.css`). Only add a new CSS class when the style truly needs CSS features or is reused across files.
- **When writing or editing any CSS in `assets/`, match the banner/section-comment style and indentation already used across the existing stylesheets.** In short:
  - **Top-of-file banner:** a three-line block opened and closed by a full row of `=`, with the title (and any note lines) indented 3 spaces in the middle:
    ```css
    /* ==========================================================================
       Title — optional one-line note
       ========================================================================== */
    ```
  - **Section separator:** a single-line comment `/* --- Title ---…--- */` where the trailing dashes pad the line to roughly 75 columns.
  - **Indentation:** selectors and at-rules start at column 0; their declarations are indented **4 spaces** (never tabs).

## Shared UI Components — Stat Cards
- **All stat-card-style elements across the app must use the same CSS classes** defined in `08-jobs.css`:
  - Container: `jobs-stats-row` (flex row with wrapping and gap).
  - Card: `jobs-stat-card` (flex: 1, centered, bordered, shadowed).
  - Value: `jobs-stat-value` (large, bold, primary color).
  - Label: `jobs-stat-label` (small, uppercase, secondary text).
- **Never create page-specific stat card classes** (e.g., no `jobs-detail-card`, `jobs-meta-card`). Reuse the shared set everywhere — My Jobs stats, Job Results header, tool-specific results meta, etc.
- When adding new pages with summary statistics, follow the same pattern.

## Icons
- All FontAwesome icon class strings should be defined as constants in `enzyme_tk_app/app/components/icons.py` with a descriptive name relative to where they are used (e.g., `ICON_LOGO = "fa-solid fa-flask"`).
- Components should import icon constants from `icons.py` rather than hardcoding class strings.
- Icons should be free icons from FontAwesome's free collection, not pro icons.

## Code Style
- Follow **PEP 8 naming conventions** strictly:
  - Functions and methods: `snake_case` (e.g., `tool_card`, `default_results_layout`).
  - Variables and parameters: `snake_case`.
  - Constants: `UPPER_SNAKE_CASE` (e.g., `STYLE_BADGE_LIB`, `NAV_LINKS`).
  - Classes and TypedDicts: `PascalCase` (e.g., `ToolDef`, `JobInfo`).
  - **Never use PascalCase for functions** — even for Dash component factories, use `snake_case` (e.g., `navbar()`, not `Navbar()`).
- Add **docstrings** (Google style) to all modules, functions, and classes.
- Add **inline comments** for non-obvious logic.
- Use **double quotes** for all strings.
- Line length limit is **120** characters.
- Keep CSS class names in sync — don't add a `className` unless there is a matching rule in `styles.css` or it comes from an external library (e.g., FontAwesome).

## Formatting & Linting
- This project uses **ruff** for formatting and linting, configured in `pyproject.toml`.
- After making code changes, run the **Verify Agent** (defined in [agents/verify.md](agents/verify.md)) which executes `tox run -e format` then `tox`. All code-generating agents invoke Verify automatically as their final step.
- `tox run -e format` auto-formats code, sorts imports, **and removes unused imports** (F401).
- All code must pass `tox run -e check-style` before being considered done (included in the `tox` default envlist).
- No need for permission to run tox commands — they are part of the development workflow.
- If an import is needed for its **side effect** (e.g., `from enzyme_tk_app.app.app import app` to satisfy `dash.register_page()`), add a `# noqa: F401` comment with a reason to prevent auto-removal.

## Writing Tests
- **All new tests MUST follow the architectural guidelines and pytest patterns defined in the [Write-Tests Agent](agents/write-tests.md).**
- After writing tests, the Write-Tests agent automatically runs the Verify Agent and then the Review-Tests agent.
