# Verify Agent

**Trigger:** Ask the agent to "verify", "run verification", or "run the verify agent".

Every code-generating agent invokes Verify as its final step. It can also
be called standalone at any time.

Run the **Core Steps** in order. Stop and report the first failure.
If the user says "verify with docker", "full verify", or "verify with
compose", also run the **Docker Compose Smoke Test** after the core steps.

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

## Docker Compose Smoke Test (optional)

**Only run when the user explicitly requests it** (see trigger phrases
above). This spins up an isolated compose stack that will NOT interfere
with any dev stack already running on the default ports.

### Setup

Generate a timestamped project name so each verify run is isolated:

```bash
PROJECT="etk-verify-$(date +%Y%m%d-%H%M%S)"
```

Start the stack using the dev + verify port-override overlays:

```bash
docker compose -p "$PROJECT" \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  -f docker-compose.verify.yml \
  up --build -d
```

Wait for services to initialise:

```bash
sleep 10
```

### Health Checks

Run all three checks. If **any** check fails, skip the remaining checks
and jump to **On Failure**.

1. **All services running**
   ```bash
   docker compose -p "$PROJECT" ps --status running --format json | \
     python3 -c "import sys,json; svcs=json.loads(sys.stdin.read()); \
     names={s['Service'] for s in svcs}; \
     assert names >= {'web','redis','worker'}, f'Missing: { {\"web\",\"redis\",\"worker\"} - names }'"
   ```

2. **Web returns HTTP 200**
   ```bash
   STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8051/)
   [ "$STATUS" = "200" ] || (echo "Web returned $STATUS" && exit 1)
   ```

3. **Worker connected to Redis**
   ```bash
   docker compose -p "$PROJECT" logs worker 2>&1 | grep -q "celery@.*ready"
   ```
   If the log line is not found, try the explicit Celery ping:
   ```bash
   docker compose -p "$PROJECT" exec -T worker \
     celery -A enzyme_tk_app.app.backend.celery_app inspect ping
   ```

### On Success

Leave the stack running so the user can inspect it. Print the project name
and URL:

```
Docker Compose Smoke Test ✓
  Project:  $PROJECT
  Web URL:  http://127.0.0.1:8051/
  Tip:      docker compose -p $PROJECT down -v   # to tear down later
```

### On Failure

Print the relevant service logs, then tear down:

```bash
docker compose -p "$PROJECT" logs --tail=50
docker compose -p "$PROJECT" down -v
```

Report which check failed and the log output.

---

## Reporting

After all steps pass, print a summary:

```
Verification ✓
  Auto-format:      pass
  Full tox suite:   pass  (<N> tests passed)
  Docker Compose:   pass / skipped
```

If any step fails, stop immediately and report the error output.
