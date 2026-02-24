import os
import sys

import dash
from dash import html


from enzyme_tk_app.app.components.algorithm_cards import AlgorithmGrid
from enzyme_tk_app.app.components.hero import Hero

# from components.navbar import Navbar # Will add to app.py layout usually, or here.

dash.register_page(__name__, path="/")


def layout():
    return html.Div([Hero(), AlgorithmGrid()])
