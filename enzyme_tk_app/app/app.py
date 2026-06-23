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
# successful admin login.  In production this MUST be supplied via
# ``ETK_SECRET_KEY`` so the signed cookie cannot be forged.  When unset we
# generate a random per-process key: convenient for local dev (no config
# needed) but it rotates on every restart, logging admins out.
if config.SECRET_KEY:
    server.secret_key = config.SECRET_KEY
else:
    server.secret_key = secrets.token_hex(32)
    server.logger.warning(
        "ETK_SECRET_KEY is not set — using an ephemeral per-process key. "
        "Admin sessions will not survive a restart. Set ETK_SECRET_KEY in production."
    )

# Register anonymous session-cookie management so every request gets a
# ``flask.g.session_id`` that Dash callbacks can read.
from enzyme_tk_app.app.backend.session import init_session  # noqa: E402

init_session(server)

if __name__ == "__main__":
    app.run(port=8050, debug=True)
