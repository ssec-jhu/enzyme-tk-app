"""Tests for the Dash app configuration, page layout, and UI components."""

import dash
import pytest
from dash import dcc, html

from enzyme_tk_app.app.app import app  # noqa: F401 — must import before pages to satisfy dash.register_page()
from enzyme_tk_app.app.app import layout as app_layout
from enzyme_tk_app.app.components.footer import PARTNERS
from enzyme_tk_app.app.components.icons import ICON_SOCIAL_GITHUB
from enzyme_tk_app.app.components.navbar import NAV_LINKS, make_nav_link, update_active_link
from enzyme_tk_app.app.pages.home import layout as home_layout

from .conftest import find_components, get_text

# -- App layout --


def test_app_layout_returns_div_with_navbar_page_container_and_footer():
    """app.layout() must return an html.Div with navbar, page_container, and footer."""
    result = app_layout()

    assert isinstance(result, html.Div)
    assert len(result.children) == 3
    # The second child must be the Dash page container.
    assert result.children[1] is dash.page_container


def test_home_layout_returns_div_with_hero_and_tools():
    result = home_layout()
    assert isinstance(result, html.Div)
    assert len(result.children) == 3


# -- Navbar --


def test_navbar_contains_location_tracker(navbar):
    locations = find_components(navbar, dcc.Location)
    assert len(locations) == 1
    assert locations[0].id == "id-location"


def test_navbar_renders_all_nav_links(navbar):
    links = find_components(navbar, html.A)
    labels = {link.children for link in links}
    for nav in NAV_LINKS:
        assert nav["label"] in labels, f"Missing nav link: {nav['label']}"


def test_make_nav_link_active_class():
    link = make_nav_link({"label": "Home", "href": "/"}, pathname="/")
    assert "active" in link.className

    link_inactive = make_nav_link({"label": "Home", "href": "/"}, pathname="/other")
    assert "active" not in link_inactive.className


def test_make_nav_link_active_with_hash():
    link = make_nav_link({"label": "Tools", "href": "/#tools"}, pathname="/", url_hash="#tools")
    assert "active" in link.className

    link_wrong_hash = make_nav_link({"label": "Tools", "href": "/#tools"}, pathname="/", url_hash="")
    assert "active" not in link_wrong_hash.className


@pytest.mark.parametrize(
    ("pathname", "url_hash", "expected_active_label"),
    [
        ("/", "", "Home"),
        ("/", "#tools", "Tools"),
        ("/my-tasks", "", "My Tasks"),
        ("/nonexistent", "", None),
    ],
    ids=["home-active", "tools-hash-active", "my-tasks-active", "no-match"],
)
def test_update_active_link_marks_correct_link(pathname, url_hash, expected_active_label):
    """update_active_link must return nav links with exactly one (or zero) marked active."""
    links = update_active_link(pathname, url_hash)

    assert len(links) == len(NAV_LINKS)
    active_links = [link for link in links if "active" in link.className]

    if expected_active_label is None:
        assert len(active_links) == 0, "No link should be active for an unmatched pathname"
    else:
        assert len(active_links) == 1, f"Expected exactly one active link, got {len(active_links)}"
        assert active_links[0].children == expected_active_label


# -- Footer --


def test_footer_has_copyright_text(footer):
    text = get_text(footer)
    assert "EnzymeTK Tool Suite" in text


def test_footer_renders_partner_logos(footer):
    images = find_components(footer, html.Img)
    partner_names = {img.alt for img in images}
    for p in PARTNERS:
        assert p["name"] in partner_names, f"Missing partner logo: {p['name']}"


def test_footer_github_link(footer):
    links = find_components(footer, html.A)
    github_links = [a for a in links if a.href and "github.com" in a.href]
    assert len(github_links) == 1
    icon = find_components(github_links[0], html.I)
    assert icon[0].className == ICON_SOCIAL_GITHUB
