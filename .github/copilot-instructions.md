# Copilot Instructions for EnzymeTK Tool Suite

## Project Setup
- This is a **Dash** (Plotly) Python web app.
- Run the app with: `python3 -m enzyme_tk_app.app.app` from the project root.
- Always use **package imports** (e.g., `from enzyme_tk_app.app.components.navbar import navbar`), never relative path hacks with `sys.path`.

## Component IDs
- All Dash component IDs must follow the pattern: `id-<component-type>-<name>` (e.g., `id-div-nav-links`, `id-location`).
- Only assign an `id` to a component if it is used in a **callback** (`Input`, `Output`, or `State`). HTML anchor targets are an exception.

## Adding a New Tool (Algorithm)
- Tools live in self-contained sub-packages under `enzyme_tk_app/app/tools/`.
- Auto-discovery in `tools/__init__.py` scans sub-packages at import time — **no central file to edit**.
- To add a tool, create a folder with:

  | File | Required? | Must export | Purpose |
  |------|-----------|-------------|---------|
  | `__init__.py` | Yes | `TOOL_DEF: ToolDef` | Metadata (slug, title, desc, icon, order, libraries) |
  | `modal.py` | No | `modal() → dbc.Modal` | Input form shown when "Launch →" is clicked |
  | `callbacks.py` | No | *(side-effect)* | `@callback` decorators auto-register on import |
  | `compute.py` | No | `run(params) → dict` | Core algorithm executed by the Celery worker |
  | `results.py` | No | `results_layout(job) → html.Div` | Custom results page; falls back to raw JSON if absent |
- `TOOL_DEF` requires an `order: int` field that controls the card's position in the grid (lower numbers appear first).
- Tool card appears automatically from `TOOL_DEF`. Modal appears automatically if `modal.py` exists. Callbacks register automatically if `callbacks.py` exists. Custom results page appears if `results.py` exists.
- Import icon constants from `enzyme_tk_app.app.components.icons` and the `ToolDef` type from `enzyme_tk_app.app.tools`.
- `ToolDef` supports an optional `max_duration` field (timeout in seconds, default 3600). When a job exceeds this duration the worker records it as `TIMEOUT`. A small hard-kill grace period (`HARD_TIMEOUT_GRACE_SECONDS`, default 60 s) is added automatically.

### Single-source slug & title — the rename-once invariant
- **`TOOL_DEF` in `__init__.py` is the single source of truth** for a tool's slug, title, and icon. Changing them there must be the only edit needed (besides renaming the folder — see below).
- In `modal.py` and `callbacks.py`, import `TOOL_DEF` from the tool's own package and use it directly:
  ```python
  from enzyme_tk_app.app.tools.<tool_folder> import TOOL_DEF
  ```
- **Build all slug-dependent component IDs** with f-strings from `TOOL_DEF["slug"]` — never hardcode the slug in an ID string:
  - Modal ID: `f"id-modal-{TOOL_DEF['slug']}"`
  - Launch button match: `f"id-btn-launch-{TOOL_DEF['slug']}"` (must match the auto-generated ID from `tool_cards.py`)
  - Sub-component IDs: `f"id-btn-{TOOL_DEF['slug']}-submit"`, `f"id-input-{TOOL_DEF['slug']}-duration"`, etc.
- **Use `TOOL_DEF["title"]`** for the modal header text instead of a hardcoded string.
- **Use `TOOL_DEF["slug"]`** when calling `scheduler.submit_job()` instead of a hardcoded slug string.
- **Do not create local aliases** like `_SLUG = TOOL_DEF["slug"]` — use `TOOL_DEF["slug"]` directly to keep the origin obvious.
- **Folder-name invariant:** The folder name **must** equal `slug.replace("-", "_")`. The task dispatcher in `tasks.py` converts the slug back to a folder name using this convention. If you change the slug, rename the folder to match.
- See `timer_tool_template/modal.py` and `timer_tool_template/callbacks.py` for the canonical pattern.

