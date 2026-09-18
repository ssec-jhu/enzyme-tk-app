#!/usr/bin/env python3
"""Drive N anonymous users against a running EnzymeTK app, like real traffic.

The app has no accounts — "a user" is one ``etk_session_id`` cookie. So N users
means N cookie jars, each getting its own session id from the real
``before_request``/``after_request`` pair in ``backend/session.py`` and each
submitting a real Timer Tool job that a real Celery worker runs. Nothing is
seeded into Redis.

Timer Tool is the vehicle because it has no data-file dependencies and its
modal exposes both a duration and a simulate-failure flag, so one run can
produce SUCCESS, FAILURE, and still-STARTED jobs — the spread the admin
dashboard's five stat cards need to be worth checking.

Usage::

    python3 simulate_users.py --base-url http://localhost:8051 --users 3
    python3 simulate_users.py --isolation-check        # adds the scoping asserts

Prints a JSON report on stdout. Exit code is non-zero if a submission or an
isolation assertion failed.

stdlib only, on purpose: this runs from the host against a container, and
adding a dependency to look at a web page is not worth it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# Timer Tool's submit button — the anchor used to find the callback contract.
SUBMIT_BUTTON_ID = "id-btn-timer-tool-template-submit"
# My Tasks fills its own table from a poll, NOT from the page router — routing
# to /my-tasks returns an empty placeholder. This is the callback that reads
# g.session_id and returns the rows, so it is the one that proves scoping.
MY_TASKS_POLL_INPUT = "id-interval-jobs-poll"
SESSION_COOKIE_NAME = "etk_session_id"
MIN_USERS_FOR_ISOLATION = 2

# What each simulated user submits. Two quick jobs so the SUCCESS/FAILURE cards
# have something to count, and one long one that is still STARTED by the time
# the dashboard is read — that job is the safe target for Cancel Selected.
USER_PROFILES = [
    {"label": "quick-success", "seconds": 3, "fail": False},
    {"label": "quick-failure", "seconds": 3, "fail": True},
    {"label": "long-running", "seconds": 280, "fail": False},
]


class DashClient:
    """One simulated user: one cookie jar, one session id.

    Cookies are handled by hand rather than with ``http.cookiejar``. Both of
    this app's cookies are marked ``Secure``, and ``cookiejar`` (which
    ``requests`` uses underneath) refuses to replay a ``Secure`` cookie over
    plain ``http://`` — it has no localhost exception, though browsers do. One
    captured header beats subclassing a cookie policy to work around that.
    """

    def __init__(self, base_url: str) -> None:
        """Start with an empty jar; :meth:`start` fills it."""
        self.base_url = base_url.rstrip("/")
        self.session_id: str | None = None

    def _request(self, path: str, payload: dict | None = None) -> tuple[str, dict]:
        """Issue one request, capturing the session cookie on the way back."""
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if self.session_id:
            headers["Cookie"] = f"{SESSION_COOKIE_NAME}={self.session_id}"

        req = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 - localhost http by design
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", "replace")
            # Only the first response carries a Set-Cookie; after that we
            # replay the value ourselves and the server stays quiet.
            for raw in resp.headers.get_all("Set-Cookie") or []:
                if raw.startswith(f"{SESSION_COOKIE_NAME}="):
                    self.session_id = raw.split("=", 1)[1].split(";", 1)[0]
            return body, dict(resp.headers)

    def start(self) -> str:
        """Hit the app once to be issued a session id. Returns it."""
        self._request("/")
        if not self.session_id:
            raise RuntimeError("no etk_session_id cookie was issued — is the app really at this URL?")
        return self.session_id

    def callback(self, spec: dict, inputs: list, state: list) -> str:
        """POST one Dash callback, zipping *inputs*/*state* onto its contract."""
        payload = {
            "output": spec["output"],
            "outputs": _outputs_for(spec["output"]),
            "inputs": [{**dep, "value": val} for dep, val in zip(spec["inputs"], inputs, strict=True)],
            "state": [{**dep, "value": val} for dep, val in zip(spec.get("state", []), state, strict=True)],
            "changedPropIds": [f"{spec['inputs'][0]['id']}.{spec['inputs'][0]['property']}"],
        }
        body, _ = self._request("/_dash-update-component", payload)
        return body


def _outputs_for(output: str) -> dict | list:
    """Rebuild the ``outputs`` field Dash expects from a callback's key.

    Multi-output keys look like ``..a.children...b.data..``; single ones like
    ``a.children``. The ``@<hash>`` suffix on ``allow_duplicate`` outputs is
    left exactly as found — it is derived from the whole callback set and
    changes whenever that set does, so it must never be hardcoded.
    """
    if output.startswith(".."):
        parts = [p for p in output.strip(".").split("...") if p]
        return [_split_one(p) for p in parts]
    return _split_one(output)


def _split_one(item: str) -> dict:
    """Split ``"id-div-x.children"`` into its id and property."""
    component_id, _, prop = item.rpartition(".")
    return {"id": component_id, "property": prop}


def fetch_dependencies(base_url: str) -> list[dict]:
    """Read the live callback graph Dash publishes at ``/_dash-dependencies``."""
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/_dash-dependencies", timeout=30) as resp:  # noqa: S310
        return json.load(resp)


def find_by_input(deps: list[dict], input_id: str) -> dict:
    """Return the callback whose inputs include *input_id*."""
    for dep in deps:
        if any(i.get("id") == input_id for i in dep.get("inputs", [])):
            return dep
    raise LookupError(f"no callback takes {input_id} as an input — did the tool's ids change?")


def submit_job(client: DashClient, spec: dict, task_name: str, seconds: int, fail: bool) -> str:
    """Submit one Timer Tool job and return the response text (carries the id)."""
    # State order mirrors the modal's field order: task name, duration, fail flag.
    # n_clicks 1 on submit, None on the launch button so ctx.triggered_id is submit.
    return client.callback(spec, [1, None], [task_name, seconds, ["fail"] if fail else []])


def run(base_url: str, n_users: int, *, isolation_check: bool) -> dict:
    """Create *n_users* sessions, submit a job each, and report what happened."""
    deps = fetch_dependencies(base_url)
    submit_spec = find_by_input(deps, SUBMIT_BUTTON_ID)
    my_tasks_spec = find_by_input(deps, MY_TASKS_POLL_INPUT)

    users = []
    for n in range(n_users):
        profile = USER_PROFILES[n % len(USER_PROFILES)]
        client = DashClient(base_url)
        session_id = client.start()
        task_name = f"check-admin-u{n + 1}-{profile['label']}"
        response = submit_job(client, submit_spec, task_name, profile["seconds"], profile["fail"])
        users.append(
            {
                "user": n + 1,
                "session_id": session_id,
                "task_name": task_name,
                "profile": profile["label"],
                # The callback echoes the job id into the modal's results div.
                "submitted": "Job submitted" in response or "job" in response.lower(),
                "client": client,
            }
        )

    report = {
        "base_url": base_url,
        "users": [{k: v for k, v in u.items() if k != "client"} for u in users],
        "distinct_session_ids": len({u["session_id"] for u in users}),
        "all_submitted": all(u["submitted"] for u in users),
    }

    # One user cannot leak to anyone, so the scoping assert needs at least two.
    if isolation_check and len(users) >= MIN_USERS_FOR_ISOLATION:
        report["isolation"] = check_isolation(users, my_tasks_spec)

    return report


def check_isolation(users: list[dict], my_tasks_spec: dict) -> dict:
    """Assert each user's My Tasks list holds their own job and nobody else's.

    Covers the half only HTTP can prove: that session identity is established
    per cookie jar and scoped correctly end to end.
    ``tests/test_backend_multisession.py`` already covers ownership *refusal*
    at the scheduler layer, where ``_owns_job`` actually lives — this does not
    duplicate it.
    """
    results = []
    for user in users:
        # One poll tick, as this user. The callback reads g.session_id off the
        # cookie we replay, so the rows it returns are that user's whole world.
        rows = user["client"].callback(my_tasks_spec, [1], [])
        others = [o["task_name"] for o in users if o is not user and o["task_name"] in rows]
        results.append(
            {
                "user": user["user"],
                "sees_own_job": user["task_name"] in rows,
                "leaked_from_other_sessions": others,
            }
        )
    return {
        "per_user": results,
        "every_user_sees_own_job": all(r["sees_own_job"] for r in results),
        "no_cross_session_leak": all(not r["leaked_from_other_sessions"] for r in results),
    }


def main() -> int:
    """Parse arguments, run the simulation, print the JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8051", help="app to drive (default: the side-car)")
    parser.add_argument("--users", type=int, default=3, help="how many independent sessions to create")
    parser.add_argument("--isolation-check", action="store_true", help="also assert per-session My Tasks scoping")
    args = parser.parse_args()

    try:
        report = run(args.base_url, args.users, isolation_check=args.isolation_check)
    except (urllib.error.URLError, LookupError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(report, indent=2))

    ok = report["all_submitted"] and report["distinct_session_ids"] == args.users
    if "isolation" in report:
        ok = ok and report["isolation"]["every_user_sees_own_job"] and report["isolation"]["no_cross_session_leak"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
