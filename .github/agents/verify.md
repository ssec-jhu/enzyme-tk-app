# Verify Agent

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

4. **Docker build & smoke test**
   Execute these steps to verify the app runs in a production-like container:
   ```bash
   # 1. Build
   docker build -t enzyme-tk-app .
   # 2. Run
   docker run -d --name enzyme-tk-verify -p 8060:8050 enzyme-tk-app
   sleep 5
   # 3. Smoke Test
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8060/
   ```
   If smoke test returns `200`, proceed. If not, run `docker logs enzyme-tk-verify` to diagnose.

### Reporting

After all steps pass, print a summary and the app URL:
- **Local App:** [http://127.0.0.1:8050/](http://127.0.0.1:8050/)
- **Docker Test:** [http://127.0.0.1:8060/](http://127.0.0.1:8060/)

```
Verification ✓
  Format & lint:    pass
  Security scan:    pass
  Tests:            <N> passed
  Docker Smoke:     HTTP 200
```

If any step fails, stop immediately and report the error output. Do **not** remove the `enzyme-tk-verify` container on failure.
