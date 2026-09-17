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
- Only assign an `id` to a component if it is used in a **callback** (`Input`, `Output`, or `State`). Three exceptions: HTML anchor targets; `dbc.Tooltip` targets — a tooltip is bound by `target=` and needs no callback (e.g. `id-icon-<slug>-databases-info` from `create_modal_databases_label()`, `id-data-warning-<slug>` in `components/data_warning.py`); and a **JavaScript mount target**, an empty div an `assets/*.js` file finds and fills — `id-div-<slug>-captcha` from `create_modal_footer()`, located by `assets/12-altcha-bridge.js`, which is what makes the id a real contract even though no Python reads it.

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
- **`create-ag-grid`** — column definition rules, theme conventions, and the shared CSV-export toolbar for AG Grid results tables.
- **`write-tests`** — pytest patterns for new tests. After writing tests, run `verify`, then `review-tests` on the files you touched.
- **`review-tests`** — audits existing tests for duplicates, parametrize candidates, brittle strings, uncovered guard clauses, isolation issues, and weak assertions; complements `write-tests`.
- **`verify`** — runs `tox run -e format` then `tox`. Every code-generating agent (or code-generating task you do directly) invokes `verify` as its final step.
- **`verify-ui`** *(skill, not an agent — it runs in your own context so you can see the screenshots)* — drives the running app in the Browser pane to prove a UI change actually works: rebuilding the Docker image, submitting a real job, clicking the thing, measuring the result. Invoke it with the `Skill` tool.
- **`check-admin`** *(skill, same reason)* — the same idea aimed at `/admin`, which `verify-ui` never reaches because it is behind a token: real login, session-cookie replay, stat cards, both grids, Cancel Selected, both Danger Zone dialogs, and idle expiry, with several simulated users submitting real jobs via its `simulate_users.py`. It runs a **side-car** `web-check` container on port 8051 (`docker-compose.check-admin.yml`) that shares the running stack's Redis, so the app on 8050 is never stopped or reconfigured and the dashboard still shows real data. It edits nothing in the repo and never confirms a destructive action — an interrupted run cannot leave your app on a throwaway token. Keep that contract if you touch the compose file.
- **`check-coverage`** — runs the test suite with coverage and reports uncovered functions; read-only.
- **`architecture-diagram`** — explores the codebase and generates a Mermaid architecture diagram plus a print-friendly HTML file in `docs/`.
- **`cleanup`** — scans for dead code (unused Python functions, icon constants, CSS classes, static assets) after removing or replacing code.
- **`edit-dockerfile`** — cross-platform (`linux/amd64` + `linux/arm64`) rules for Dockerfile changes.
- **`check-updates`** — audits dependency updates in `requirements/`, producing a `requirements_v2/` and compatibility report.
- **`admin-page`** — security invariants and doc sync for the admin login flow, session tokens, and secret key management.
- **`sync-docs`** — the final step after any change: audits/updates every doc and instruction file (`AGENTS.md`, `README.md`, `docs/deployment-guide.md`, `docs/admin-login.md`) against the code, and flags when a new doc is warranted. (The Copilot agent copies are symlinks to the `.claude/agents/` sources, so they need no regeneration.)

