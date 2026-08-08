"""Tests for session cookie management (``backend.session``).

These tests verify that the ``before_request`` / ``after_request`` hooks
installed by ``init_session()`` correctly assign, persist, and configure the
anonymous session cookie.

Implementation note
-------------------
The ``_simulate_request`` helper re-implements the session hook logic from
``session.py`` rather than exercising the real Flask hooks.  This is a
deliberate trade-off: Dash registers its own ``before_request`` hook for
page routing that raises duplicate-path errors when ``preprocess_request()``
runs in the test process.  Any time ``session.py`` changes, these tests
**must** be updated in lockstep to stay meaningful.
"""

import uuid

import pytest
from flask import g

from enzyme_tk_app.app.app import app  # noqa: F401 — instantiate Dash before importing pages
from enzyme_tk_app.app.backend.session import SESSION_COOKIE_MAX_AGE, SESSION_COOKIE_NAME, _is_valid_uuid4


@pytest.fixture()
def server():
    """Provide the Flask server underlying the Dash app."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415 — deferred until Dash app is instantiated

    return server


_SENTINEL = object()  # marker for "config key not set"


def _simulate_request(server, cookie_value=None, *, session_cookie_secure=_SENTINEL):
    """Run the before/after_request hooks manually and return (session_id, response).

    This mirrors the logic in ``session.py`` rather than calling the real
    Flask hooks, because Dash's page-router ``before_request`` hook fails
    with duplicate-path errors in multi-file test suites.

    Args:
        server: The Flask server instance.
        cookie_value: If provided, simulates a returning visitor.
        session_cookie_secure: If provided, sets Flask's ``SESSION_COOKIE_SECURE``
            config for this request.  Use ``_SENTINEL`` (default) to leave the
            config unset, which makes the code fall back to ``request.is_secure``.
    """
    from flask import make_response, request  # noqa: PLC0415 — must import inside request context
    from werkzeug.test import EnvironBuilder  # noqa: PLC0415 — co-located with its only call site

    # Temporarily set / remove the Flask config key for this request.
    had_key = "SESSION_COOKIE_SECURE" in server.config
    old_value = server.config.get("SESSION_COOKIE_SECURE")
    if session_cookie_secure is not _SENTINEL:
        server.config["SESSION_COOKIE_SECURE"] = session_cookie_secure
    elif had_key:
        del server.config["SESSION_COOKIE_SECURE"]

    try:
        # Build a minimal WSGI environ; inject the cookie header if simulating a return visit.
        builder = EnvironBuilder(method="GET", path="/_session_test")
        env = builder.get_environ()
        if cookie_value:
            env["HTTP_COOKIE"] = f"{SESSION_COOKIE_NAME}={cookie_value}"

        with server.request_context(env):
            # --- before_request logic (mirrors _ensure_session_cookie) ----------
            session_id = request.cookies.get(SESSION_COOKIE_NAME)
            if not _is_valid_uuid4(session_id):
                # Missing or invalid cookie → new/rotated visitor: generate a fresh UUID4.
                session_id = str(uuid.uuid4())
                # Flag tells the after_request hook to emit a Set-Cookie header.
                g._set_session_cookie = True  # noqa: SLF001
            g.session_id = session_id

            # --- after_request logic (mirrors _set_session_cookie) --------------
            response = make_response("ok")
            if getattr(g, "_set_session_cookie", False):
                # Prefer an explicit Flask config flag, fall back to request.is_secure.
                secure = bool(server.config.get("SESSION_COOKIE_SECURE", request.is_secure))
                # Only set the cookie when the flag was raised (new visitor).
                response.set_cookie(
                    SESSION_COOKIE_NAME,
                    g.session_id,
                    max_age=SESSION_COOKIE_MAX_AGE,
                    httponly=True,
                    secure=secure,
                    samesite="Lax",
                )

            return g.session_id, response
    finally:
        # Restore original config state.
        if had_key:
            server.config["SESSION_COOKIE_SECURE"] = old_value
        elif "SESSION_COOKIE_SECURE" in server.config:
            del server.config["SESSION_COOKIE_SECURE"]


# ---------------------------------------------------------------------------
# New visitor
# ---------------------------------------------------------------------------


def test_new_visitor_gets_secure_session_cookie(server):
    """First request without a cookie must set a secure, properly configured session cookie.

    Why: Anonymous users are identified solely by this cookie.  It must be
    present on the very first response so the browser stores it before any
    subsequent AJAX callback.  The ID must be UUID4 to avoid collisions
    across concurrent users.  HttpOnly prevents client-side JS from reading
    the value (XSS mitigation), SameSite=Lax stops the cookie from being
    sent on cross-site POST requests (CSRF mitigation), and Max-Age must
    match the configured constant so the cookie survives browser restarts
    for the expected 30-day window.
    """
    session_id, response = _simulate_request(server)
    cookie_header = response.headers.get("Set-Cookie", "")

    # Cookie must be present with all security attributes.
    assert SESSION_COOKIE_NAME in cookie_header, "cookie must be set on first visit"
    assert "HttpOnly" in cookie_header, "cookie must be HttpOnly to prevent XSS theft"
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in cookie_header, "Max-Age must match configured TTL"
    assert "SameSite=Lax" in cookie_header, "SameSite=Lax prevents CSRF-style cookie leaking"

    # Session ID must be a valid UUID4.
    parsed = uuid.UUID(session_id)
    assert parsed.version == 4, "session ID must be UUID4 to avoid collisions"


# ---------------------------------------------------------------------------
# Returning visitor
# ---------------------------------------------------------------------------


def test_returning_visitor_keeps_same_session(server):
    """A request carrying the existing session cookie must reuse the ID and not re-set the cookie.

    Why: If the server regenerated the cookie on every request, the user's
    job history (keyed by session ID in Redis) would be lost.  Omitting a
    new Set-Cookie header also avoids unnecessary response overhead and
    prevents the Max-Age from silently resetting on every page load, which
    would mask the intended 30-day expiry window.
    """
    session_id_1, _ = _simulate_request(server)

    # Send the cookie back on a second request.
    session_id_2, response = _simulate_request(server, cookie_value=session_id_1)

    assert session_id_2 == session_id_1, "session ID must be stable across requests"

    session_cookies = [c for c in response.headers.getlist("Set-Cookie") if SESSION_COOKIE_NAME in c]
    assert len(session_cookies) == 0, "no Set-Cookie header on return visit"


# ---------------------------------------------------------------------------
# Secure cookie flag
# ---------------------------------------------------------------------------


def test_session_cookie_secure_true_sets_flag(server):
    """When SESSION_COOKIE_SECURE is True, the cookie must always have the Secure attribute.

    Why: In deployments where TLS is guaranteed (e.g., behind a load balancer),
    operators can force Secure regardless of ``request.is_secure``.
    """
    _, response = _simulate_request(server, session_cookie_secure=True)
    cookie_header = response.headers.get("Set-Cookie", "")
    assert "Secure" in cookie_header, "Secure flag must be set when SESSION_COOKIE_SECURE=True"


def test_session_cookie_secure_false_omits_flag(server):
    """When SESSION_COOKIE_SECURE is False, the cookie must omit the Secure attribute.

    Why: Local development typically runs over plain HTTP; setting Secure
    would prevent the browser from storing the cookie.
    """
    _, response = _simulate_request(server, session_cookie_secure=False)
    cookie_header = response.headers.get("Set-Cookie", "")
    assert "Secure" not in cookie_header, "Secure flag must be absent when SESSION_COOKIE_SECURE=False"


def test_session_cookie_secure_unset_mirrors_request(server):
    """When SESSION_COOKIE_SECURE is not set, the Secure flag follows request.is_secure.

    Why: Behind a TLS-terminating reverse proxy that sets X-Forwarded-Proto,
    ``request.is_secure`` is True and the cookie is marked Secure automatically.
    In plain-HTTP dev, the flag is False and the cookie works normally.
    """
    # Plain HTTP → no Secure flag (request.is_secure is False).
    _, response = _simulate_request(server)  # config key absent → fallback
    cookie_header = response.headers.get("Set-Cookie", "")
    assert "Secure" not in cookie_header, "unset: plain HTTP should omit Secure"


# ---------------------------------------------------------------------------
# Invalid cookie values are rotated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        "not-a-uuid",
        "12345",
        "x" * 1000,  # very long string
        "session:injection:attempt",  # contains colons
        "<script>alert(1)</script>",  # XSS attempt
        "",
        "00000000-0000-1000-8000-000000000000",  # UUID v1, not v4
    ],
    ids=["gibberish", "short-number", "long-string", "colon-injection", "xss", "empty", "uuid-v1"],
)
def test_invalid_cookie_is_rotated_to_fresh_uuid4(server, bad_value):
    """A request with a non-UUID4 cookie must generate a fresh UUID4 and overwrite the cookie.

    Why: The session ID is used as part of Redis key patterns
    (e.g., ``session:<id>:jobs``).  Accepting arbitrary strings would allow
    keyspace abuse, surprising key formats, or injection of control
    characters.  Invalid values are silently replaced with a new UUID4 and
    a ``Set-Cookie`` header overwrites the bad cookie in the browser.
    """
    session_id, response = _simulate_request(server, cookie_value=bad_value)
    cookie_header = response.headers.get("Set-Cookie", "")

    # The returned session ID must be a valid UUID4 (not the bad value).
    parsed = uuid.UUID(session_id)
    assert parsed.version == 4, "rotated session ID must be UUID4"
    assert session_id != bad_value, "bad cookie value must be replaced"

    # A Set-Cookie header must be present to overwrite the bad value.
    assert SESSION_COOKIE_NAME in cookie_header, "Set-Cookie must overwrite the bad value"


def test_valid_uuid4_cookie_is_accepted(server):
    """A request carrying a valid UUID4 cookie must accept it without rotation.

    Why: Ensures the validation logic does not accidentally reject
    legitimate session cookies, which would erase the user's job history.
    """
    original = str(uuid.uuid4())
    session_id, response = _simulate_request(server, cookie_value=original)

    assert session_id == original, "valid UUID4 must be accepted as-is"
    session_cookies = [c for c in response.headers.getlist("Set-Cookie") if SESSION_COOKIE_NAME in c]
    assert len(session_cookies) == 0, "no Set-Cookie header for valid cookie"
