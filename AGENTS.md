# Agent Instructions (Router)

This file acts as a central router for on-demand workflows and specialized agent rules. 
These sub-agents do **not** run automatically unless their trigger condition is explicitly met — ask for them by name when needed!

---

## Verify Agent
**Trigger:** Ask the agent to "verify", "run verification", or "run the verify agent". Also invoked automatically at the end of every code-generating agent.
**Action:** The agent must execute the format-and-test workflow defined in [`.github/agents/verify.md`](.github/agents/verify.md). Core steps (`tox run -e format` + `tox`) always run. An optional Docker Compose smoke test runs when the user says "verify with docker" or "full verify".

## Modal Creation Agent
**Trigger:** When asked to generate, design, restyle, or fundamentally modify frontend UI modals.
**Action:** The agent MUST strictly follow the architectural layout constraints and CSS variable styling guidelines defined in [`.github/agents/create-modal.md`](.github/agents/create-modal.md).

## Test Coverage Agent
**Trigger:** Ask the agent to "check coverage", "run tests with coverage", or "find uncovered lines".
**Action:** The agent must execute the test suite and coverage reporting workflow defined in [`.github/agents/check-coverage.md`](.github/agents/check-coverage.md).

## Architecture Diagram Agent
**Trigger:** When asked to "generate a diagram", "show architecture", or "diagram the [scope]".
**Action:** The agent must explore the codebase and generate a Mermaid diagram following the guidelines in [`.github/agents/architecture-diagram.md`](.github/agents/architecture-diagram.md).

## Dead Code Cleanup Agent
**Trigger:** After completing any task that removes or replaces code (e.g., deleting a tool, renaming a slug, removing a component, refactoring a module). Ask the agent to "run cleanup", "check for dead code", or "find unused exports".
**Action:** The agent must scan for orphaned symbols — unused Python functions, icon constants, CSS classes, and static assets — following the workflow in [`.github/agents/cleanup.md`](.github/agents/cleanup.md).

## Write-Tests Agent
**Trigger:** When asked to "write tests", "create a test", or "add test coverage" for a module or feature.
**Action:** The agent must follow the strictly defined pytest patterns and architectural guidelines defined in [`.github/agents/write-tests.md`](.github/agents/write-tests.md).

## Review-Tests Agent
**Trigger:** When asked to "review tests", "audit tests", "clean up tests", or "improve test quality" for a given scope.
**Action:** The agent must audit existing tests for duplicates, parametrize candidates, brittle string assertions, uncovered guard clauses, isolation issues, and weak assertions following the workflow in [`.github/agents/review-tests.md`](.github/agents/review-tests.md). It complements the Write-Tests agent by improving existing test quality rather than creating new tests.

## Create Tool Agent
**Trigger:** When asked to "create a new tool", "add a new algorithm", or "generate a tool scaffold".
**Action:** The agent MUST follow the architectural guidelines for tool discovery, single-source slug invariants, and module structure defined in [`.github/agents/create-tool.md`](.github/agents/create-tool.md). For any modal UI generation, it MUST delegate to the Modal Creation Agent.

## Write-Callback Agent
**Trigger:** When writing, creating, or modifying Dash `@callback` functions.
**Action:** The agent MUST follow the decorator syntax, guard-clause, and naming patterns defined in [`.github/agents/write-callback.md`](.github/agents/write-callback.md).

## AG Grid Table Agent
**Trigger:** When creating, modifying, or adding columns to an AG Grid results table (e.g., `results.py`).
**Action:** The agent MUST follow the column definition rules, theme conventions, and `autoHeight` guidelines defined in [`.github/agents/create-ag-grid.md`](.github/agents/create-ag-grid.md).
