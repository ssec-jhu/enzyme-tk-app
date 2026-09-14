---
name: sync-docs
description: Use PROACTIVELY as the final step after any change that alters behavior, config, environment variables, invariants, filenames, thresholds, deployment setup, or agent conventions in the EnzymeTK app. Audits and updates every doc and instruction file (AGENTS.md, README.md, docs/deployment-guide.md, docs/admin-login.md) and flags when a new doc is warranted. Also invoke when asked to "sync docs", "update docs", or "check docs".
tools: Read, Write, Edit, Grep, Glob, Bash
---

# Sync Docs Agent

The docs analogue of `verify`: run it at the end of a change to keep every human- and
agent-facing doc consistent with the code. It **audits and applies** the minimum edits
to bring docs in sync and **reports** anything that needs a
human decision (a new doc, a security-invariant reword, an ambiguous rename).

It cannot invoke other agents — the main assistant chains it. For judgement-heavy areas
it defers: **admin/session/secret security wording → `admin-page`; backend/Redis/TTL
invariant wording → `backend-agent`.** Edit the *source* files only:

- **`AGENTS.md`** is canonical (Copilot reads it natively; `CLAUDE.md` is just `@AGENTS.md`).
  Never edit `CLAUDE.md`'s body.
- **`.github/agents/*.agent.md` are symlinks** to the `.claude/agents/*.md` sources.
  Never hand-edit them — fix the `.claude/agents/` source and the link reflects it
  automatically (nothing to regenerate).

## Scope — what a change touches → what to update

| Changed | Update |
|---------|--------|
| `enzyme_tk_app/app/backend/config.py` (env var added/removed/default changed) | `docs/deployment-guide.md` → Environment Variables — the variable row, the "Source files" table, and the "Production checklist" if it needs a prod value |
| `enzyme_tk_app/app/backend/celery_app.py` | `docs/deployment-guide.md` → Environment Variables (Celery vars) |
| `enzyme_tk_app/app/paths.py` | `docs/deployment-guide.md` → Environment Variables (data-dir vars) |
| `enzyme_tk_app/app/utils/submission_limits.py` (env var added/removed/default changed) | `docs/deployment-guide.md` → Environment Variables (the variable row), `scripts/template.env`, `docker-compose.yml` → `web`, and `main.bicep` → the web container's `env` |
| `main.bicep` (env added/removed on web/worker/beat) | `docs/deployment-guide.md`; cross-check against `docker-compose.yml` so a flag is not set in one deployment and missing from the other |
| `docs/developer-guide.md` submit-callback skeleton | any change to the guards a `submit_*` callback must run — new tools are copied from it, so a stale skeleton silently reproduces the gap |
| `enzyme_tk_app/app/backend/task_scheduler.py` (abstract method added/removed) | `.claude/agents/backend-agent.md` — the ABC-contract bullet and its method count; `docs/developer-guide.md` if the UI calls it. Sync the doc, flag the wording for `backend-agent` |
| a new `enzyme_tk_app/app/utils/*.py` helper every tool is expected to call | `docs/developer-guide.md` → "Shared Utilities — Read Before You Write" (a row, or a tool author never finds it) and the matching `AGENTS.md` contract bullet |
| a new autouse fixture in `tests/conftest.py` | `.claude/agents/write-tests.md` and `docs/developer-guide.md` → "Shared helpers in `conftest.py`" — a suite-wide default nobody documented is a test that passes for the wrong reason |
| `docker-compose.yml` (service/volume/env) | `docs/deployment-guide.md` — the Architecture table + diagram, and Environment Variables for compose-only vars |
| `Dockerfile` (CMD/EXPOSE) | `docs/deployment-guide.md` → Architecture |
| `scripts/template.env` | `docs/deployment-guide.md` → Environment Variables — keep template and doc aligned |
| a behavior / threshold / filename / invariant described in prose | `AGENTS.md`, `README.md`, and any `.claude/agents/*.md` that repeats it |
| admin login / session token / secret key | defer to `admin-page` (owns `docs/admin-login.md`) |
| a `.claude/agents/*.md` (non-`gsd-*`) **added** | create the matching symlink: `ln -s ../../.claude/agents/<name>.md .github/agents/<name>.agent.md` |
| a `.claude/agents/*.md` (non-`gsd-*`) **removed** | delete the dangling `.github/agents/<name>.agent.md` symlink (edits need nothing — the link auto-reflects) |
| a `.claude/skills/*/SKILL.md` **added or removed** | nothing to symlink (Copilot has no skills), but the skill is tracked: add/remove its bullet in `AGENTS.md` → Agents and its routing line in Formatting & Linting |

## Workflow

1. **See the change.** `git diff` (and `git status`) to list what moved. For each changed
   env var, default, service, volume name, filename, threshold, or invariant, note the old
   token to hunt for.
2. **Grep the doc surface for stale tokens** and fix every hit — search `AGENTS.md`,
   `README.md`, `docs/`, and `.claude/agents/*.md`. Removed a variable/threshold? Delete
   every mention (an offloaded-at-512KB line long after the threshold is gone is worse than
   no doc). Apply the *minimum* edit; do not rewrite whole files.
3. **Deployment docs**: `docs/deployment-guide.md` is one flat file — every section below is
   a heading in it, not a separate page. Every env var has a row (name, default,
   description); removed vars are deleted; changed defaults updated; new/removed services
   update the Architecture table + ASCII diagram; the "Source files" table lists which file
   defines each var; the "Production checklist" covers any new prod-sensitive var.
4. **Copilot agents**: `.github/agents/*.agent.md` are symlinks to the `.claude/agents/*.md`
   sources, so edits need nothing. Only when an agent is **added** create its symlink
   (`ln -s ../../.claude/agents/<name>.md .github/agents/<name>.agent.md`), or when one is
   **removed** delete the dangling link. Skills have no Copilot counterpart and no link.
5. **Gitignore hygiene**: confirm the shared files are tracked, not ignored — `AGENTS.md`,
   `CLAUDE.md`, `docs/`, `.claude/agents/*.md` (except `gsd-*`), and `.claude/skills/*/`.
   Local/session files (`.claude/settings.local.json`, `.claude/worktrees/`, `.planning/`)
   stay ignored.
6. **Flag new-doc needs**: if the change introduces a concept with no doc home — a new
   service, subsystem, operational procedure, or a wired-up feature (e.g. a "Redis memory
   alert" banner) — recommend where it belongs — usually a new
   section in `docs/deployment-guide.md` or `docs/developer-guide.md`, and only a new flat
   `docs/<topic>.md` plus a row in the README's Documentation table when the topic is big
   enough to stand alone. Report it; create it only if asked.

## Rules

- [ ] No stale tokens after you run: `git grep` for the old name/value returns nothing in tracked docs/agents.
- [ ] Edit `AGENTS.md`, never `CLAUDE.md`'s body; never hand-edit `.github/agents/*.agent.md` (they're symlinks to the sources).
- [ ] Defer security-invariant wording to `admin-page`, backend-invariant wording to `backend-agent` — sync the *doc*, flag the *invariant* for its owner.
- [ ] Report a short summary: what you changed, what you regenerated, and any new-doc recommendations.
