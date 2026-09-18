"""Proof-of-work captcha on every tool submission, so rotating a cookie stops being free.

Read ``submission_limits.py`` first — this module is deliberately its twin, and its reasoning
about ``APP_IN_PRODUCTION_MODE``, about policy living in constants rather than environment
variables, and about why a validator returns a message instead of raising all applies here
verbatim.  The parse is a membership test for the same reason: every tool's ``callbacks.py``
imports this module and ``tools/__init__.py`` swallows an import error there *after* the tool is
already in ``TOOLS``, so an exception at import would leave all six tool cards rendering with
dead Run buttons behind an HTTP 200 and one log line.

**What this buys, precisely.**  ``validate_active_job_limit`` caps a session at three concurrent
jobs and names its own hole: the session cookie is client-controlled, so dropping it buys fresh
slots for free.  The challenge minted here carries ``data={"sid": <session id>}`` **inside the
HMAC-signed parameters**, so a solved payload cannot be retargeted at another session — moving
it sets ``invalid_signature``.  Session rotation therefore costs a fresh proof of work, and the
two guards compose: 3N job slots costs N solves.  The binding is the whole feature, not a detail.

**The secret is derived, not configured.**  ``ETK_SECRET_KEY`` already exists, is already minted
by ``scripts/generate-env.sh``, and is already injected by ``main.bicep`` — so deriving from it
keeps this change out of the four-place environment-variable sync rule in
``docs/deployment-guide.md`` entirely.  ``blake2b(person=...)`` domain-separates the two uses so
neither ever sees the other's key material.  The cost is that rotating ``ETK_SECRET_KEY`` now
also invalidates challenges in flight, alongside the admin sessions it already invalidated.  The
door, if the captcha ever needs rotating independently of admin login: a dedicated
``ETK_CAPTCHA_HMAC_KEY`` and the five files that come with it.

It must be *stable across processes*: gunicorn runs ``--workers 2``, and a challenge minted by
one worker is verified by whichever worker gets the submit.  ``app.py`` refuses to start when
production mode is on without ``ETK_SECRET_KEY`` set, so the random per-process fallback there
can never reach this module.

Deliberate limitations, each with its door:

- **A solved payload is replayable until it expires.**  ``verify_solution`` records nothing, so
  one proof funds unlimited submissions *from the session it was issued to* for
  ``CHALLENGE_TTL_SECONDS``.  Bounded by the three-job cap it sits beside, the exploit is
  "submit, cancel, repeat, for five minutes" — a nuisance, not a flood.  One-shot nonces need a
  store, and UI code never imports Redis (``backend-agent``): the door is one
  ``claim_once(key, ttl)`` method on the ``TaskScheduler`` ABC and one call here.
- **Verification costs one PBKDF2 derivation per submit** — measured at 1.9 ms for
  ``COST``, paid only after the signature check, so an unsigned flood is rejected for free.  If
  it ever shows up in a profile, ALTCHA's deterministic mode (``counter=`` plus
  ``hmac_key_secret=``) reduces verification to a single HMAC.
- **No cookie, no captcha.**  The binding is the session id, so a browser refusing
  ``etk_session_id`` can never pass.  Such a browser cannot use the app today anyway — job
  scoping already collapses without it (``backend/session.py``).
- **The widget is client-side work.**  A bot that implements the PoW in Go pays CPU, not
  puzzles.  That is the trade: this raises the cost of automation, it does not identify a bot.

Tests override the constants with ``monkeypatch.setattr``; they bind at import, so
``monkeypatch.setenv`` has no effect on them (the pattern ``test_backend_config.py`` documents).
"""

import datetime
import hashlib
import hmac
import logging
import os

import altcha
from flask import Flask, g, jsonify

from enzyme_tk_app.app.backend import config

