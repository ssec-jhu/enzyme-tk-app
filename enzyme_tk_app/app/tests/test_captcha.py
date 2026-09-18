"""Tests for the proof-of-work captcha on job submission.

The constants bind at import, so every test here overrides them with ``monkeypatch.setattr``
rather than ``setenv``.  The env-parsing tests reload the module instead, which is the only way
to exercise the parse itself — the same shape as ``test_submission_limits.py``.

The happy path solves a real challenge with ``altcha.solve_challenge`` rather than mocking the
verifier, because the thing worth testing is that our challenge and our verification agree.
``COST`` is dropped to 100 in the fixture to keep that under a few milliseconds; the client's
work is a geometric draw of ~256 attempts, so the default 10 000 would make the suite crawl.
No network is involved at any point — ``altcha`` is pure stdlib.
"""

import importlib
import re
from pathlib import Path

import altcha
import pytest
from dash import dcc, html

from enzyme_tk_app.app.components import modal_helpers
from enzyme_tk_app.app.utils import captcha

from .conftest import find_components

TEST_SECRET = "captcha-test-secret"


@pytest.fixture()
def captcha_on(monkeypatch):
    """Switch the captcha on with a known key, as a production deployment would."""
    monkeypatch.setattr(captcha, "PRODUCTION_MODE", True)
    monkeypatch.setattr(captcha, "_HMAC_SECRET", TEST_SECRET)
    # The client's expected work is ~256 derivations; 100 iterations keeps that instant.
    monkeypatch.setattr(captcha, "COST", 100)


def solved_payload_for(session_id: str) -> str:
    """Issue a real challenge for *session_id*, solve it in-process, return the base64 payload."""
    challenge = altcha.Challenge.from_dict(captcha.new_challenge(session_id))
    return altcha.Payload(challenge, altcha.solve_challenge(challenge)).to_base64()


# ── The switch ──────────────────────────────────────────────────────────────────


def test_disabled_returns_none_without_reading_the_key(monkeypatch):
    """Local mode is the default, and it must do no work at all.

    The counterpart of ``test_disabled_returns_none_without_touching_the_scheduler``: the
    production check sits first so a scientist running the app locally never pays for a parse,
    a derivation, or a key read on submit.
    """
    monkeypatch.setattr(captcha, "PRODUCTION_MODE", False)
    # A secret that would reject everything, to prove it is never consulted.
    monkeypatch.setattr(captcha, "_HMAC_SECRET", "")
    assert captcha.validate_captcha(None, "sess-1") is None
    assert captcha.validate_captcha("garbage", "sess-1") is None


def test_production_mode_without_a_key_refuses_every_submission(monkeypatch):
    """Half-configured production fails CLOSED, and says so as an operator problem.

    Unreachable through ``app.py``, which refuses to start in this state — but UI gating is
    never the protection boundary, so the guard is tested on its own terms.
    """
    monkeypatch.setattr(captcha, "PRODUCTION_MODE", True)
    monkeypatch.setattr(captcha, "_HMAC_SECRET", "")

    message = captcha.validate_captcha("anything", "sess-1")

    assert message is not None
    assert "misconfigured" in message.lower()


# ── The happy path ──────────────────────────────────────────────────────────────


def test_a_freshly_solved_challenge_is_accepted(captcha_on):
    """Our challenge and our verification agree, end to end, with no mocking."""
    assert captcha.validate_captcha(solved_payload_for("sess-1"), "sess-1") is None


def test_the_challenge_carries_the_session_and_an_expiry(captcha_on):
    """The two fields the whole design rests on must actually be in the minted challenge."""
    parameters = captcha.new_challenge("sess-abc")["parameters"]

    assert parameters["data"] == {"sid": "sess-abc"}
    assert parameters["expiresAt"], "a challenge with no expiry is replayable forever"


# ── Rejection ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [None, "", "   ", "not-base64!!", "e30=", "eyJjaGFsbGVuZ2UiOiB7fX0="],
    ids=["none", "blank", "whitespace", "garbage", "empty-json", "no-solution"],
)
def test_a_missing_or_malformed_payload_is_refused_without_raising(captcha_on, payload):
    """Every malformed client string returns a message and never raises.

    Raising would surface as an HTTP 500 on ``/_dash-update-component`` instead of as text in
    the modal — the contract the whole module is built around.
    """
    assert captcha.validate_captcha(payload, "sess-1") is not None


def test_a_payload_signed_with_another_key_is_refused(captcha_on, monkeypatch):
    """A challenge this server did not mint must not verify."""
    monkeypatch.setattr(captcha, "_HMAC_SECRET", "some-other-servers-secret")
    payload = solved_payload_for("sess-1")
    monkeypatch.setattr(captcha, "_HMAC_SECRET", TEST_SECRET)

    assert captcha.validate_captcha(payload, "sess-1") == captcha._REJECTED


