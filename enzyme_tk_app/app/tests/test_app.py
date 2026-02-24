"""Simple tests for the Dash application."""

import sys
from pathlib import Path

# Add app directory to path for imports
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))


class TestAppImports:
    """Test that app modules can be imported."""

    def test_import_app(self) -> None:
        """Test that the main app module can be imported."""
        from app import app

        assert app is not None
        assert app.title == "EnzymeTK Tool Suite"

    def test_import_navbar(self) -> None:
        """Test that navbar component can be imported."""
        from components.navbar import Navbar

        navbar = Navbar()
        assert navbar is not None

    def test_import_footer(self) -> None:
        """Test that footer component can be imported."""
        from components.footer import Footer

        footer = Footer()
        assert footer is not None

    def test_import_hero(self) -> None:
        """Test that hero component can be imported."""
        from components.hero import Hero

        hero = Hero()
        assert hero is not None

    def test_import_algorithm_cards(self) -> None:
        """Test that algorithm cards component can be imported."""
        from components.algorithm_cards import AlgorithmGrid

        grid = AlgorithmGrid()
        assert grid is not None


class TestHomePageLayout:
    """Test the home page layout."""

    def test_home_layout_is_callable(self) -> None:
        """Test that home page layout is a callable function."""
        from pages.home import layout

        assert callable(layout)

    def test_home_layout_returns_div(self) -> None:
        """Test that home page layout returns a Div component."""
        from dash import html
        from pages.home import layout

        result = layout()
        assert isinstance(result, html.Div)
