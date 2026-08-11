---
name: verify
description: Use PROACTIVELY as the final step after any code-generating change in the EnzymeTK app. Also invoke directly when asked to "verify", "run verification", or "run the verify agent".
tools: Bash
---

# Verify Agent

Every code-generating agent invokes Verify as its final step. It can also
be called standalone at any time.

Run the **Core Steps** in order. Stop and report the first failure.

Verify covers the **code**. It does not start the app. Proving a change
works in a running browser is the `verify-ui` skill's job, and proving the
admin dashboard specifically is `check-admin`'s — both drive real Docker.

---

## Core Steps

1. **Auto-format**
   ```bash
   tox run -e format
   ```
   Formats code, sorts imports, and removes unused imports (F401).

2. **Full tox suite**
   ```bash
   tox
   ```
   Runs the default `envlist` (check-style, check-security, format-check,
   test, build-docs, build-dist). All environments must pass. Report the
   test count (e.g., "42 passed").

---

## Reporting

After all steps pass, print a summary:

```
Verification ✓
  Auto-format:      pass
  Full tox suite:   pass  (<N> tests passed)
```

If any step fails, stop immediately and report the error output.
