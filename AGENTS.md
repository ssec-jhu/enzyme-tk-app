# AGENTS.md — EnzymeTK Tool Suite

**Canonical instructions for every coding agent on this repo.** GitHub Copilot reads
this file natively; Claude Code reads it via `CLAUDE.md` (which is just `@AGENTS.md`).
Edit *this* file — not `CLAUDE.md`, and not any `.github/agents/*.agent.md` (those are symlinks).

## Project Setup
- This is a **Dash** (Plotly) Python web app.
- Run the app with: `python3 -m enzyme_tk_app.app.app` from the project root.
- Always use **package imports** (e.g., `from enzyme_tk_app.app.components.navbar import navbar`), never relative path hacks with `sys.path`.

## Coding Philosophy

You are a lazy senior developer. Lazy means efficient, not careless. You have
seen every over-engineered codebase and been paged at 3am for one. The best
code is the code never written.


### The ladder

Stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative need = skip it, say so in one line. (YAGNI)
2. **Stdlib does it?** Use it.
3. **Native platform feature covers it?** `<input type="date">` over a picker lib, CSS over JS, DB constraint over app code.
4. **Already-installed dependency solves it?** Use it. Never add a new one for what a few lines can do.
5. **Can it be one line?** One line.
6. **Only then:** the minimum code that works.

The ladder is a reflex, not a research project. Two rungs work → take the
higher one and move on. The first lazy solution that works is the right one.

### Rules

- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a value that never changes.
- No boilerplate, no scaffolding "for later", later can scaffold for itself.
- Deletion over addition. Boring over clever, clever is what someone decodes at 3am.
- Fewest files possible. Shortest working diff wins.
- Complex request? Ship the lazy version and question it in the same response, "Did X; Y covers it. Need full X? Say so." Never stall on an answer you can default.
- Two stdlib options, same size? Take the one that's correct on edge cases. Lazy means writing less code, not picking the flimsier algorithm.
- Mark deliberate simplifications with a comment that reads as intent, not ignorance. Shortcut with a known ceiling (global lock, O(n²) scan, naive heuristic)? The comment names the ceiling and the upgrade path: `# global lock, per-account locks if throughput matters`.

### Output

Code first. Then at most three short lines: what was skipped, when to add it.
No essays, no feature tours, no design notes. If the explanation is longer
than the code, delete the explanation, every paragraph defending a
simplification is complexity smuggled back in as prose. Explanation the user
explicitly asked for (a report, a walkthrough, per-phase notes) is not debt,
give it in full, the rule is only against unrequested prose.

Pattern: `[code] → skipped: [X], add when [Y].`

### Intensity

| Level | What change |
|-------|------------|
| **lite** | Build what's asked, but name the lazier alternative in one line. User picks. |
| **full** | The ladder enforced. Stdlib and native first. Shortest diff, shortest explanation. Default. |
| **ultra** | YAGNI extremist. Deletion before addition. Ship the one-liner and challenge the rest of the requirement in the same breath. |

Example: "Add a cache for these API responses."
- lite: "Done, cache added. FYI: `functools.lru_cache` covers this in one line if you'd rather not own a cache class."
- full: "`@lru_cache(maxsize=1000)` on the fetch function. Skipped custom cache class, add when lru_cache measurably falls short."
- ultra: "No cache until a profiler says so. When it does: `@lru_cache`. A hand-rolled TTL cache class is a bug farm with a hit rate."

### When NOT to be lazy

Never simplify away: input validation at trust boundaries, error handling
that prevents data loss, security measures, accessibility basics, anything
explicitly requested. User insists on the full version → build it, no
re-arguing.

Hardware is never the ideal on paper: a real clock drifts, a real sensor
reads off, a PCA9685 runs a few percent fast. Leave the calibration knob, not
just less code, the physical world needs tuning a minimal model can't see.

Lazy code without its check is unfinished. Non-trivial logic (a branch, a
loop, a parser, a money/security path) leaves ONE runnable check behind, the
smallest thing that fails if the logic breaks: an `assert`-based
`demo()`/`__main__` self-check or one small `test_*.py`. No frameworks, no
fixtures, no per-function suites unless asked. Trivial one-liners need no
test, YAGNI applies to tests too.

### Boundaries

The shortest path to done is the right path.

