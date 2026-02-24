import os
import sys

import dash
from dash import html

# Ensure we can import components relative to root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.algorithm_cards import AlgorithmGrid
from components.hero import Hero

# from components.navbar import Navbar # Will add to app.py layout usually, or here.

dash.register_page(__name__, path="/")


def layout():
    return html.Div([Hero(), AlgorithmGrid()])