### Keep agents & instructions in sync (mandatory)
- **Hand-edit only three things: this canonical `AGENTS.md` (shared conventions — `CLAUDE.md` imports it, Copilot reads it natively), the agent sources in `.claude/agents/*.md`, and the skill sources in `.claude/skills/*/SKILL.md`.** The `.github/agents/*.agent.md` Copilot copies are **symlinks** to the agent sources, so editing the source is all it takes — there is nothing to regenerate. When you *add* a new agent, create the matching symlink once: `ln -s ../../.claude/agents/<name>.md .github/agents/<name>.agent.md`. A **skill** needs no symlink — Copilot has no skills — but it *is* shared: `.gitignore` un-ignores `/.claude/skills/`, so `verify-ui` and `check-admin` travel with the repo and a stale one misleads exactly like a stale agent.
- **Before finishing any change, check whether it invalidates an agent source (`.claude/agents/*.md`) or an instruction file (`AGENTS.md`, `docs/deployment-guide.md`, `README.md`).** If a rule, invariant, threshold, filename, or behavior you touched is described in one of those files, update it in the *same* change. A stale instruction is worse than none — it makes future work faithfully reproduce the behavior you just removed. (Example: renaming the `job-outputs` volume means `docs/deployment-guide.md` and `backend-agent`'s volume line must change too.)
- **When the change is backend/scheduler/Redis, tests, CSS, a modal, a Dockerfile, deploy config, etc., route it through the matching agent above rather than editing directly** — that agent's file is where the conventions live, and consulting it is how you stay consistent.
- **End such a change by running the `sync-docs` agent** (the docs analogue of `verify`): it applies the doc edits and flags anything needing a human decision. (No Copilot-copy regeneration — those are symlinks.)

## Adding a New Tool (Algorithm)
- **All new tools MUST follow the architectural guidelines and module structure defined by the `create-tool` agent.**
- **Database-backed tools share one contract** (`create-tool` §3b): a `multi=True` "Databases" dropdown with every option pre-selected, its label column from `create_modal_databases_label(slug, contents)` so the label carries an info icon whose tooltip names in one sentence what those databases hold, `validate_db_names(names, options)` from `utils/data_loading.py` as the only name validator — it checks **membership in the tool's own `get_*_database_options()` list**, not a regex or a suffix — `params["databases"]` as a `list[str]`, all selections merged into one reference set tagged with a `database` column, and an unreadable database skipped and named in a **Databases Skipped** stat card — failing only when *every* selection is unreadable.
- **A modal's example picker prefills the Task Name** (`create-modal` §7). Each example dict carries a `task_name` next to its `label`/`value`, and the tool's `populate_example_*` callback returns it **verbatim** as its **last** output, into `f"id-input-{TOOL_DEF['slug']}-task-name"`. Task Name is the one field that blocks submit, so an example that leaves it blank is not runnable in one click. An example may prefill **more** than its input field — optional per-example keys, one extra `Output` each — and Task Name is last of however many there are, because the shared test reads `populate(...)[-1]`; the rules for a prefilled field (its value must be one the control actually offers, `allow_duplicate` when another callback owns the property, and clearing with `[]` rather than `no_update`) are in `create-modal` §7. Which fields a given tool prefills is that tool's business and belongs in its own `_get_example_*()` docstring. **Never prepend the tool slug** — the My Tasks table already has a Tool column beside Task Name, and the Task Name column has no `max-width`, so a long name widens it and squeezes the other eight. Keep `task_name` short and kebab-case, with identifiers in their own casing (`DEHP-MEHP`, `A0A009IHW8`); a selection overwrites a name the user already typed, like every other example-filled field. `test_every_example_prefills_a_task_name` in `tests/test_tools.py` walks the live dropdowns and enforces a non-blank name for every tool.
- **Every tool's `submit_*` callback ends with the per-session job cap.** `validate_active_job_limit(g.session_id)` from `utils/submission_limits.py` is the **last** guard, after every field validator and after the captcha below, immediately before `get_task_scheduler()`, so a malformed submit still shows its own field error first. It returns **a message or `None`**, like `validate_db_names` and `validate_top_n`, and is a no-op unless the deployment set `APP_IN_PRODUCTION_MODE` (default off, so a downloaded checkout runs locally unlimited). A tool that skips it is an uncapped submission endpoint and nothing else in the app would notice — `test_every_tool_enforces_the_active_job_limit` in `tests/test_tools.py` walks the live registry and fails any tool whose `callbacks.py` does not import it. The cap counts PENDING + STARTED via `TaskScheduler.count_active_jobs()`, never `list_jobs()`, which would deserialise every job's params — including a multi-megabyte base64 structure upload — on the *rejected* path. Its deliberate limits (check-then-act overshoot, PENDING never ageing out) are named in the module docstring with their upgrade paths; the cookie-rotation bypass it used to name is now **priced rather than closed** by the captcha below — dropping the cookie still buys fresh slots, it just costs a fresh proof of work.
- **Every tool's `submit_*` callback verifies the submission captcha, immediately before the job cap.** `validate_captcha(captcha_payload, g.session_id)` from `utils/captcha.py` is the guard, reading a new **last** `State` on `f"id-store-{TOOL_DEF['slug']}-captcha"` — the `dcc.Store` `create_modal_footer()` renders for every tool — into a new **last** parameter. It sits after every field validator (so a typo still shows its own error rather than "tick the box") and **before** `validate_active_job_limit` (it costs no Redis round trip, so an unverified caller never gets the cap's O(N) read for free). Like `validate_db_names` and `validate_active_job_limit` it returns **a message or `None`** and never raises, and it is a no-op unless the deployment set `APP_IN_PRODUCTION_MODE`. The proof is an ALTCHA PBKDF2/SHA-256 challenge minted per session and **signed over the session id**, so a solved payload cannot be retargeted at another session — that binding is the whole feature, since it is what makes discarding the session cookie cost a solve rather than nothing. It is deliberately the twin of `utils/submission_limits.py`: policy in constants, not environment variables, and **no new environment variable at all** — the HMAC key is derived from `ETK_SECRET_KEY` (`blake2b(person=b"etk-altcha")`), which is why `ETK_SECRET_KEY` is now required whenever production mode is on and `app.py` refuses to start without it. A tool that skips the guard is an unverified submission endpoint: `test_every_tool_verifies_the_captcha` and `test_every_modal_carries_a_captcha_store` in `tests/test_tools.py` walk the live registry and modals and fail the build, and the behavioural tests in `test_tools_timer.py` pin the ordering the import walk cannot see. Its known limits (a payload replayable inside its 300 s window by the session it was issued to, verification costing one PBKDF2 derivation, no cookie meaning no captcha) are named in the module docstring with their upgrade paths.
- **A user-typed structure is validated in three places, through `utils/smiles_validation.py`.** `validate_reaction_smiles(smiles)` (reactions) and `validate_smiles(smiles)` (one molecule) return **a message or `None`**, like `validate_db_names` and `validate_top_n`. The form callback gates the Run button and marks the field (`dbc.Textarea(invalid=…, debounce=300)` + a `dbc.FormFeedback` sibling — `create-modal` §6, `write-callback` §4); the submit callback repeats the check because the client gate is bypassable; `run()` repeats it again because a replayed job never touches the modal. A **blank** field disables Run without turning red — an empty form is not yet a mistake. **`debounce` is a number of milliseconds, never `True`**: validating every keystroke puts several round-trips in flight at once and the field ends up showing whichever verdict landed last, so a corrected structure stays marked invalid. A rejection carries **RDKit's own diagnosis** (`unclosed ring`), captured with `rdBase.CaptureErrorLog` — never an echo of the string the user is already looking at, which is exactly how a lost ring-closure digit reads as no mistake at all. The validators are deliberately stricter than the parsers downstream: `enzymetk`'s `ReactionDist` reads the query as SMARTS (no `useSmiles=True`), so without this `">>"`, `"CCO>>"` and hypervalent atoms all finish as a **successful job full of meaningless scores**. `>>` is the app-wide reaction convention — the three-part `reactants>agents>products` form is rejected, matching every modal placeholder, every shipped example, and `reaction_to_svg_data_uri`'s contract. `test_every_smiles_field_is_validated` in `tests/test_tools.py` walks the live modals and fails any tool with a SMILES field whose `callbacks.py` imports no validator.
- **A tool-specific invariant belongs in that tool's own module docstring, not in this file.** `AGENTS.md` carries contracts that bind *every* tool; a rule about how one algorithm encodes its input belongs next to the code enforcing it, where a reader who opens `compute.py` cannot miss it — the same locality rule as "used by one page → inline `_`-helper; used by many → `components/`" below. Tools come and go, and a retired tool's rule left here reads as a live constraint on new ones. Concretely: Func-E's batch-softmax coupling, its no-download policy, and how it reduces a dot-joined side all live in `tools/funce/compute.py`'s docstring; what belongs here is only the general form — a tool that encodes user structures documents its encoding constraints where it encodes them.
- **A tool's `run()` return value must be JSON-serialisable in its entirety.** The worker `json.dumps` it with no `default=` before offloading it to the shared volume, so one numpy scalar or ndarray left in a `dataframe` column records the finished job as FAILURE at persist time — after the compute already succeeded. Convert or drop those columns (`funce/compute.py`'s `DROPPED_COLS`) and pin it with a `json.dumps(result)` assertion in the tool's test.
- **`data/sequences/` files must declare their columns** (`create-tool` §3b.9): a file there is a sequence database only when its extension is one of `SEQUENCE_DB_SUFFIXES` (`.csv`, `.tsv`, `.csv.gz`, `.tsv.gz`) **and** its header carries every one of `REQUIRED_SEQUENCE_COLUMNS` (`Entry`, `Sequence`, `EC number`). Every other column is metadata the app never enumerates — it rides through the search into the results grid untouched. **`Cofactor` is the one exception:** still optional (a file without it is a database), but when present its `Name=` values are enumerated by `get_cofactors()` so a tool can offer them as a filter, and the column is rewritten to them before it reaches a grid. `extract_cofactor_names()` in `utils/data_loading.py` is the single parser for both — a tool that filters on names other than the ones its dropdown offered returns nothing, silently. A non-compliant file is not offered in the dropdown at all; `scan_sequence_databases()` names it and its missing columns for the tool's home-page "Missing data" tooltip. This contract is `data/sequences/` only — `reactions/`, `sequence_embeddings/`, and `foldseek_db/` are unchanged.
- **A shared data directory is named for its data, not for a tool that reads it.** `data/sequence_embeddings/` holds protein embedding pickles; it is not `funce_db/` just because Func-E is today's only reader, and its option builder is `get_sequence_embedding_database_options()`. `data/unimol_weights/` is the same case for model weights — it holds the UniMol checkpoint Func-E's reaction encoder loads (`UNIMOL_WEIGHTS_DIR`), so it is named for the model, not `funce_unimol/`. A directory *is* named for a tool only when the tool genuinely owns it — `foldseek_db/` and `foldseek_models/` (whose names are foldseek's own identifiers) and `funce_models/` (Func-E's EC checkpoints).
- **The repo ships a `*_demo_set` per reference directory, and every shipped tool example must return hits against it.** `data/sequences/enzymes_demo_set.tsv` (100 rows), `data/reactions/enzymemap_demo_set.csv` (110 rows), `data/sequence_embeddings/enzymes_demo_set.pkl` and `data/foldseek_db/enzymes_demo_set/` are the only data files `.gitignore` un-ignores besides `structures/`, and they exist so `git clone` plus `docker compose up` is runnable with no download. Three rules bind them. **They are strict row-subsets of the full file, copied verbatim** — the header line plus selected data lines, byte for byte, never round-tripped through pandas and never hand-edited; a sample containing a value that is not in the master file is a fabricated reference database. **The stem is shared**, because `build_enzyme_db.py` names both artifacts it builds after its `INPUT_FILE`, so the pickle and the foldseek directory follow the TSV's name for free — pick a new stem and all three move together. **Adding or changing a tool example means re-checking the demo set**: an example that names an accession, writes an EC or cofactor filter value verbatim, or ships a query structure needs that row present, and `test_demo_data.py` walks the live examples and fails the build when one is not — which is how the two EC-filter examples that silently returned nothing were caught. Sizing is measured, not guessed: the 110 reaction rows are the union of the exact top-10 hits for all 11 chemistry examples, so the demo set reproduces the full 62,896-row file's answer for every one of them.
- **`scripts/db_build/download_data.py`'s `report()` mirrors the app's own data checks — a change to one is a change to the other, in the same commit.** That script ships in its own image and cannot import the app package, so its checks are deliberate hand-copies of `tools/funce/check_data.py`, `tools/sequence_structure_similarity/check_data.py`, and the `SEQUENCE_DB_SUFFIXES` / `REQUIRED_SEQUENCE_COLUMNS` contract in `utils/data_loading.py`. Add a data directory, rename one, move a checkpoint, or tighten a column contract and `report()` is wrong the moment you land it: it prints `OK` for data the app will refuse to offer (or `MISSING` for data that is fine), and a pre-flight check that disagrees with the app is worse than no pre-flight check at all. Its tests live beside it in `scripts/db_build/` — `scripts/` is outside the app package, so they are not part of the `enzyme_tk_app/app/tests/` suite. The same applies to its **tiers**: `MINIMAL` is defined as *what a clone cannot ship*, so shipping a new demo set that satisfies a tool means dropping the corresponding download out of `MINIMAL` — `pdb`/`afdb` are `--full` only precisely because `foldseek_db/enzymes_demo_set/` already answers for them, and `reactions` joined them for the same reason once `reactions/enzymemap_demo_set.csv` shipped. The two units that fetch the project's **own** published data go through `fetch_dataset_file_from_hugging_face()` against `ETK_HUGGING_FACE_DATASET_REPO`, named once so another published file is a one-line unit rather than another copy of the `hf_hub_download` call.
- **A database is named on screen exactly as it is named in `data/`, extension included** — `Funce_pairs.pkl` shows as `Funce_pairs.pkl`, the FoldSeek folder `AFDB_SWISSPROT` as `AFDB_SWISSPROT` (a directory, so no extension to show). Never prettify (no `.replace("_", " ").title()`) and never strip the suffix (no `.stem`); this holds for dropdown labels, the `database` column, stat cards, and the input-parameters row alike, so the app and the disk always agree. The canonical statement, the reason the option *value* keeps its extension, and the one FoldSeek exception are in the `enzyme_tk_app/app/utils/data_loading.py` module docstring and `create-tool` §3c.

