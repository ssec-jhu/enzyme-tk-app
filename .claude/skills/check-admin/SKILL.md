---
name: check-admin
description: Drive the /admin dashboard in a browser to confirm it still works — token login, session cookie, stat cards, both grids, Cancel Selected, the Danger Zone dialogs, and idle expiry, with several simulated users submitting real jobs. Use after any change to pages/admin.py, the admin auth flow, backend/session.py, or the session cookie config. Safe to run against a live local stack; it never disturbs the app on 8050 and never purges anything.
---

# Check Admin Skill

`tests/test_admin.py` proves the callbacks. **This proves the dashboard.**

It runs a **side-car** container on port 8051 sharing the real stack's Redis, so
your app on 8050 keeps serving throughout and the dashboard still shows real
job data. Nothing in the repo is edited, and no destructive admin action is
ever confirmed.

---

## 1. Start the side-car — never reconfigure the running app

`docker-compose.check-admin.yml` adds one service, `web-check`. Always pass
both compose files and **name the service**, or `up` will also recreate `web`:

**Write the token to a file first** — you have to type it into a form later, and
a `VAR=$(openssl …) docker compose` prefix throws it away where you cannot read
it back:

```bash
openssl rand -hex 16 > /tmp/check-admin-token
ETK_CHECK_ADMIN_TOKEN=$(cat /tmp/check-admin-token) \
  docker compose -f docker-compose.yml -f docker-compose.check-admin.yml \
  up -d --build web-check
```

The token being in the transcript is fine and expected — that is what
"disposable" buys. It dies with the container in §7.

**The variable is `ETK_CHECK_ADMIN_TOKEN`, not `ETK_ADMIN_TOKEN`.** Compose
substitutes from `.env` automatically, so naming it `ETK_ADMIN_TOKEN` would
mean a forgotten override silently boots the side-car with the **real** token —
which you would then type into a browser. `.env` never defines the `CHECK`
name, so omitting it fails the compose file loudly instead. If you see
`required variable ETK_CHECK_ADMIN_TOKEN is missing a value`, that guard is
working; set it and re-run.

**Never read `.env`, and never print the real token.** `settings.local.json`
denies `Read(.env)`. `ETK_SECRET_KEY` still resolves from `.env` unread, which
is what keeps the signed cookie valid. Never `echo`, `printenv`, or
`docker compose exec web env` the real value — a transcript is permanent, and
the only remedy is `./scripts/generate-env.sh`.

The idle window defaults to **20 s** — short so §7 is testable in one sitting,
but short enough that **the session will expire under you while you work** (see
§3). Set `ETK_CHECK_ADMIN_SESSION_TTL_SECONDS=300` for §4–§6 and re-create the
side-car with 20 s only when you reach §7, or accept re-logging-in often.

Base stack first — `docker compose ps` lists `web`, `worker`, `beat`, `redis`
(the *container* names are `enzyme-tk-app-web-1` and friends, so a literal
`docker ps` check on bare names reads as "stack is down"). `docker compose up -d
--build` if not. Rebuild is ~60–90 s; the source tree is not bind-mounted, so an
edit means a rebuild. Then:

```
preview_start { url: "http://localhost:8051/admin" }
```

## 2. Two things verify-ui gets wrong about this browser

Measured, not assumed — both matter here.

- **The JS context persists across `javascript_tool` calls, and it is the
  page's own world.** `window.foo` set in one call is readable in the next, and
  `window.dash_ag_grid` is visible. So `document.body.dataset` round-trips are
  unnecessary — **but a top-level `const` also leaks**, and the next call
  redeclaring it dies with `Identifier 'x' has already been declared`. **Wrap
  every snippet in an IIFE** (`(() => { ... })()`) and the problem disappears.
- **Because it is the page's world, a plain `window.confirm = ...` assignment
  works.** No `<script>` injection needed (§6).

Two more limits worth knowing before you hit them:

- **`javascript_tool` aborts around 30 s.** Never `await` a long sleep in the
  page; put waits in a shell command between calls. §7's ~26 s wait only just
  fits, so do it in Bash.
- `read_page` is unreliable here — verify-ui reports `(empty page)`, and it does
  return a usable tree on the simple login card. Do not depend on either
  outcome; every assertion in this skill goes through ids.

## 3. Unlock, and the one diagnostic that matters

Wrong token first, then the real one. Dash inputs need the native setter:

```js
(() => {
  const el = document.getElementById("id-input-admin-token");
  const proto = window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, "<token>");
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  document.getElementById("id-btn-admin-login").click();
})();
```

Wrong token must leave `.admin-login-error` reading `Invalid token. Access
denied.` with `id-div-admin-stats` still `null`. `document.cookie` must be
empty the whole time — both cookies are HttpOnly.

