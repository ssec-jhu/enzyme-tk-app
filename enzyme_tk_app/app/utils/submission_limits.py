"""Per-session cap on concurrent jobs, so one browser cannot starve the worker pool.

``APP_IN_PRODUCTION_MODE`` is the **only** operator lever, and it is deliberately the only
one: the cap below is policy this app owns, not deployment config, so changing it is a code
edit and a review rather than an environment variable a deployer can set on a whim.  CI
rebuilds the image on every push to ``main``, so a change here reaches Azure on the next
deploy without a manual build.

The switch lives here rather than in an app-level ``config.py``: ``paths.py`` is the standing
precedent that an app-layer module owns its own environment variable, and ``app.py`` already
binds the name ``config`` to ``backend.config``.  Move it to a module of its own the day a
second feature reads it.

Reading it is a membership test so it **cannot raise**.  Every tool's ``callbacks.py`` imports
this module and ``tools/__init__.py`` swallows an import error there *after* the tool is
already in ``TOOLS`` — so an exception here would leave all six tool cards rendering with dead
Run buttons, dead validation and dead example pickers behind an HTTP 200 and one log line.  A
typo'd value resolves to ``False`` instead, and ``app.py``'s startup line prints what was
actually resolved.

Tests patch ``enzyme_tk_app.app.utils.submission_limits.get_task_scheduler`` — **not** the
tool's ``callbacks.get_task_scheduler``, which is a different binding — and override the
constants with ``monkeypatch.setattr``.  ``PRODUCTION_MODE`` binds at import, so
``monkeypatch.setenv`` has no effect on it (the pattern ``test_backend_config.py`` documents).
"""

import os

from enzyme_tk_app.app.backend import get_task_scheduler

# The one operator lever, and the only environment variable this module reads.  Default OFF:
# a scientist who downloads the repo runs it locally with no submission limits and no code
# edits.  Today it gates this cap and nothing else — not the cookie flags (always Secure),
# not logging, not debug.
PRODUCTION_MODE: bool = os.environ.get("APP_IN_PRODUCTION_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

# How many jobs one session may hold at once.  A constant, not an environment variable: the
# right value is a policy call about who this app is for, and a deployer who could raise it
# to 1000 would quietly undo the protection.  Worth re-deriving against total worker capacity
# (`worker` replicas x Celery concurrency — 3 x CPU count under Compose) if that changes: a
# cap at or above capacity throttles nothing.
MAX_ACTIVE_JOBS_PER_SESSION: int = 3


def validate_active_job_limit(session_id: str) -> str | None:
    """Return an error message when *session_id* is at its concurrent-job cap, else ``None``.

    Message-or-``None``, like ``validate_top_n`` / ``validate_db_names`` /
    ``validate_reaction_smiles``, so it reads identically to the validators it sits beside in
    every submit callback.  Returning rather than raising is required: the app installs no
    Dash ``on_error`` handler, so an exception would surface as an HTTP 500 on
    ``/_dash-update-component`` instead of as text in the modal.

    Deliberate limitations, each with its door:

    - **The session cookie is client-controlled.**  Drop it and ``session.py`` mints a fresh
      UUID4 with fresh slots.  This stops the impatient user, the runaway script and the naive
      bot — not a determined one.  CAPTCHA is the upgrade path, ideally challenge-at-threshold
      reusing this cap as the trigger, so a scientist running twenty jobs never sees one.
    - **Check-then-act.**  The count and the submit are separate round trips, so concurrent
      requests can each pass the check before any lands.  At the ``gunicorn --workers 2
      --threads 4`` and single web replica that the Dockerfile, ``docker-compose.yml`` and
      ``main.bicep`` ship, the ceiling is ``MAX_ACTIVE_JOBS_PER_SESSION + 7`` per session,
      refillable on each drain — a throttle, not a hard invariant.  That ``7`` is a deployment
      fact: re-derive it if the worker/thread/replica counts change.  A *different* hole from
      the cookie one, which CAPTCHA does not close; the fix if the overshoot ever matters is an
      atomic Redis INCR/DECR counter (a third key, so ``backend-agent``'s dual-key TTL
      invariant becomes three-way — deliberately not in this change).
    - **Nothing ages out PENDING.**  ``_is_timed_out`` only rescues STARTED, so with the worker
      pool down these jobs hold slots until their Redis TTL.  ``cancel_job`` refuses only
      terminal statuses, so Cancel does work on PENDING — which is why the message points
      there.  Ageing out PENDING is a scheduler change this feature does not need.
    - **O(N) Redis reads on every submit, not just a blocked one**, where N is every id in the
      session set — its whole TTL-window history, including terminal and stale ids, not just
      the active ones.  A per-session counter key if it ever shows up in a profile.

    Args:
        session_id: The anonymous session id, from ``flask.g.session_id``.

    Returns:
        An error message string when the session is at its cap, or ``None`` when the
        submission may proceed (including whenever production mode is off).
    """
    # Checked before get_task_scheduler() so local mode never touches Redis.
    if not PRODUCTION_MODE:
        return None

    active = get_task_scheduler().count_active_jobs(session_id)
    if active < MAX_ACTIVE_JOBS_PER_SESSION:
        return None

    # "Cancel", never "clear": Clear Finished calls clear_jobs(), which refuses non-terminal
    # jobs and would free nothing for a user who is at the cap.
    return (
        f"You already have {active} job(s) queued or running "
        f"(limit {MAX_ACTIVE_JOBS_PER_SESSION}). Wait for one to finish, or use "
        "Cancel on the My Tasks page."
    )
