"""Main Dash application entry point for the EnzymeTK Tool Suite."""

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html

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

# Register anonymous session-cookie management so every request gets a
# ``flask.g.session_id`` that Dash callbacks can read.
from enzyme_tk_app.app.backend.session import init_session  # noqa: E402

init_session(server)

if __name__ == "__main__":
    app.run(port=8050, debug=True)
