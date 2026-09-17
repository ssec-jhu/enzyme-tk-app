---
name: verify-ui
description: Drive the running EnzymeTK app in the Browser pane to confirm a UI change actually works — clicking buttons, filling tool modals, reading grids, capturing downloads. Use after any change to pages/, components/, tools/*/modal.py, tools/*/results.py, or assets/*.css. The browser analogue of the `verify` agent; run both.
---

# Verify UI Agent

`verify` proves the code is clean. **This proves the change works in a browser.**
Run it after any change a user could see: a page, a component, a tool modal, a
results layout, or a stylesheet. Pure-backend, test, or tooling changes skip it.

Never ask the user to check manually — drive it yourself and show a screenshot.

---

## 1. Get the app running

**This project runs in Docker. Always.** `docker-compose.yml` does **not**
mount the source tree, so editing a `.py` or `.css` file changes nothing in the
running container until you rebuild:

```bash
docker compose up -d --build web
```

~60–90 s. That picks up any change in *this* repo, but **not new `enzymetk`
commits** — `requirements/prd.txt` tracks a branch, so pip and the layer cache
both see an unchanged branch name. When the behaviour you are verifying lives in
the library, force the refetch:

```bash
docker compose build --no-cache web && docker compose up -d web
```

Then open the pane against the Docker app:

```
preview_start { url: "http://localhost:8050" }
```

Use the `url` form, **not** `preview_start {name: ...}`. `.claude/launch.json`
describes a bare-metal gunicorn on port 8051 that nobody runs — it does not
match how this app is deployed and will give you an app without Redis, Celery,
or the data volume.

Check the stack is up first — `docker ps` should show `web`, `worker`, `beat`,
and `redis`. If `web` is missing, `docker compose up -d`.

---

## 2. Drive the page with JavaScript, not coordinates

`read_page` returns `(empty page)` for this app — the accessibility tree does
not come back. Do not fight it, and do not click by coordinate; screenshots are
scaled (a 1400 px viewport returns an 800 px image), so pixel maths goes wrong
and the page scrolls out from under you between calls.

Every interactive component here has a stable `id-<type>-<name>` id
(`AGENTS.md` → Component IDs). Use it:

```js
document.getElementById("id-btn-results-download").click();
```

To discover what a modal exposes:

```js
[...document.querySelector(".modal-content").querySelectorAll("[id]")]
  .map((e) => e.id)
  .filter((i) => i.startsWith("id-"));
```

### Dash inputs need the native setter

Assigning `.value` does not reach Dash — React overrides the property, so the
callback never sees your text and the submit button stays disabled. Go through
the prototype descriptor and dispatch both events:

```js
function setVal(el, val) {
    const proto =
        el.tagName === "TEXTAREA"
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
}
```

For `dcc.Dropdown` and `dbc.RadioItems`, `.click()` the rendered option or
input rather than setting a value.

### `javascript_tool` calls share ONE context — the page's own

Measured, not assumed: `window.foo` set in one call is readable in the next,
and `window.dash_ag_grid` / `window.dash_clientside` are visible, so this is
the page's main world rather than an isolated one. Two consequences:

- You can stub page globals directly — `window.confirm = ...` takes effect for
  real clicks. No `<script>` injection needed.
- **A top-level `const` leaks too**, so the next call that redeclares it dies
  with `Identifier 'x' has already been declared`. **Wrap every snippet in an
  IIFE** and the problem disappears:

```js
(() => {
  const api = window.dash_ag_grid.getApi("id-grid-results");
  return JSON.stringify({ rows: api.getDisplayedRowCount() });
})();
```

`document.body.dataset` is still the tidiest place to park a value a *page
script* must also see (see the `window.confirm` stub in `check-admin`).

---

## 3. Results pages need a completed job

A tool's `results_layout` only renders for a `SUCCESS` job, so there is nothing
to look at until you create one. Submit through the UI:

1. `http://localhost:8050/` → click a card's `Launch →`.
2. Fill the modal (see the native-setter note above) and click
   `id-btn-<slug>-submit`.
3. Poll `http://localhost:8050/my-tasks` until the badge reads `SUCCESS`, then
   follow the `/my-tasks/<job_id>` link.

Reaction Similarity and Substrate/Product Similarity run in seconds on the
bundled data and are the reliable choices. **Func-E** now encodes the query
reaction itself and succeeds in ~15 s, but only with `data/unimol_weights/`
and `data/funce_models/` present — the tool card shows a **Missing data** badge
when they are not. `scripts/db_build/download_data.py` downloads the first and
reports on the second (the Func-E checkpoints have no public source yet, so they
are placed by hand); running it with every unit commented out prints an
`OK`/`MISSING` line per data item, which is the quickest way to tell a missing
prerequisite from a real regression. **Sequence / Sequence+Structure Similarity** need database
files that are usually absent locally — a failure there is almost certainly not
your change. Confirm by reading `.jobs-error-box`.

The browser session is cookie-scoped, so a fresh pane starts with zero tasks
even when jobs exist in Redis.

**`You already have 3 job(s) queued or running` is config, not a bug.** The
per-session cap is off by default and only on when `APP_IN_PRODUCTION_MODE` is
set — `docker compose logs web` prints the resolved values on startup. Cancel a
job on `/my-tasks` (Clear Finished frees nothing — it refuses non-terminal
jobs), or unset the switch and restart, before reading it as a regression.

To exercise the cap deliberately, bring `web` up with the switch on (no rebuild
needed if the image is current) and hold slots with long Timer Tool jobs:

```bash
APP_IN_PRODUCTION_MODE=1 docker compose up -d web
```

The cap is the constant `MAX_ACTIVE_JOBS_PER_SESSION` (3) in
`utils/submission_limits.py`, not an env var, so you need **three** concurrent
jobs to reach it — Timer Tool at `seconds=280` three times. `docker compose up
-d web` with no override puts it back.

### Production mode also turns the captcha on

The same switch adds a **proof-of-work captcha to every tool modal**, so a
production-mode run is not just the default run with a cap. What changes:

- `ETK_SECRET_KEY` must be set or the container **exits at startup** with a
  `RuntimeError` — the captcha derives its signing key from it. `.env` already
  carries one; `docker compose logs web` shows the message if it does not.
- Every modal footer grows an ALTCHA widget on its left, and the startup line
  reads `submission captcha: on`.
- **Run will be refused until the widget has solved**, with *"Please complete the
  verification check in this dialog, then press Run."* in the submission-results
  div. The solve starts when the modal opens and takes ~2 s, so open the modal,
  fill the form, then check the widget says verified before clicking — a first
  click inside that window is a hiccup, not a regression. Poll for it rather
  than sleeping blind:

  ```js
  document.querySelector("div.etk-captcha altcha-widget")?.getAttribute("state");
  ```

- The widget is mounted by `assets/12-altcha-bridge.js` into an empty holder div,
  **not** by Dash. An empty `div.etk-captcha` with no `altcha-widget` inside it
  after the modal opens means the bridge or the vendored `assets/11-altcha.js`
  failed — check the browser console, which is where that failure is reported.
- Verifying anything *else* in production mode? Leave the switch off unless the
  captcha is what you are checking. Its only visible surface is the modal footer.

---

## 4. Assert on facts, not on the screenshot

A screenshot proves layout. For anything else, measure it.

```js
// Layout: is the toolbar really a left-aligned flex row above the grid?
const bar = document.getElementById("id-btn-results-download").parentElement;
const cs = getComputedStyle(bar);
JSON.stringify({ display: cs.display, justify: cs.justifyContent, gap: cs.gap });
```

**Native `title` tooltips never appear in screenshots** — they are drawn by the
OS, not the page. Verify one by walking up from the hover point instead:

```js
let el = document.elementFromPoint(x, y),
    t = null;
while (el && el !== document.body) {
    if (el.getAttribute?.("title")) {
        t = el;
        break;
    }
    el = el.parentElement;
}
```

Sweeping that over an element's bounding box gives you real hit-area coverage,
which is how you catch a tooltip that only fires over the glyphs.

### Capturing a download

AG Grid sets the filename with `setAttribute("download", …)`, **not** the
`.download` property — hook both, plus the blob, and read them back in a
later call:

```js
const b = document.body;
b.dataset.dl = "";
const sa = HTMLAnchorElement.prototype.setAttribute;
HTMLAnchorElement.prototype.setAttribute = function (n, v) {
    if (String(n).toLowerCase() === "download") b.dataset.dl += v + "|";
    return sa.call(this, n, v);
};
const oc = URL.createObjectURL;
URL.createObjectURL = function (x) {
    x.text().then((t) => (b.dataset.body = t.slice(0, 500)));
    return oc.call(URL, x);
};
```

### The grid's own API

`window.dash_ag_grid.getApi("id-grid-results")` gives the live AG Grid API —
use `setFilterModel(...)` + `onFilterChanged()` to create the state you need to
test, `getDisplayedRowCount()` and `forEachNode` for the before/after counts,
`getColumnDefs()` to see what actually reached the grid.

---

## 5. Finish

- `read_console_messages { onlyErrors: true }` — must be empty.
- One screenshot of the change for the user.
- State what you measured, with numbers. If something could not be exercised
  in this environment, say so plainly rather than implying it passed.

---

## Mandatory

Run the `verify` agent (`tox run -e format`, then `tox`) as well. This skill
does not replace it — `verify` covers the code, this covers the browser.