## Backend Architecture
- **All backend task scheduler modifications and Redis TTL invariants MUST follow the `backend-agent` agent.**

## Callback Naming
- Callback functions names should start with a verb that describes the action they perform (e.g., `update`, `toggle`, `get`).
- Keep callbacks close to the component they modify.
- **For detailed callback authoring patterns** (guard clauses vs. intentional DOM writes, decorator syntax, naming), you MUST follow the `write-callback` agent.

## Page vs. Component Organization
- `enzyme_tk_app/app/pages/` modules are route entry points (each calls `dash.register_page()`) and own their `layout()` plus any page-specific helpers and callbacks.
- **Keep page-private helpers inline in the page module** and prefix them with a leading underscore (e.g., `_build_admin_page_stats`, `_jobs_to_rows`, `_dashboard_layout` in `admin.py`; `_build_my_tasks_page_stats`, `_build_job_row` in `my_tasks.py`). Do **not** move single-page helpers into `components/` just because there are many of them — locality is preferred.
- **Name a page-private helper for its page when a sibling page has the same job.** `admin.py`'s `_build_admin_page_stats` and `my_tasks.py`'s `_build_my_tasks_page_stats` both build a `jobs-stats-row`, but count different things over different scopes; the page-qualified names keep them from reading as one shared helper. Only the leaf they share — `build_stat_card` in `components/results_helpers.py` — is generic.
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