def test_a_wrong_counter_is_refused(captcha_on):
    """A payload whose solution does not actually solve the challenge is refused."""
    challenge = altcha.Challenge.from_dict(captcha.new_challenge("sess-1"))
    solution = altcha.solve_challenge(challenge)
    solution.counter += 1

    assert captcha.validate_captcha(altcha.Payload(challenge, solution).to_base64(), "sess-1") == captcha._REJECTED


def test_an_expired_challenge_is_refused(captcha_on, monkeypatch):
    """Expiry is what bounds the replay window, so it must actually be enforced."""
    monkeypatch.setattr(captcha, "CHALLENGE_TTL_SECONDS", -1)

    message = captcha.validate_captcha(solved_payload_for("sess-1"), "sess-1")

    assert message is not None
    assert "expired" in message.lower()


# ── Session binding — the reason this feature exists ────────────────────────────


def test_a_solution_issued_to_another_session_is_refused(captcha_on):
    """A valid proof minted for one session must not submit for another.

    This is the test that pins the whole design.  ``validate_active_job_limit`` is keyed on a
    cookie the client can simply discard; the binding here is what makes discarding it cost a
    fresh proof of work.  Delete ``data={"sid": ...}`` from ``new_challenge`` and this fails.
    """
    assert captcha.validate_captcha(solved_payload_for("sess-a"), "sess-b") == captcha._REJECTED


def test_retargeting_a_solved_payload_breaks_the_signature(captcha_on):
    """Rewriting the bound session after solving must not work either.

    The binding lives *inside* the HMAC-signed parameters, so an attacker cannot solve once and
    relabel the payload for each fresh cookie.  This asserts the property rather than trusting
    the library's docs for it.
    """
    challenge = altcha.Challenge.from_dict(captcha.new_challenge("sess-victim"))
    solution = altcha.solve_challenge(challenge)
    challenge.parameters.data = {"sid": "sess-attacker"}

    payload = altcha.Payload(challenge, solution).to_base64()

    assert captcha.validate_captcha(payload, "sess-attacker") == captcha._REJECTED


# ── Documented limitation, asserted rather than wished away ─────────────────────


def test_the_same_payload_verifies_twice_within_its_window(captcha_on):
    """Replay inside the expiry window is a known, documented limitation — not a bug.

    Asserting it keeps the module docstring honest, and this is the test that flips to
    ``is not None`` on the day one-shot nonces land.
    """
    payload = solved_payload_for("sess-1")

    assert captcha.validate_captcha(payload, "sess-1") is None
    assert captcha.validate_captcha(payload, "sess-1") is None


def test_every_genuine_rejection_returns_the_same_message(captcha_on):
    """A prober must not learn which check it failed.

    Expiry and misconfiguration are deliberately distinct — both are actionable and neither
    tells an attacker anything — but signature, counter and session-binding failures must be
    indistinguishable.
    """
    wrong_session = captcha.validate_captcha(solved_payload_for("sess-a"), "sess-b")
    malformed = captcha.validate_captcha("garbage", "sess-b")

    assert wrong_session == malformed == captcha._REJECTED


