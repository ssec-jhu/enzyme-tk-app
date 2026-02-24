"""Simple tests for the Dash application."""


class TestAppImports:
    """Test that app modules can be imported."""

    def test_import_app(self) -> None:
        """Test that the main app module can be imported."""
        from enzyme_tk_app.app.app import app

        assert app is not None
        assert app.title == "EnzymeTK Tool Suite"

    def test_import_navbar(self) -> None:
        """Test that navbar component can be imported."""
        from enzyme_tk_app.app.components.navbar import Navbar

        navbar = Navbar()
        assert navbar is not None

    def test_import_footer(self) -> None:
        """Test that footer component can be imported."""
        from enzyme_tk_app.app.components.footer import Footer

        footer = Footer()
        assert footer is not None

    def test_import_hero(self) -> None:
        """Test that hero component can be imported."""
        from enzyme_tk_app.app.components.hero import Hero

        hero = Hero()
        assert hero is not None

    def test_import_algorithm_cards(self) -> None:
        """Test that algorithm cards component can be imported."""
        from enzyme_tk_app.app.components.algorithm_cards import AlgorithmGrid

        grid = AlgorithmGrid()
        assert grid is not None


class TestHomePageLayout:
    """Test the home page layout."""

    def test_home_layout_is_callable(self) -> None:
        """Test that home page layout is a callable function."""
        from enzyme_tk_app.app.pages.home import layout

        assert callable(layout)

    def test_home_layout_returns_div(self) -> None:
        """Test that home page layout returns a Div component."""
        from dash import html

        from enzyme_tk_app.app.pages.home import layout

        result = layout()
        assert isinstance(result, html.Div)
