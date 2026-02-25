# Agent Instructions

This file defines on-demand workflows that can be invoked explicitly.
They do **not** run automatically — ask for them by name when needed
(e.g., "run the verify agent", "verify everything").

---

## Verify Agent

**Trigger:** Ask the agent to "verify", "run verification", or "run the verify agent".

Run every step below **in order**. Stop and report the first failure.

### Steps

1. **Format & lint**
   ```bash
   tox run -e format && tox run -e check-style
   ```
   All code must pass with zero warnings.

2. **Security scan**
   ```bash
   tox run -e check-security
   ```

3. **Unit tests**
   ```bash
   tox run -e test
   ```
   All tests must pass. Report the count (e.g., "23 passed").

4. **App smoke test**
   ```bash
   lsof -ti:8050 | xargs kill -9 2>/dev/null; sleep 1
   python3 -m enzyme_tk_app.app.app &
   sleep 5
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8050/
   ```
   Expect HTTP `200`. Kill the process after checking.

5. **Docker build & smoke test**
   ```bash
   docker build -t enzyme-tk-app .
   docker run -d --name enzyme-tk-verify -p 8050:8050 enzyme-tk-app
   sleep 5
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8050/
   docker rm -f enzyme-tk-verify
   ```
   Expect HTTP `200`. Remove the container after checking.

### Reporting

After all steps pass, print a summary:

```
Verification ✓
  Format & lint:    pass
  Security scan:    pass
  Tests:            <N> passed
  App smoke test:   HTTP 200
  Docker smoke:     HTTP 200
```

If any step fails, stop immediately and report which step failed and the error output.
