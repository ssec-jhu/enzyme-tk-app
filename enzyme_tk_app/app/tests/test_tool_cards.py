"""Tests for the tool registry and tool card rendering."""

from dash import html

from enzyme_tk_app.app.components.tool_registry import TOOLS

from .conftest import find_components, get_text

# -- Tool registry data integrity --


def test_tools_list_not_empty():
    assert len(TOOLS) >= 1


def test_every_tool_has_required_keys():
    required = {"title", "desc", "icon"}
    for tool in TOOLS:
        missing = required - tool.keys()
        assert not missing, f"Tool '{tool.get('title', '?')}' missing keys: {missing}"


def test_tool_icons_are_fontawesome_strings():
    for tool in TOOLS:
        assert tool["icon"].startswith("fa-"), f"Tool '{tool['title']}' icon is not FontAwesome"


def test_tool_libraries_are_lists_when_present():
    for tool in TOOLS:
        libs = tool.get("libraries")
        if libs is not None:
            assert isinstance(libs, list), f"Tool '{tool['title']}' libraries should be a list"
            assert all(isinstance(lib, str) for lib in libs)


# -- ToolCard rendering --


def test_tool_card_displays_title_and_description(sample_tool_card):
    text = get_text(sample_tool_card)
    assert "Test Tool" in text
    assert "A test description" in text


def test_tool_card_has_launch_action(sample_tool_card):
    spans = find_components(sample_tool_card, html.Span)
    launch_spans = [s for s in spans if getattr(s, "children", None) == "Launch →"]
    assert len(launch_spans) == 1


def test_tool_card_renders_library_badges(sample_tool_card):
    badges = find_components(sample_tool_card, html.Span)
    badge_texts = {get_text(b) for b in badges}
    assert "numpy" in badge_texts
    assert "pandas" in badge_texts


def test_tool_card_no_badges_when_no_libraries(sample_tool_card_no_libs):
    badges = [s for s in find_components(sample_tool_card_no_libs, html.Span) if "badge" in (s.className or "")]
    assert len(badges) == 0


# -- ToolGrid --


def test_tool_grid_has_tools_anchor_id(tool_grid):
    grid_heading = find_components(tool_grid, html.H2)
    assert any(getattr(h, "id", None) == "tools" for h in grid_heading)


def test_tool_grid_renders_one_card_per_registry_tool(tool_grid):
    cards = [c for c in find_components(tool_grid, html.Div) if getattr(c, "className", None) == "card"]
    assert len(cards) == len(TOOLS), f"Expected {len(TOOLS)} cards, got {len(cards)}"


def test_tool_grid_contains_all_tool_titles(tool_grid):
    text = get_text(tool_grid)
    for tool in TOOLS:
        assert tool["title"] in text, f"Tool '{tool['title']}' not found in grid"
