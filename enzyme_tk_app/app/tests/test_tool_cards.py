"""Tests for the tool registry and tool card rendering."""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.tool_cards import tool_card as create_tool_card
from enzyme_tk_app.app.tools import TOOLS, ToolDef

from .conftest import find_components, get_text, patch_tool_checks

# -- Tool registry data integrity --


def test_tools_list_not_empty():
    assert len(TOOLS) >= 1


def test_every_tool_has_required_keys():
    required = ToolDef.__required_keys__
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
    buttons = find_components(sample_tool_card, dbc.Button)
    # Match on structural ID pattern rather than button label text.
    launch_buttons = [b for b in buttons if (getattr(b, "id", "") or "").startswith("id-btn-launch-")]
    assert len(launch_buttons) == 1


def test_tool_card_renders_library_badges(sample_tool_card):
    badges = find_components(sample_tool_card, dbc.Badge)
    badge_texts = {get_text(b) for b in badges}
    assert "numpy" in badge_texts
    assert "pandas" in badge_texts


def test_tool_card_no_badges_when_no_libraries(sample_tool_card_no_libs):
    badges = find_components(sample_tool_card_no_libs, dbc.Badge)
    assert len(badges) == 0


# -- Data availability on the card --
# Each test builds its own card *after* patching the registry: the shared
# ``sample_tool_card`` fixture is resolved during setup, before a test body runs,
# so a card taken from it would have been rendered against the unpatched checks.

DATA_CARD_SLUG = "data-card-tool"


def _build_card(slug=DATA_CARD_SLUG):
    """Build one tool card for *slug*, with no library badges to get in the way."""
    return create_tool_card(
        slug=slug,
        title="Data Card Tool",
        description="A tool used to check the card's data states",
        icon_class="fa-solid fa-wrench",
    )


def _badge_classes(card):
    """Return the class string of every data badge on *card* (empty list = no badge)."""
    return [
        span.className
        for span in find_components(card, html.Span)
        if str(getattr(span, "id", "")).startswith("id-data-warning-")
    ]


def _data_notes(card):
    """Return every visible data note on *card* (empty list = no note)."""
    return [div for div in find_components(card, html.Div) if getattr(div, "className", None) == "card-data-note"]


def _launch_button(card):
    """Return the card's single Launch button."""
    buttons = [b for b in find_components(card, dbc.Button) if str(getattr(b, "id", "")).startswith("id-btn-launch-")]
    assert len(buttons) == 1, f"Expected exactly one launch button, found {len(buttons)}"
    return buttons[0]


def test_card_missing_data_warns_but_still_opens_the_tool(monkeypatch):
    """A blocked tool shows the red badge and the note — and Launch stays enabled.

    The enabled Launch is deliberate and is what this test guards: Launch only
    opens the form, and a tool that cannot run needs a screen that explains
    itself, not a dead control with no way to find out why.  The real gate is the
    modal's Run button, which ``validate_tool_data`` disables.  Anyone "fixing"
    the card by disabling Launch takes away the explanation as well.
    """
    patch_tool_checks(monkeypatch, DATA_CARD_SLUG, blocking=["Sequence databases (data/sequences/)"])

    card = _build_card()

    assert _badge_classes(card) == ["card-data-badge"]
    notes = _data_notes(card)
    assert len(notes) == 1, f"{DATA_CARD_SLUG}: a blocked tool must say so visibly on its card"
    note_text = get_text(notes[0])
    # The path out of the label, plus the script that fetches it — the tooltip
    # directly above already carries the full human-readable label.
    assert "data/sequences/" in note_text
    assert "scripts/db_build/download_data.py" in note_text
    assert not getattr(_launch_button(card), "disabled", False), (
        f"{DATA_CARD_SLUG}: Launch must stay enabled — it only opens the form, and the form is "
        "where the user finds out what is missing"
    )


def test_card_with_a_skipped_file_stays_launchable_and_shows_no_note(monkeypatch):
    """An advisory-only tool gets the amber badge and nothing else.

    The tool runs fine on the databases that are left, so the card must not send
    the user to the download script for a file whose columns are simply wrong.
    """
    patch_tool_checks(monkeypatch, DATA_CARD_SLUG, warnings=["bad.csv — missing columns: EC number"])

    card = _build_card()

    assert _badge_classes(card) == ["card-data-badge card-data-badge-advisory"]
    assert _data_notes(card) == [], f"{DATA_CARD_SLUG}: a tool that still runs must not be told to re-download"
    assert not getattr(_launch_button(card), "disabled", False)


def test_card_shows_nothing_when_no_check_is_registered(monkeypatch):
    """A tool with no ``check_data.py`` has no data dependencies — so the card is plain.

    Registering the checks under another slug is what "this tool has none" looks
    like to the card.  A badge appearing here would warn about a tool that
    submits perfectly well.
    """
    patch_tool_checks(monkeypatch, "another-tool", blocking=["something else is missing"])

    card = _build_card()

    assert _badge_classes(card) == []
    assert _data_notes(card) == []


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
