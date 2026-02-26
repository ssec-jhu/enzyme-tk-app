"""Tests for the Dash app configuration, page layout, and UI components."""

from dash import dcc, html

from enzyme_tk_app.app.app import app  # noqa: F401 — must import before pages to satisfy dash.register_page()
from enzyme_tk_app.app.components.footer import PARTNERS
from enzyme_tk_app.app.components.icons import ICON_SOCIAL_GITHUB
from enzyme_tk_app.app.components.navbar import NAV_LINKS, make_nav_link
from enzyme_tk_app.app.pages.home import layout as home_layout

from .conftest import find_components, get_text


def test_home_layout_returns_div_with_hero_and_tools():
    result = home_layout()
    assert isinstance(result, html.Div)
    assert len(result.children) == 2


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


# -- Hero --


def test_hero_headline_text(hero):
    text = get_text(hero)
    assert "Protein" in text
    assert "Engineering" in text


def test_hero_cta_buttons(hero):
    links = find_components(hero, html.A)
    hrefs = {a.href for a in links}
    assert "/#tools" in hrefs, "Missing 'Explore Tools' CTA"


def test_hero_feature_pills_present(hero):
    text = get_text(hero)
    assert "Python-Powered Tools" in text
    assert "Async Job Processing" in text


# -- Icons --


def test_all_icon_constants_are_fontawesome():
    from enzyme_tk_app.app.components import icons

    icon_vars = {k: v for k, v in vars(icons).items() if k.startswith("ICON_")}
    assert len(icon_vars) >= 7, "Expected at least 7 icon constants"
    for name, value in icon_vars.items():
        assert value.startswith("fa-"), f"{name} does not start with 'fa-'"