**The swap is not the assertion. The card *values* are.** `_dashboard_layout()`
is the callback's return value, so it renders even if the browser rejected the
session cookie. **Blank stat cards after a successful unlock mean the cookie
was dropped**, not that there is no data — every poll is then 204ing on
`_is_admin()`. Both cookies are always `Secure` (`app.py` forces
`SESSION_COOKIE_SECURE`), which works on `localhost` only because browsers
treat it as a trustworthy origin.

Note `document.getElementById("id-interval-admin-poll")` is **null** even when
mounted — `dcc.Interval` renders no DOM node. Not a failure.

### The other failure: populated but frozen

There are two ways the dashboard lies, and they look opposite:

| Symptom | Cause |
| --- | --- |
| Cards **blank** after a successful unlock | The browser dropped the session cookie |
| Cards **populated but never changing**, and actions do nothing | The admin session **expired**; every callback is now 204 |

The second is the one that will actually bite you, because there is no visible
signal: an expired session makes every admin callback return HTTP 204 with an
empty body, so Dash writes nothing and the **last-rendered numbers stay on
screen** — including whatever `#id-div-admin-action-result` last said. Re-reading
a stale `No jobs selected.` from a dead session is an easy hour to lose.

While `/admin` stays mounted you are fine: the 10 s poll slides the idle window
on every tick, and it keeps firing even though the Browser pane tab reports
`document.visibilityState === "hidden"` (measured: ticks at 6/16/26/36/47 s, all
HTTP 200, session still alive at 47 s against a 20 s TTL). You lose the session
by **navigating away** — §7's expiry test, or any stretch where the dashboard is
unmounted. Coming back re-renders the login card, so that case is obvious; the
dangerous case is a long shell step with the page mid-navigation.

If anything looks stuck, re-run the §3 unlock before trusting a reading. It is
idempotent and costs one call.

## 4. Read the dashboard, and cross-check it

The cards populate on mount; no 10 s wait needed. `getApi` **throws** (`no grid
found, or grid is not initialized yet`) rather than returning null if you call
it a moment early, which aborts the whole call — so catch it:

```js
(() => {
  const cards = [...document.querySelectorAll("#id-div-admin-stats .jobs-stat-card")]
    .map((c) => [c.querySelector(".jobs-stat-label").textContent,
                 c.querySelector(".jobs-stat-value").textContent]);
  const api = (id) => { try { return window.dash_ag_grid.getApi(id); } catch { return null; } };
  const jobs = api("id-grid-admin-jobs");
  const sess = api("id-grid-admin-sessions");
  return JSON.stringify({
    cards,
    jobRows: jobs ? jobs.getDisplayedRowCount() : "grid not ready — retry",
    sessionRows: sess ? sess.getDisplayedRowCount() : "grid not ready — retry",
  });
})();
```

Two invariants, both from one `admin_list_all_jobs()` call so they cannot
legitimately disagree: **Jobs in System == jobs-grid rows**, and **Active
Sessions == sessions-grid rows**. Read them in one call — the 10 s poll moves
the numbers between calls, and comparing across calls invents failures.

A third worth running: every session row's `total` must equal the jobs actually
carrying that `session_id` (`forEachNode` both grids and count). And note
`getColumnDefs()` includes the hidden `job_id` column — that is what carries
the full UUID into `selectedRows`.

## 5. Several users, submitting real jobs

**Run this before §6** — §6 cancels a running job, and this is what creates one.

`simulate_users.py` (next to this file) creates N independent anonymous
sessions and submits a real Timer Tool job from each — no seeded Redis rows:

```bash
python3 .claude/skills/check-admin/simulate_users.py --users 3 --isolation-check
```

Each user is one cookie jar getting its own `etk_session_id` from the real
`before_request`/`after_request` pair; the jobs run on the real Celery worker.
The three profiles produce SUCCESS, FAILURE, and a **280 s** job still STARTED
when you read the dashboard — that last one is §6's cancel target, so **finish
§6 within ~4 minutes or re-run this**, or it completes and there is nothing
left to cancel. `--isolation-check` additionally asserts each user's My Tasks
poll returns their own job and none of the others'; it needs **≥ 2 users** and
silently skips the isolation report below that. Exit code is non-zero on any
failure.

Two things it deliberately does not do: N browser tabs share one cookie jar, so
tabs are **not** users; and cross-session *refusal* (`_owns_job`) is already
covered by `tests/test_backend_multisession.py` at the layer where it lives.

**Inspect state through the app, not redis-cli.** A `docker compose exec` inside
a `while read` loop swallows the piped stdin and you get one silent, wrong row:

