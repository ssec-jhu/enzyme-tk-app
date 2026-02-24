"""Home page layout for the EnzymeTK Tool Suite."""

import dash
from dash import html

from enzyme_tk_app.app.components.algorithm_cards import AlgorithmGrid
from enzyme_tk_app.app.components.hero import Hero

# Register this module as the home page ("/") in Dash's multi-page system.
dash.register_page(__name__, path="/")


def layout():
    """Return the home page layout.

    Returns:
        An ``html.Div`` containing the hero banner and the tools grid.
    """
    return html.Div([Hero(), AlgorithmGrid()])
