"""Home page layout for the EnzymeTK Tool Suite."""

import dash
from dash import html

from enzyme_tk_app.app.components.hero import Hero
from enzyme_tk_app.app.components.tool_cards import ToolGrid
from enzyme_tk_app.app.tools import ToolModals

# Register this module as the home page ("/") in Dash's multi-page system.
dash.register_page(__name__, path="/")


def layout():
    """Return the home page layout.

    Returns:
        An ``html.Div`` containing the hero banner, tools grid, and modals.
    """
    return html.Div([Hero(), ToolGrid(), ToolModals()])