### Modal dropdowns, inputs, and form controls — use `themed-control` everywhere
- **All new UI Modals must strictly follow the standard Layout Structure documented in `.github/agents/create-modal.md`. Read that file before generating or modifying any `modal.py` components.**
- **All dropdowns in tool modals must use `dcc.Dropdown`** (from `dash`), never `dbc.Select` (from `dash_bootstrap_components`). This ensures consistent look-and-feel and theming across all tools.
- **For all form controls inside modals (Dropdowns, Inputs, Textareas, Checkboxes, RadioItems)** always add the CSS class `themed-control` for dark-mode-aware styling (defined in `07-modals.css`).
- Example for a dropdown:
  ```python
  dcc.Dropdown(
      id=f"id-dropdown-{TOOL_DEF['slug']}-example",
      options=[...],
      className="mb-3 themed-control",
  )
  ```
- Set `multi=True` or `multi=False` as appropriate for the tool's needs.
- Set `searchable=False` for short option lists (e.g., example pickers); leave it `True` (default) for longer lists.
- Use `id-dropdown-` as the component-type prefix in the ID (not `id-select-`).
- See `reaction_similarity/modal.py` for a multi-select database dropdown and single-select example picker.

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
- **Dual-scheduler invariant — keep Local in sync with Celery:** There are two `TaskScheduler` implementations: `CeleryTaskScheduler` (production, Redis + Celery) and `LocalTaskScheduler` (dev, in-memory dicts). Both must honour the same behavioural contract defined in the `TaskScheduler` ABC and its docstrings. When modifying any method in `CeleryTaskScheduler`, **always review the corresponding method in `LocalTaskScheduler`** to ensure the same semantics (e.g., terminal-status guards on delete/clear, ownership checks, return-value schema). Shared constants like `TERMINAL_STATUSES` live in `models.py` — import from there, never duplicate. Run `test_backend_task_scheduler_local.py` after any change to either scheduler.

## Callback Naming
- Callback functions names should start with a verb that describes the action they perform (e.g., `update`, `toggle`, `get`) then followed by a description of what they update or toggle (e.g., `update_active_link`, `toggle_dark_mode`).
- Keep callbacks close to the component they modify — define them in the same file as the component that owns the `Output`.

## Inline Styles
- Group related styles into constants at the top of the file (e.g., `STYLE_NAVBAR`, `STYLE_FOOTER`).
- Use descriptive names for style constants that indicate where they are applied.
- Keep inline styles in the component file, but if styles are shared across similar components in the file, consider refactoring into a shared style constant so changing the style in one place will update all components that use it.

## When to Use CSS vs Inline Styles
- **Use CSS** for styles that require pseudo-classes (`:hover`, `:focus`, `::after`), media queries, animations, or are shared across multiple components/pages.
- **Use inline styles** (Python dicts) for one-off styles scoped to a single component that don't need pseudo-classes — keep the style co-located with the element it applies to.
- When converting a CSS class to inline, merge all cascading rules into one flat `STYLE_*` constant (e.g., `.badge` + `.badge-lib` → `STYLE_BADGE_LIB`).
- CSS files live in `enzyme_tk_app/app/assets/` and are split by concern with numbered prefixes (e.g., `00-variables.css`, `05-cards.css`). Only add a new CSS class when the style truly needs CSS features or is reused across files.

## Shared UI Components — Stat Cards
- **All stat-card-style elements across the app must use the same CSS classes** defined in `08-jobs.css`:
  - Container: `jobs-stats-row` (flex row with wrapping and gap).
  - Card: `jobs-stat-card` (flex: 1, centered, bordered, shadowed).
  - Value: `jobs-stat-value` (large, bold, primary color).
  - Label: `jobs-stat-label` (small, uppercase, secondary text).
- **Never create page-specific stat card classes** (e.g., no `jobs-detail-card`, `jobs-meta-card`). Reuse the shared set everywhere — My Jobs stats, Job Results header, tool-specific results meta, etc.
- See `enzyme_tk_app/app/components/results_helpers.py` and `enzyme_tk_app/app/pages/my_jobs_callbacks.py` for existing usage of these classes.
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
- After making code changes, always run: `tox run -e format` to auto-format, then `tox run -e check-style` to verify.
- `tox run -e format` auto-formats code, sorts imports, **and removes unused imports** (F401).
- All code must pass `tox run -e check-style` before being considered done.
- No need for permission to run tox commands — they are part of the development workflow.
- If an import is needed for its **side effect** (e.g., `from enzyme_tk_app.app.app import app` to satisfy `dash.register_page()`), add a `# noqa: F401` comment with a reason to prevent auto-removal.

