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
- Keep inline styles in the component file, but if styles are shared across similar components in the file, consider refatoring into a shared style constant so changeing the style in one place will update all components that use it.

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
- All code must pass `tox run -e check-style` before being considered done.
- No need for permission to run tox commands — they are part of the development workflow.

## Running & Testing
- After making changes, always **run the app** to verify it starts without errors.
- Kill any existing process on the port before restarting.
