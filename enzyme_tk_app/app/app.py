"""Main Dash application entry point for the EnzymeTK Tool Suite."""

import logging
import secrets

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.components.footer import footer
from enzyme_tk_app.app.components.navbar import navbar
from enzyme_tk_app.app.utils import submission_limits

# Initialize the app
# We include FontAwesome for icons and Bootstrap for dbc component functionality.
# Bootstrap CSS is loaded FIRST so our custom CSS in assets/ overrides it.
external_stylesheets = [
    dbc.themes.BOOTSTRAP,
    "https://use.fontawesome.com/releases/v6.4.0/css/all.css",
]

app = Dash(__name__, use_pages=True, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)

app.title = "EnzymeTK Tool Suite"


# Using a function for layout ensures all page modules are fully loaded before
# the layout is evaluated, which prevents UnboundLocalError with the hot reloader.
def layout():
    """Return the top-level app layout."""
    return html.Div([navbar(), dash.page_container, footer()])


app.layout = layout

# Expose the underlying Flask server for production WSGI servers (e.g., gunicorn).
server = app.server

# Secret key used to sign the Flask session cookie that records a
# successful admin login.  When admin is enabled (ETK_ADMIN_TOKEN set),
# the secret key MUST also be provided — otherwise the app refuses to start.
# When admin is disabled (no token), a random ephemeral key is used so the
# app starts without any env vars for local development.  This branch only
# runs in single-process local dev (admin disabled); in production both env
# vars are always set, so all gunicorn workers share the same stable key.
if config.SECRET_KEY:
    server.config["SECRET_KEY"] = config.SECRET_KEY
elif config.ADMIN_TOKEN:
    raise RuntimeError(
        "ETK_ADMIN_TOKEN is set but ETK_SECRET_KEY is not. "
        "A stable secret key is required to sign admin session cookies. "
        "Run scripts/generate-env.sh to generate both."
    )
else:
    server.config["SECRET_KEY"] = secrets.token_hex(32)

# This tells the browser that the cookie should only be sent in HTTP requests
# and should not be accessible via client-side scripts (like JavaScript's document.cookie).
server.config["SESSION_COOKIE_HTTPONLY"] = True
# SameSite=Lax: This setting controls how cookies are sent on cross-site requests.
# Lax is a safe default that prevents the browser from sending the cookie on
# cross-site POST requests, which helps block CSRF attacks.
server.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Secure: only ever send the cookie over an encrypted connection.  This key governs
# BOTH cookies — backend/session.py reads it for the anonymous etk_session_id cookie
# too — and it is forced on unconditionally, so neither is ever sent in the clear.
# Browsers treat http://localhost as a trustworthy origin and accept Secure cookies
# there, which is the only reason local Docker works without TLS.  Serve the app over
# plain HTTP on any other origin (a LAN IP, a bare hostname) and both cookies are
# silently dropped: admin login appears to succeed but the dashboard never populates,
# and every anonymous request mints a fresh session id.  Deploy behind a
# TLS-terminating reverse proxy.
server.config["SESSION_COOKIE_SECURE"] = True

# Register anonymous session-cookie management so every request gets a
# ``flask.g.session_id`` that Dash callbacks can read.
from enzyme_tk_app.app.backend.session import init_session  # noqa: E402

init_session(server)

# Deliberately WARNING, not INFO: the app calls no ``logging.basicConfig`` and the
# Dockerfile's gunicorn CMD sets no ``--log-level``, so an INFO record is dropped by
# ``logging.lastResort`` and never reaches ``docker compose logs web``.  This line is an
# operator's only confirmation that the production switch took — including when a typo'd
# value resolved to False instead of raising.  Prints once per gunicorn worker.
logging.warning(
    "EnzymeTK starting — production mode: %s, concurrent-job cap per session: %s",
    submission_limits.PRODUCTION_MODE,
    # The cap only applies in production mode, so print what is actually in force
    # rather than a number that is being ignored.
    submission_limits.MAX_ACTIVE_JOBS_PER_SESSION if submission_limits.PRODUCTION_MODE else "off",
)

if __name__ == "__main__":
    app.run(port=8050, debug=True)