## Shared UI Components — Results Table & CSV Export
- **`build_ag_grid(column_defs, df_payload)` in `components/results_helpers.py` returns an `html.Div`** — the shared CSV-export toolbar plus the `dag.AgGrid`, not a bare grid. The signature is unchanged, so every tool's `results.py` keeps calling it exactly as before; just don't type or assert the result as `dag.AgGrid`.
- **Every results table gets the download control for free — never add a per-tool export button, `csvExportParams`, or `dcc.Download`.** Change `build_ag_grid()` so all tools move together.
- **The columns share out any width a short table leaves over; give each one a `width` and leave `minWidth` and `flex` alone.** `build_ag_grid()` copies every `width` into `minWidth` and sets `columnSize="responsiveSizeToFit"`, so a short table ends flush with the page instead of against a grey gutter, while a table wider than the page is already at its floor, cannot shrink, and keeps scrolling unchanged. Read `width` as "at least this wide". How wide a table ends up is decided by the *data*: a tool declares every column it might get and `build_ag_grid()` drops the defs the payload has no field for, so Reaction Similarity declares 32 and renders the 7 `ReactionDist` returns (1340px). **`flex` is not an alternative** — dash-ag-grid 35.3.0 records it in the column state and never applies it. See the `create-ag-grid` agent (§2.1).
- **Only one results grid may exist per page.** The grid id (`GRID_ID`), download button, and scope radios are static ids because `my_tasks_view_results` renders exactly one tool's `results_layout()`. Need two grids on a page? Give `build_ag_grid()` an `id` argument and move the `download_results_csv` callback to `MATCH` — do not duplicate the static ids.
- **SVG columns are excluded from the CSV.** `_csv_export_params()` drops any column whose def has `cellRenderer == "SvgRenderer"` (each cell is a ~20 KB base64 data URI); the SMILES it was drawn from is exported instead. A new image renderer under a different name must widen that check in the same change — see the `create-ag-grid` agent (§1.1, §2.2, §6).
- **The download filename reads the job id off the page.** `my_tasks_view_results._build_job_info_header()` puts `id=JOB_ID_SPAN_ID` (imported from `results_helpers`) on the task-id span whose `title` is the bare job id; the export callback takes it as `State`. This page↔component contract is guarded by a test in `test_my_tasks.py` — keep the `title` if you touch that header.
- **Clicking an SVG cell opens a compare lightbox — the job's query structure next to the clicked result.** `_openSvgOverlay(src, smiles)` in `assets/dashAgGridComponentFunctions.js` finds the query image with `querySelector("img." + QUERY_PREVIEW_CLASS)` and reads its SMILES off `QUERY_SMILES_ATTR`; both constants live in `results_helpers.py` and are written by `_render_smiles_preview()`, so renaming either means editing the JS in the same change (`test_query_preview_anchors_match_the_compare_lightbox` in `test_smiles_rendering.py` pins both ends, exactly like the `JOB_ID_SPAN_ID` contract above). Caption the result panel by setting `"cellRendererParams": {"smilesField": <the row's SMILES column>}` on the SVG column def — no other wiring is needed, and a page with no query image degrades to the single-image overlay. See the `create-ag-grid` agent (§2.2).
- **The panels' orientation comes from the structure's shape, not the viewport.** `_stackWideImages()` adds `.svg-compare-stacked` (`09-ag-grid.css`) when a panel image's `naturalWidth / naturalHeight` exceeds `_STACK_ASPECT_RATIO = 2.5`, so a reaction stacks query-over-result at ~88vw each while a molecule stays side by side; a `data:` URI has no `naturalWidth` until it decodes, so the measurement re-runs on each image's `load`. The constant sits in the gap between the only two canvases the app draws — molecules 500x300 (1.67) and the narrowest real reaction 750x200 (3.75, `max(400, n_templates * 250)` wide) — **so it is only valid while reactions are drawn 200 px high**; draw them taller and a one-reactant/one-product reaction quietly stops stacking. Change a canvas size and re-measure the constant in the same change: `test_stack_threshold_separates_reactions_from_molecules` in `test_smiles_rendering.py` reads it out of the JS and asserts `molecule < threshold < reaction`. The `@media (max-width: 768px)` block still owns the narrow-viewport case — the JS never stacks a molecule.

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
- **If the change is visible in a browser** — anything under `pages/`, `components/`, `tools/*/modal.py`, `tools/*/results.py`, `assets/*.css`, or `assets/*.js` (the AG Grid cell renderers draw real UI) — also invoke the **`verify-ui` skill** and confirm it in the running app. `verify` proves the code is clean; only `verify-ui` proves the button works. Never ask the user to check by hand.
- **If the change touches the admin dashboard or session identity** — `pages/admin.py`, `backend/session.py`, the `ADMIN_*` config, or the cookie settings in `app.py` — invoke the **`check-admin` skill** instead of (not as well as) `verify-ui`: it is the only check that gets past the token gate. It is safe to run against a live local stack.
- `tox run -e format` auto-formats code, sorts imports, **and removes unused imports** (F401).
- All code must pass `tox run -e check-style` before being considered done (included in the `tox` default envlist).
- **CPU torch has two enforcement points — the `Dockerfile` and `tox.ini` — and they move together.** `enzymetk` and `unimol_tools` both leave `torch` unpinned, so a plain install on linux resolves PyPI's CUDA build (~2.8 GB of `nvidia-*`/`triton` wheels, ~5.5 GB unpacked). The image keeps it out by install *ordering* (the CPU wheel first — `edit-dockerfile`'s ordering exception, with `TORCH_INDEX_URL` as the GPU opt-in); `tox.ini`'s `[testenv:test]` keeps it out of CI by pointing `PIP_EXTRA_INDEX_URL` at the PyTorch CPU channel on Linux, where that stack overruns a GitHub runner's ~14 GB disk. Change how torch or `requirements/prd.txt` resolves and check **both** — neither mechanism covers the other. The CI `test` job runs `fail-fast: false` so a linux-only break cannot hide behind a green macOS leg.
- No need for permission to run tox commands — they are part of the development workflow.
- If an import is needed for its **side effect** (e.g., `from enzyme_tk_app.app.app import app` to satisfy `dash.register_page()`), add a `# noqa: F401` comment with a reason to prevent auto-removal.
- **Python code blocks in markdown are formatted too.** ruff formats ` ```python `, ` ```py `, and ` ```pycon ` blocks inside `.md` files. This is **active** — `requirements/test.txt` pins ruff 0.16.5, and markdown formatting is stable from 0.16 onward (it was preview-only through 0.15.x). Keep every snippet a **valid statement** — a bare fragment like `{"field": "x"},` is parsed as a tuple and rewritten to `({"field": "x"},)`, so give it its real context (`column_defs = [...]`, `dag.AgGrid(...)`) instead. A **magic trailing comma** keeps a block expanded, and `<!-- fmt: off -->` / `<!-- fmt: on -->` skips one entirely. Markdown is only *formatted*, never linted — `ruff check` still ignores it. `docs/` is excluded via `[tool.ruff] exclude`; `.claude/agents/` and `.github/` are not.

## Writing Tests
- **All new tests MUST follow the architectural guidelines and pytest patterns defined by the `write-tests` agent.**
- After writing tests, the `write-tests` agent's workflow automatically runs `verify` and then `review-tests`.

## Deployment Documentation
- Deployment configuration is documented in **`docs/deployment-guide.md`** (architecture, admin secrets, env vars, production mode, TLS, shared volume, the `enzymetk` refetch and GPU build args, Azure). The `README.md` is for a user who clones the repo and runs it locally — it keeps only the Quickstart and the **Data Directories** table, and routes everything operator-facing to the deployment guide. Environment variables are read in **five** places — `backend/config.py` (backend runtime, `web` + `worker`, plus the three `ETK_ADMIN_*` values that only matter on `web`), `backend/celery_app.py` (`DEFAULT_MAX_DURATION`, `HARD_TIMEOUT_GRACE_SECONDS`), `paths.py` (`ETK_DATA_DIR`), `utils/submission_limits.py` and `utils/captcha.py` (each its **own** binding of `APP_IN_PRODUCTION_MODE`, `web` only — two module-level reads of one variable, so patching one in a test does nothing to the other) — so a new variable is not necessarily a `config.py` edit. The submission cap, and the captcha's cost and TTL, are **constants** in those modules, not variables: they are policy the app owns, so changing one is a code edit and a review, never an operator's env setting. `APP_IN_PRODUCTION_MODE` now gates **two** features, not one — the per-session job cap and the submission captcha — and because the captcha derives its signing key from `ETK_SECRET_KEY`, that secret is **required** whenever production mode is on (`app.py` raises at startup otherwise, where it previously only required it alongside `ETK_ADMIN_TOKEN`).
- **Any change that adds, removes, or modifies an environment variable, `config.py`, `submission_limits.py` or `captcha.py` setting, `docker-compose.yml` service, `main.bicep` container env, data directory, Docker build argument (`TORCH_INDEX_URL`), `.dockerignore` entry, or Celery configuration MUST also update the corresponding deployment docs** (and `scripts/template.env`, which is what an operator actually copies) — the `sync-docs` agent handles this. A build arg is operator-facing even though nothing reads it at run time: an operator who does not know it exists cannot get the behaviour it gates.
- **Secrets live in the process environment, never in a file inside the image.** There is no `python-dotenv` anywhere in the repo: every setting is an `os.environ.get` in the four files above, and `docker-compose.yml` does its `${VAR}` substitution on the **host**, so `.env` is host-only by design. `.dockerignore` excludes `.env` and `.env.*` from the build context for that reason — the `Dockerfile`'s closing `COPY . .` would otherwise bake a live deployment's `ETK_ADMIN_TOKEN` and `ETK_SECRET_KEY` into a published layer at `/app/.env`, which is exactly what it did before that entry existed. CI builds from a clean checkout and never saw it, so a green pipeline is no evidence here. **Adding or widening a `COPY` means reading `.dockerignore` in the same change** (route it through `edit-dockerfile`), and a secret never travels as an `ARG` or `ENV` — both are recorded in the image history. The operator-facing version is in `docs/deployment-guide.md` → *Admin Secrets*.