## Writing Tests
- Tests live in `enzyme_tk_app/app/tests/` and use **pytest**.
- Test files should be named `test_*.py` and test functions should be named `test_*`.
- Write **flat test functions**, not test classes. One test per distinct behavior — avoid multiple tests that verify the same thing.
- Use fixtures in `conftest.py` for shared setup (component instances, helpers like `find_components` and `get_text`).
- Focus on testing the **functionality** of components and callbacks, not implementation details.
- **File naming convention**: name test files `test_<module_or_feature>.py` so the scope is obvious from the filename alone (e.g., `test_backend_config.py` tests `backend/config.py`). Group related tests in one file rather than splitting by class — scan `enzyme_tk_app/app/tests/` to see the current layout.
- **Import order matters**: always import `app` before importing any page module (e.g., `home.py`) — `dash.register_page()` requires the Dash app to be instantiated first. See `test_app.py` for the pattern.
- **Write for scientists**: test code should be readable by developers who are not Python experts. Use descriptive variable names (`_tool_folder_names`, not `_SUBPKGS`), plain-English docstrings, explicit loops over clever comprehensions, and inline comments that explain *why*. See `test_tools.py` for the style.
- **Resilient to change**: tests for registries or auto-discovered components (e.g., tools, icons) must **scan the source at runtime** rather than hard-coding names or counts. This way adding or removing a tool folder doesn't break existing tests. See the `_tool_folder_names` pattern in `test_tools.py`.
- **Numbered section headers**: in larger test files, group related tests under comment banners with numbers (e.g., `# 1. Discovery`, `# 2. Schema`) so the logical flow is easy to follow.
- **Why this matters**: adding context to tests helps future developers understand the purpose and importance of each test, making maintenance easier and reducing the risk of accidental breakage.
- Quality over quantity — it's better to have a few well-written, meaningful tests than many brittle or trivial ones.

## Running & Testing
- After making changes, always **run the app** to verify it starts without errors.
- Kill any existing process on the port before restarting.

## Dependencies
- **Two systems, distinct roles:**
  - `pyproject.toml` — loose/minimum version constraints (`dash>=2.0`). Used by `pip install .` and `pip install .[dev]`. This is the library-style declaration.
  - `requirements/*.txt` — exact-pinned versions (`dash==4.0.0`). Used by Docker, tox, and CI for **reproducible** environments.
- **Requirements file layout** (`requirements/`):
  | File | Purpose | Consumers |
  |------|---------|-----------|
  | `prd.txt` | Runtime deps (dash, gunicorn) | Dockerfile, tox `test` |
  | `test.txt` | Linting + testing (ruff, pytest, bandit) | tox `check-style`, `format`, `test` |
  | `dev.txt` | Local dev orchestration (tox) | `all.txt` |
  | `build.txt` | Package build (setuptools, build) | tox `build-dist` |
  | `docs.txt` | Sphinx doc generation | tox `build-docs` |
  | `all.txt` | Umbrella — includes all of the above | Developer local install |
- **Adding a new dependency:**
  1. Add the loose pin to the appropriate section in `pyproject.toml` (`dependencies` for runtime, `[project.optional-dependencies]` for dev/docs).
  2. Add the exact pin to the matching `requirements/*.txt` file.
  3. Keep `requirements/*.txt` files **self-contained** — each file only lists its own packages (no `-r` cross-references except `all.txt`).
- **Never duplicate a package** across requirements files — pick the one file where it belongs. `all.txt` composes them all.

## Docker
- The app runs in Docker with **gunicorn** as the production WSGI server.
- For local development with the full stack (web + Redis + Celery worker), use: `docker compose up --build`
- Build standalone: `docker build -t enzyme-tk-app .`
- Run standalone: `docker run -p 8050:8050 enzyme-tk-app`
- The Dockerfile uses `gunicorn enzyme_tk_app.app.app:server` — the `server` variable in `app.py` exposes the underlying Flask server.
- `docker-compose.yml` defines three services: `web` (gunicorn), `redis` (broker + results), and `worker` (Celery). A shared volume at `/data` is mounted on web and worker. Job result files are stored under `JOB_OUTPUTS_PATH` (default `/data/job_outputs`).
- Production requirements are in `requirements/prd.txt` (not `pyproject.toml` optional-dependencies).

## Final Checks Before Committing
- Ensure new code has appropriate docstrings and comments.
- For full verification (format, lint, security, tests, app & Docker smoke tests), ask the agent to **"run the verify agent"** — Run `.github/verify-docker-build-agent.md`.
