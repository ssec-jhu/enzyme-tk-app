"""Shared fixtures for EnzymeTK app tests."""

import pytest

from enzyme_tk_app.app.components.footer import Footer
from enzyme_tk_app.app.components.hero import Hero
from enzyme_tk_app.app.components.navbar import Navbar
from enzyme_tk_app.app.components.tool_cards import ToolCard, ToolGrid


@pytest.fixture()
def navbar():
    return Navbar()


@pytest.fixture()
def footer():
    return Footer()


@pytest.fixture()
def hero():
    return Hero()


@pytest.fixture()
def tool_grid():
    return ToolGrid()


@pytest.fixture()
def sample_tool_card():
    return ToolCard(
        slug="test-tool",
        title="Test Tool",
        description="A test description",
        icon_class="fa-solid fa-wrench",
        libraries=["numpy", "pandas"],
    )


@pytest.fixture()
def sample_tool_card_no_libs():
    return ToolCard(
        slug="bare-tool",
        title="Bare Tool",
        description="No libraries",
        icon_class="fa-solid fa-gear",
    )


def find_components(component, target_type, results=None):
    """Recursively find all Dash components of a given type in a component tree.

    Args:
        component: Root Dash component to search.
        target_type: The component class to find (e.g., html.A, html.Img).
        results: Accumulator list (internal).

    Returns:
        List of matching components.
    """
    if results is None:
        results = []
    if isinstance(component, target_type):
        results.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            find_components(child, target_type, results)
    elif children is not None:
        find_components(children, target_type, results)
    return results


def get_text(component):
    """Extract concatenated text content from a Dash component tree.

    Args:
        component: Root Dash component.

    Returns:
        A string with all text content joined by spaces.
    """
    if isinstance(component, str):
        return component
    parts = []
    children = getattr(component, "children", None)
    if isinstance(children, str):
        parts.append(children)
    elif isinstance(children, list):
        for child in children:
            parts.append(get_text(child))
    return " ".join(parts).strip()