# ── Env parsing — must never raise (see the module docstring) ───────────────────


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, False),
        ({"APP_IN_PRODUCTION_MODE": "true"}, True),
        ({"APP_IN_PRODUCTION_MODE": "TRUE"}, True),
        ({"APP_IN_PRODUCTION_MODE": "1"}, True),
        ({"APP_IN_PRODUCTION_MODE": " yes "}, True),
        ({"APP_IN_PRODUCTION_MODE": "false"}, False),
        ({"APP_IN_PRODUCTION_MODE": ""}, False),
        ({"APP_IN_PRODUCTION_MODE": "ture"}, False),
    ],
    ids=["unset", "true", "upper", "one", "padded-yes", "false", "blank", "typo"],
)
def test_production_mode_parsing(monkeypatch, env, expected):
    """A typo must resolve to False, never raise.

    ``tools/__init__.py`` swallows a callbacks import error *after* appending the tool, so a
    raising module here would leave every tool card rendering with a dead Run button behind an
    HTTP 200 — the same trap ``submission_limits.py`` documents.
    """
    monkeypatch.delenv("APP_IN_PRODUCTION_MODE", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    try:
        assert importlib.reload(captcha).PRODUCTION_MODE is expected
    finally:
        monkeypatch.undo()
        importlib.reload(captcha)


def test_the_cost_is_a_constant_not_an_environment_variable(monkeypatch):
    """The work factor must not be settable from the environment.

    It is policy this app owns: a deployer who could set it to 1 would quietly undo the
    protection while the widget still appears to work. This test is what stops an env read
    being reintroduced as a convenience.
    """
    for name in ("COST", "CAPTCHA_COST", "ALTCHA_COST", "ETK_CAPTCHA_COST", "CHALLENGE_TTL_SECONDS"):
        monkeypatch.setenv(name, "1")
    try:
        reloaded = importlib.reload(captcha)
        assert reloaded.COST == 10_000
        assert reloaded.CHALLENGE_TTL_SECONDS == 300
        # And no resurrected second switch: PRODUCTION_MODE is the only lever.
        assert not hasattr(reloaded, "CAPTCHA_ENABLED")
    finally:
        monkeypatch.undo()
        importlib.reload(captcha)


def test_the_hmac_secret_is_domain_separated_from_the_flask_key(monkeypatch):
    """The captcha key must never equal the cookie-signing key it is derived from.

    Sharing a source is the whole reason this change needs no new environment variable; sharing
    key *material* would mean a captcha payload and a session cookie are signed alike.
    """
    monkeypatch.setattr("enzyme_tk_app.app.backend.config.SECRET_KEY", "a" * 64)
    try:
        reloaded = importlib.reload(captcha)
        assert reloaded._HMAC_SECRET
        assert reloaded._HMAC_SECRET != "a" * 64
    finally:
        monkeypatch.undo()
        importlib.reload(captcha)


def test_the_hmac_secret_is_empty_when_no_flask_key_is_configured(monkeypatch):
    """The fail-closed default app.py's startup check depends on."""
    monkeypatch.setattr("enzyme_tk_app.app.backend.config.SECRET_KEY", "")
    try:
        assert importlib.reload(captcha)._HMAC_SECRET == ""
    finally:
        monkeypatch.undo()
        importlib.reload(captcha)


# ── The JS↔Python contract (see test_smiles_rendering.py for the same pattern) ──


def _bridge_source() -> str:
    return (Path(__file__).resolve().parents[1] / "assets" / "12-altcha-bridge.js").read_text(encoding="utf-8")


def test_captcha_bridge_constants_match_python():
    """Pin both ends of the JS↔Python contract the captcha widget rides on.

    ``assets/12-altcha-bridge.js`` finds the holder div by class, points the widget at the
    challenge route, and derives the Store id from the holder id.  Renaming any of them on the
    Python side alone fails **silently and only in production**: the observer simply never
    matches, no widget mounts, no payload is ever published, and every submit is refused with
    "please complete the verification check" — forever.  Nothing in the local run would show it.
    """
    js = _bridge_source()

    assert f'_CAPTCHA_HOLDER_CLASS = "{modal_helpers.CAPTCHA_HOLDER_CLASS}"' in js
    assert f'_CHALLENGE_PATH = "{captcha.CHALLENGE_PATH}"' in js


def test_the_bridge_derives_the_store_id_the_footer_actually_renders(monkeypatch):
    """The bridge turns a holder id into a Store id by string surgery — prove it lands.

    ``_publishPayload`` does ``STORE_ID_PREFIX + holderId.slice(HOLDER_ID_PREFIX.length)``.
    Asserting the two prefixes exist is not enough: what matters is that applying them to the
    holder this footer renders yields the Store id the submit callback reads as ``State``.
    """
    monkeypatch.setattr(captcha, "PRODUCTION_MODE", True)
    footer = modal_helpers.create_modal_footer("demo-tool")

    holders = [
        d
        for d in find_components(footer, html.Div)
        if modal_helpers.CAPTCHA_HOLDER_CLASS in str(getattr(d, "className", ""))
    ]
    stores = [s for s in find_components(footer, dcc.Store) if str(getattr(s, "id", "")).endswith("-captcha")]
    assert len(holders) == 1, "production footer must render exactly one captcha holder"
    assert len(stores) == 1, "footer must render exactly one captcha Store"

    js = _bridge_source()
    store_prefix = re.search(r'_STORE_ID_PREFIX = "([^"]+)"', js).group(1)
    holder_prefix = re.search(r'_HOLDER_ID_PREFIX = "([^"]+)"', js).group(1)

    holder_id = holders[0].id
    assert holder_id.startswith(holder_prefix), f"{holder_id} does not start with the JS prefix {holder_prefix}"
    derived = store_prefix + holder_id[len(holder_prefix) :]

    assert derived == stores[0].id, (
        f"the bridge would publish to {derived!r}, but the footer renders {stores[0].id!r} — "
        "the solved payload would never reach the submit callback"
    )


def test_the_vendored_widget_registers_the_element_the_bridge_mounts():
    """The bridge creates <altcha-widget>; the vendored bundle must define that exact tag.

    Re-vendoring a different build or a major version bump can change the tag or drop the
    self-registration, and the bridge's fallback would then replace every modal's captcha with
    "Verification could not load" — a production-only failure with a green test suite.
    """
    vendored = Path(__file__).resolve().parents[1] / "assets" / "11-altcha.js"
    source = vendored.read_text(encoding="utf-8", errors="ignore")

    assert 'customElements.define("altcha-widget"' in source
    assert 'document.createElement("altcha-widget")' in _bridge_source()