## Component IDs
- All Dash component IDs must follow the pattern: `id-<component-type>-<name>` (e.g., `id-div-nav-links`, `id-location`).
- Only assign an `id` to a component if it is used in a **callback** (`Input`, `Output`, or `State`). HTML anchor targets are an exception.

## Agents
This project defines specialized agents that encode its conventions. **Claude Code**
reads them from `.claude/agents/<name>.md` and auto-delegates based on their
`description` (or you can ask for one by name). The **GitHub Copilot** equivalents live
in `.github/agents/<name>.agent.md` and are **symlinks** to the `.claude/agents/<name>.md`
sources — edit the source; the link needs no regeneration. Agents cannot invoke each other; the
main assistant chains them when a flow needs several in sequence:

- **`create-tool`** — architectural guidelines and module structure for adding a new tool (algorithm). For any modal UI it creates, it reads and applies `create-modal`'s conventions; for callback code, `write-callback`'s.
- **`backend-agent`** — backend task scheduler modifications and Redis TTL invariants.
- **`write-callback`** — detailed callback authoring patterns (guard clauses vs. intentional DOM writes, decorator syntax, naming).
- **`write-css`** — CSS formatting rules (banners, comments, indentation) for `enzyme_tk_app/app/assets/`.
- **`create-modal`** — layout/styling rules for new or modified tool modals.
- **`create-ag-grid`** — column definition rules and theme conventions for AG Grid results tables.
- **`write-tests`** — pytest patterns for new tests. After writing tests, run `verify`, then `review-tests` on the files you touched.
- **`review-tests`** — audits existing tests for duplicates, parametrize candidates, brittle strings, uncovered guard clauses, isolation issues, and weak assertions; complements `write-tests`.
- **`verify`** — runs `tox run -e format` then `tox`. Every code-generating agent (or code-generating task you do directly) invokes `verify` as its final step.
- **`check-coverage`** — runs the test suite with coverage and reports uncovered functions; read-only.
- **`architecture-diagram`** — explores the codebase and generates a Mermaid architecture diagram plus a print-friendly HTML file in `docs/`.
- **`cleanup`** — scans for dead code (unused Python functions, icon constants, CSS classes, static assets) after removing or replacing code.
- **`edit-dockerfile`** — cross-platform (`linux/amd64` + `linux/arm64`) rules for Dockerfile changes.
- **`check-updates`** — audits dependency updates in `requirements/`, producing a `requirements_v2/` and compatibility report.
- **`admin-page`** — security invariants and doc sync for the admin login flow, session tokens, and secret key management.
- **`sync-docs`** — the final step after any change: audits/updates every doc and instruction file (`AGENTS.md`, `README.md`, `docs/deployment/`, `docs/admin-login.md`) against the code, and flags when a new doc is warranted. (The Copilot agent copies are symlinks to the `.claude/agents/` sources, so they need no regeneration.)

