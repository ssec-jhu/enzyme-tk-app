# Copilot Instructions for EnzymeTK Tool Suite

## Project Setup
- This is a **Dash** (Plotly) Python web app.
- Run the app with: `python3 -m enzyme_tk_app.app.app` from the project root.
- Always use **package imports** (e.g., `from enzyme_tk_app.app.components.navbar import Navbar`), never relative path hacks with `sys.path`.

## Component IDs
- All Dash component IDs must follow the pattern: `id-<component-type>-<name>` (e.g., `id-div-nav-links`, `id-location`).
- Only assign an `id` to a component if it is used in a **callback** (`Input`, `Output`, or `State`). HTML anchor targets are an exception.

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
- CSS files live in `enzyme_tk_app/app/assets/` and are split by concern (`00-variables.css` … `06-footer.css`). Only add a new CSS class when the style truly needs CSS features or is reused across files.

## Icons
- All FontAwesome icon class strings should be defined as constants in `enzyme_tk_app/app/components/icons.py` with a descriptive name relative to where they are used (e.g., `ICON_LOGO = "fa-solid fa-flask"`).
- Components should import icon constants from `icons.py` rather than hardcoding class strings.
- Icons should be free icons from FontAwesome's free collection, not pro icons.

## Code Style
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
- **File organization**: UI/layout tests (app config, navbar, footer, hero, home page) go in `test_app.py`. Tool registry and tool card tests go in `test_tool_cards.py`.
- **Import order matters**: always import `app` before importing any page module (e.g., `home.py`) — `dash.register_page()` requires the Dash app to be instantiated first. See `test_app.py` for the pattern.

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
- Build: `docker build -t enzyme-tk-app .`
- Run: `docker run -p 8050:8050 enzyme-tk-app`
- The Dockerfile uses `gunicorn enzyme_tk_app.app.app:server` — the `server` variable in `app.py` exposes the underlying Flask server.
- Production requirements are in `requirements/prd.txt` (not `pyproject.toml` optional-dependencies).

## Final Checks Before Committing
- Ensure new code has appropriate docstrings and comments.
- For full verification (format, lint, security, tests, app & Docker smoke tests), ask the agent to **"run the verify agent"** — see `AGENTS.md`.
