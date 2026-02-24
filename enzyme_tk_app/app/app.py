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

app.layout = html.Div([Navbar(), dash.page_container, Footer()])

if __name__ == "__main__":
    # use_reloader=False prevents UnboundLocalError on page layouts during hot-reload.
    # The reloader spawns a subprocess that re-imports modules, and if a request arrives
    # before the layout variable/function is defined, Python raises UnboundLocalError.
    app.run(port=8050)
    # app.run(port=8050, debug=True, use_reloader=False)
