"""Main Dash application entry point for the EnzymeTK Tool Suite."""

import secrets

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html

from enzyme_tk_app.app.backend import config
from enzyme_tk_app.app.components.footer import footer
from enzyme_tk_app.app.components.navbar import navbar

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
# Secure: This setting ensures that the cookie is only sent over HTTPS connections.
# It is safe to force this on because the app is always deployed behind a TLS-terminating reverse proxy.
# In local development (without a proxy), the built-in server uses HTTP, but the admin token is unset
# anyway so the cookie is never created.
# Never send this cookie over an unencrypted connection.
server.config["SESSION_COOKIE_SECURE"] = True

# Register anonymous session-cookie management so every request gets a
# ``flask.g.session_id`` that Dash callbacks can read.
from enzyme_tk_app.app.backend.session import init_session  # noqa: E402

init_session(server)

if __name__ == "__main__":
    app.run(port=8050, debug=True)
