"""Anonymous session management via persistent cookies.

Provides ``init_session(server)`` which registers a Flask ``before_request``
hook that:

1. Checks for an ``etk_session_id`` cookie on every request.
2. If absent, generates a UUID4 and sets it as an HttpOnly, Secure cookie
   with a 30-day ``max_age``.
3. Stores the session ID in ``flask.g.session_id`` so Dash callbacks can
   read it with ``from flask import g; g.session_id``.

The cookie is **persistent** — it survives browser restarts for 30 days.
Users lose their session only if they clear cookies, use incognito mode,
switch browsers/devices, or the 30-day expiry elapses.

The ``Secure`` flag is derived from Flask's ``SESSION_COOKIE_SECURE``
config key.  When the key is not set (the default), the flag mirrors
``request.is_secure`` so it is automatically enabled behind a
TLS-terminating reverse proxy that sets ``X-Forwarded-Proto: https``.
Set ``SESSION_COOKIE_SECURE = True`` in Flask config (or via env var) to
force the flag on in all environments.
"""

from __future__ import annotations

import uuid

from flask import Flask, g, make_response, request

# Cookie name used across the application.
SESSION_COOKIE_NAME = "etk_session_id"

# Cookie lifetime: 30 days in seconds.
SESSION_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def init_session(server: Flask) -> None:
    """Register the session-cookie ``before_request`` hook on *server*.

    Must be called once during app startup (after ``server = app.server``).

    Args:
        server: The Flask server instance underlying the Dash app.
    """

    @server.before_request
    def _ensure_session_cookie() -> None:  # noqa: ANN202
        """Assign a session UUID if the cookie is missing."""
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            session_id = str(uuid.uuid4())
            # Store a flag so the after_request handler knows to set the cookie.
            g._set_session_cookie = True  # noqa: SLF001
        g.session_id = session_id

    @server.after_request
    def _set_session_cookie(response):  # noqa: ANN001, ANN202
        """Inject the ``Set-Cookie`` header when a new session was created."""
        if getattr(g, "_set_session_cookie", False):
            response = make_response(response)
            # Prefer an explicit Flask config flag, fall back to request.is_secure.
            secure = bool(server.config.get("SESSION_COOKIE_SECURE", request.is_secure))
            response.set_cookie(
                SESSION_COOKIE_NAME,
                g.session_id,
                max_age=SESSION_COOKIE_MAX_AGE,
                httponly=True,
                secure=secure,
                samesite="Lax",
            )
        return response