```bash
docker compose exec -T web-check python -c "
from enzyme_tk_app.app.backend import get_task_scheduler
for j in get_task_scheduler().admin_list_all_jobs():
    print(j.status.value, j.job_id[:8], j.tool_slug, (j.params or {}).get('task_name',''))
"
```

That listing is also the **only** place job ids and task names appear together —
the jobs grid has no `task_name` column and the script's JSON report has no job
ids. Take §6's target id from here: the `STARTED` row whose name ends
`-long-running`.

## 6. Cancel Selected, and the Danger Zone

`suppressRowClickSelection: true`, so selection goes through the grid API.
**Target the explicit job id from §5, never a blanket status filter** — a real
user's running work can be STARTED too.

**Select and click in separate calls.** `setSelected` fires `selectionChanged`,
which is how dash-ag-grid syncs `selectedRows` to the callback's `State`, but
that sync is **not synchronous** — doing both in one IIFE gets you
`No jobs selected.` Split them, and confirm the selection landed before
clicking:

```js
// call 1 — select, and verify Dash sees it
(() => {
  const api = window.dash_ag_grid.getApi("id-grid-admin-jobs");
  api.forEachNode((n) => { if (n.data && n.data.job_id.startsWith("<id-from-§5>")) n.setSelected(true); });
  return JSON.stringify({ selected: api.getSelectedRows().map((r) => r.job_id) });
})();
```

```js
// call 2 — click
(() => { document.getElementById("id-btn-admin-cancel-selected").click(); })();
```

Then read `#id-div-admin-action-result` for `Cancelled N running job(s).` and
confirm the status really moved to `REVOKED` with §5's python listing. If it
still says `No jobs selected.`, re-read the frozen-session table in §3 before
assuming the snippet is wrong.

**`dcc.ConfirmDialog` is a native `window.confirm`** — if it actually opens it
blocks the renderer and the automation hangs. Stub it *before* clicking, with a
default that refuses:

```js
(() => {
  window.confirm = (m) => { document.body.dataset.confirmMsg = m; return document.body.dataset.confirmAnswer === "ok"; };
  document.body.dataset.confirmAnswer = "cancel";
})();
```

Then click `id-btn-admin-clear` / `id-btn-admin-purge` in a later call and read
`document.body.dataset.confirmMsg`. A non-empty message proves the callback ran
and set `displayed=True`; returning `false` sends `cancel_n_clicks`, so
**nothing is destroyed**. Assert `#id-div-admin-action-result` is *unchanged*
(it still holds the cancel message from above — not empty) and that both grid
row counts are unchanged.

**Never set `confirmAnswer` to `"ok"`.** Purge revokes every running task and
`rmtree`s the shared volume — including jobs belonging to real users of the
stack you are sharing Redis with. The dialogs are what this skill verifies; the
actions themselves are covered by `test_admin.py`.

## 7. Idle expiry, then teardown

Run this **last** — it is the one step that deliberately kills your session.

The window only slides while `/admin` is mounted (§3), so `navigate` to
`http://localhost:8051/`, wait a little longer than the TTL **in a shell
command** (`javascript_tool` aborts near 30 s), then navigate back:
`id-input-admin-token` must be present and `id-div-admin-stats` `null`.

If you raised `ETK_CHECK_ADMIN_SESSION_TTL_SECONDS` for §4–§6, either re-create
the side-car at 20 s for this step or wait out whatever you set.

Finish with `read_console_messages { onlyErrors: true }` (must be empty) and one
screenshot of the unlocked dashboard — log back in first if §7 just expired you.

Teardown, in this order — delete only what the run created, through the app's
own delete path so nothing is left inconsistent. **Both commands need the
`ETK_CHECK_ADMIN_TOKEN` prefix**: the `:?` guard in the compose file fires on
*every* command that loads it, including `rm`, and the value is irrelevant here:

```bash
docker compose exec -T web-check python -c "
from enzyme_tk_app.app.backend import get_task_scheduler
s = get_task_scheduler()
mine = [j for j in s.admin_list_all_jobs() if (j.params or {}).get('task_name','').startswith('check-admin-')]
print('deleted', sum(1 for j in mine if s.delete_job(j.job_id, j.session_id)), 'of', len(mine))
"
ETK_CHECK_ADMIN_TOKEN=unused \
  docker compose -f docker-compose.yml -f docker-compose.check-admin.yml rm -sf web-check
rm -f /tmp/check-admin-token
```

Then confirm the real app was never touched: `curl -s -o /dev/null -w '%{http_code}'
http://localhost:8050/` returns `200`, and 8051 refuses the connection.

## 8. Report

State what you measured, with numbers — card values, both grid row counts, the
cancelled job's before/after status, which dialogs fired. If something could
not be exercised in this environment, say so plainly rather than implying it
passed. Run the `verify` agent as well; this skill covers the browser, `verify`
covers the code.