# The second reader of APP_IN_PRODUCTION_MODE, parsed here rather than imported from
# submission_limits so each module owns its own binding — patching one in a test must not
# silently flip the other.  submission_limits' docstring pre-authorises a shared module "the day
# a second feature reads it"; deliberately not taken for one line, which would cost a third file
# and a rewrite of test_submission_limits.py's reload-based parsing tests.  Take it on the third.
PRODUCTION_MODE: bool = os.environ.get("APP_IN_PRODUCTION_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

# Where the widget fetches a challenge.  Served by init_captcha() below, production only,
# and mirrored in assets/12-altcha-bridge.js — renaming it means editing that file too.
CHALLENGE_PATH: str = "/altcha-challenge"

# Constants, not environment variables, for the reason MAX_ACTIVE_JOBS_PER_SESSION is one: these
# are policy about who this app is for, and a deployer who could set COST to 1 would quietly
# undo the protection.
ALGORITHM: str = "PBKDF2/SHA-256"

# PBKDF2-SHA256 iterations per client attempt.  The client must find a counter whose derived key
# starts with ALTCHA's default one-byte prefix, so it runs ~256 attempts (expected value of a
# geometric draw) spread across the browser's web workers; the server pays exactly ONE
# derivation per verified submit.  Measured, not reasoned about:
#
#   server verification   0.3 / 1.0 / 1.9 / 4.7 ms  at a cost of 1k / 5k / 10k / 25k (M-series)
#   browser, end to end   ~2.0 s at 10k on 12 cores — modal open to "verified", including the
#                         challenge fetch and ALTCHA's own 500 ms minDuration
#
# It is a two-sided dial: raising it makes automation more expensive AND this server slower on
# every submit, while the *client* cost lands on the visitor's hardware, not ours — so a
# four-core laptop pays proportionally more than the number above.  ``auto="onload"`` starts the
# solve when the modal opens, so the wait normally hides behind form-filling; a user who opens a
# modal, picks an example and clicks Run within ~2 s gets "Please complete the verification
# check" and succeeds on a second click.  Lower this to 5_000 if that ever reads as broken
# rather than as a hiccup.  Re-measure both rows before changing it.
COST: int = 10_000

# How long a minted challenge stays usable: long enough to fill in a modal form without the
# widget going stale mid-typing, short enough to bound the replay window named above.
CHALLENGE_TTL_SECONDS: int = 300

# Domain-separated from the Flask session cookie signing key so the two uses never share key
# material even though they share a source.  Empty when ETK_SECRET_KEY is unset, which is only
# reachable with production mode off — app.py refuses to start in the other combination.
_HMAC_SECRET: str = (
    hashlib.blake2b(config.SECRET_KEY.encode(), digest_size=32, person=b"etk-altcha").hexdigest()
    if config.SECRET_KEY
    else ""
)

# One message for every genuine failure, rather than a taxonomy.  Telling a client which check
# it failed — signature, counter, or session binding — is free reconnaissance, and a human only
# ever needs the same instruction.  "Expired" and "misconfigured" are deliberately separate
# because both are actionable and neither tells an attacker anything.
_REJECTED = "Verification failed — tick the check box in this dialog again, then press Run."


def new_challenge(session_id: str) -> dict:
    """Return a fresh, session-bound, expiring challenge in ALTCHA's wire format.

    Args:
        session_id: The anonymous session id, from ``flask.g.session_id``.

    Returns:
        A JSON-serialisable dict with ``parameters`` and ``signature`` keys.
    """
    return altcha.create_challenge(
        ALGORITHM,
        COST,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=CHALLENGE_TTL_SECONDS),
        # Inside the signed parameters — retargeting this at another session breaks the
        # signature, which is what makes cookie rotation cost a solve.
        data={"sid": session_id},
        hmac_secret=_HMAC_SECRET,
    ).to_dict()


def validate_captcha(payload: str | None, session_id: str) -> str | None:
    """Return an error message when *payload* is not a valid proof for *session_id*, else ``None``.

    Message-or-``None``, like ``validate_active_job_limit`` and every field validator beside it in
    the submit callbacks, so it reads identically to its neighbours.  Returning rather than
    raising is required: the app installs no Dash ``on_error`` handler, so an exception would
    surface as an HTTP 500 on ``/_dash-update-component`` instead of as text in the modal.

    Args:
        payload: The base64 ALTCHA payload from the modal's ``dcc.Store``, or ``None``.
        session_id: The anonymous session id, from ``flask.g.session_id``.

    Returns:
        An error message string, or ``None`` when the submission may proceed — including
        whenever production mode is off.
    """
    # Checked first so a local run does no work at all and never reads the key.
    if not PRODUCTION_MODE:
        return None

    if not _HMAC_SECRET:
        # Unreachable through app.py, which refuses to start in this state.  Kept because UI
        # gating is never the protection boundary, and logged because a half-configured
        # production deployment is an operator's bug, not a user's.
        logging.error("APP_IN_PRODUCTION_MODE is on but ETK_SECRET_KEY is unset — captcha cannot verify.")
        return "Verification is unavailable — the server is misconfigured. Please contact the administrator."

    if not payload:
        return "Please complete the verification check in this dialog, then press Run."

    # verify_solution parses the payload itself and reports a malformed one as an unverified
    # result carrying ``error`` — it does not raise, which is why there is no try/except here.
    result = altcha.verify_solution(payload, _HMAC_SECRET)
    if result.expired:
        return "Verification expired — tick the check box in this dialog again, then press Run."
    if not result.verified:
        return _REJECTED

    # Only trustworthy now that the signature over ``parameters`` has been checked; before that,
    # ``data`` is whatever the client sent.  Re-parsing cannot fail here because verify_solution
    # just parsed the same string.
    bound = (altcha.Payload.from_base64(payload).challenge.parameters.data or {}).get("sid")
    if not isinstance(bound, str) or not hmac.compare_digest(bound, session_id):
        return _REJECTED

    return None


def init_captcha(server: Flask) -> None:
    """Register the challenge endpoint on *server* — call once, beside ``init_session``.

    The app's only Flask route, and only in production: locally no widget is rendered, so a
    downloaded checkout gains no new endpoint.  It lives here rather than in ``app.py`` for the
    same reason ``init_session`` lives in ``backend/session.py`` — the route belongs next to the
    code that mints what it serves, and keeping ``flask`` out of ``app.py``'s imports keeps its
    ``__main__`` dev-server block off bandit's B201 radar.

    Args:
        server: The Flask server behind the Dash app (``app.server``).
    """
    if not PRODUCTION_MODE:
        return

    @server.route(CHALLENGE_PATH)
    def altcha_challenge():  # noqa: ANN202
        """Mint a fresh proof-of-work challenge bound to the caller's session."""
        response = jsonify(new_challenge(g.session_id))
        # A cached challenge would hand every visitor the same nonce.
        response.headers["Cache-Control"] = "no-store"
        return response