### Keep agents & instructions in sync (mandatory)
- **Hand-edit only two things: this canonical `AGENTS.md` (shared conventions — `CLAUDE.md` imports it, Copilot reads it natively) and the agent sources in `.claude/agents/*.md`.** The `.github/agents/*.agent.md` Copilot copies are **symlinks** to those sources, so editing the source is all it takes — there is nothing to regenerate. When you *add* a new agent, create the matching symlink once: `ln -s ../../.claude/agents/<name>.md .github/agents/<name>.agent.md`.
- **Before finishing any change, check whether it invalidates an agent source (`.claude/agents/*.md`) or an instruction file (`AGENTS.md`, `docs/deployment/`, `README.md`).** If a rule, invariant, threshold, filename, or behavior you touched is described in one of those files, update it in the *same* change. A stale instruction is worse than none — it makes future work faithfully reproduce the behavior you just removed. (Example: renaming the `job-outputs` volume means `docs/deployment/index.md` and `backend-agent`'s volume line must change too.)
- **When the change is backend/scheduler/Redis, tests, CSS, a modal, a Dockerfile, deploy config, etc., route it through the matching agent above rather than editing directly** — that agent's file is where the conventions live, and consulting it is how you stay consistent.
- **End such a change by running the `sync-docs` agent** (the docs analogue of `verify`): it applies the doc edits and flags anything needing a human decision. (No Copilot-copy regeneration — those are symlinks.)

## Adding a New Tool (Algorithm)
- **All new tools MUST follow the architectural guidelines and module structure defined by the `create-tool` agent.**

## Backend Architecture
- **All backend task scheduler modifications and Redis TTL invariants MUST follow the `backend-agent` agent.**

## Callback Naming
- Callback functions names should start with a verb that describes the action they perform (e.g., `update`, `toggle`, `get`).
- Keep callbacks close to the component they modify.
- **For detailed callback authoring patterns** (guard clauses vs. intentional DOM writes, decorator syntax, naming), you MUST follow the `write-callback` agent.

## Page vs. Component Organization
- `enzyme_tk_app/app/pages/` modules are route entry points (each calls `dash.register_page()`) and own their `layout()` plus any page-specific helpers and callbacks.
- **Keep page-private helpers inline in the page module** and prefix them with a leading underscore (e.g., `_build_stat_card`, `_jobs_to_rows`, `_dashboard_layout` in `admin.py`; `_build_stats`, `_build_status_badge` in `my_tasks.py`). Do **not** move single-page helpers into `components/` just because there are many of them — locality is preferred.
- **Promote a helper to `enzyme_tk_app/app/components/` only when it is shared across ≥2 pages or tools.** Shared helper modules use a `*_helpers.py` name and public (non-underscore) functions — see `modal_helpers.py` (every tool modal) and `results_helpers.py` (every results page).
- Standalone, reusable UI widgets also live in `components/` (e.g., `navbar.py`, `footer.py`, `hero.py`, `tool_cards.py`). Page modules should compose these rather than re-implement them — see `home.py`.
- Rule of thumb: **used by one page → inline `_`-helper in that page; used by many → public helper in `components/`.**

## Styling (CSS vs Inline)
- **Use CSS** for styles that require pseudo-classes (`:hover`, `:focus`, `::after`), media queries, animations, or are shared across multiple components/pages.
- **Use inline styles** (Python dicts) for one-off styles scoped to a single component that don't need pseudo-classes — keep the style co-located with the element it applies to.
- **Inline Style Rules**:
  - Group related styles into constants at the top of the file (e.g., `STYLE_NAVBAR`, `STYLE_FOOTER`).
  - Use descriptive names for style constants that indicate where they are applied.
  - Keep inline styles in the component file. If styles are shared across similar components in the file, consider refactoring into a shared style constant.
- When converting a CSS class to inline, merge all cascading rules into one flat `STYLE_*` constant (e.g., `.badge` + `.badge-lib` → `STYLE_BADGE_LIB`).
- **CSS Files**: Live in `enzyme_tk_app/app/assets/` and are split by concern with numbered prefixes (e.g., `00-variables.css`, `05-cards.css`). Only add a new CSS class when the style truly needs CSS features or is reused across files.
- **For detailed CSS formatting rules (banners, comments, indentation), you MUST follow the `write-css` agent.**

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
- Add **docstrings** to all modules, functions, and classes. Use a single-line summary for simple functions to save tokens. Only use full Google-style docstrings (with Args/Returns) for complex logic or public APIs.
- Add **inline comments** for non-obvious logic.
- Use **double quotes** for all strings.
- Line length limit is **120** characters.
- Keep CSS class names in sync — don't add a `className` unless there is a matching rule in `styles.css` or it comes from an external library (e.g., FontAwesome).

## Formatting & Linting
- This project uses **ruff** for formatting and linting, configured in `pyproject.toml`.
- After making code changes, run the **`verify` agent** which executes `tox run -e format` then `tox`. All code-generating agents invoke `verify` automatically as their final step.
- `tox run -e format` auto-formats code, sorts imports, **and removes unused imports** (F401).
- All code must pass `tox run -e check-style` before being considered done (included in the `tox` default envlist).
- No need for permission to run tox commands — they are part of the development workflow.
- If an import is needed for its **side effect** (e.g., `from enzyme_tk_app.app.app import app` to satisfy `dash.register_page()`), add a `# noqa: F401` comment with a reason to prevent auto-removal.

## Writing Tests
- **All new tests MUST follow the architectural guidelines and pytest patterns defined by the `write-tests` agent.**
- After writing tests, the `write-tests` agent's workflow automatically runs `verify` and then `review-tests`.

## Deployment Documentation
- All deployment configuration is documented in `docs/deployment/`.
- **Any change that adds, removes, or modifies an environment variable, `config.py` setting, `docker-compose.yml` service, or Celery configuration MUST also update the corresponding deployment docs** — the `sync-docs` agent handles this.
