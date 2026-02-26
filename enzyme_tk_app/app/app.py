"""Main Dash application entry point for the EnzymeTK Tool Suite."""

import dash
from dash import Dash, html

from enzyme_tk_app.app.components.footer import Footer
from enzyme_tk_app.app.components.navbar import Navbar

# Initialize the app
# We'll include FontAwesome for icons
external_stylesheets = [
    "https://use.fontawesome.com/releases/v6.4.0/css/all.css",
]

app = Dash(__name__, use_pages=True, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)

app.title = "EnzymeTK Tool Suite"


# Using a function for layout ensures all page modules are fully loaded before
# the layout is evaluated, which prevents UnboundLocalError with the hot reloader.
def layout():
    """Return the top-level app layout."""
    return html.Div([Navbar(), dash.page_container, Footer()])


app.layout = layout

# Expose the underlying Flask server for production WSGI servers (e.g., gunicorn).
server = app.server

if __name__ == "__main__":
    app.run(port=8050, debug=True)
