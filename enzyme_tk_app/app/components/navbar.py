"""Navbar component for the EnzymeTK Tool Suite application.

Renders a top navigation bar with the app logo and navigation links.
The active link is highlighted based on the current URL pathname via a callback.
"""

from dash import Input, Output, callback, dcc, html


# Central list of navigation links displayed in the navbar.
# Each entry maps a visible label to its target href.
NAV_LINKS = [
    {"label": "Home", "href": "/"},
    {"label": "Tools", "href": "#id-div-tools"},
    {"label": "My Jobs", "href": "/my-jobs"},
    {"label": "About", "href": "#"},
]


def make_nav_link(link: dict, active_href: str = None) -> html.A:
    """Create a single navigation link element.

    Args:
        link: Dict with "label" (display text) and "href" (target URL).
        active_href: The currently active pathname. If it matches
            ``link["href"]``, the link receives the "active" CSS class.

    Returns:
        An ``html.A`` Dash component styled as a nav link.
    """
    is_active = active_href == link["href"]
    return html.A(
        link["label"],
        href=link["href"],
        className="nav-link active" if is_active else "nav-link",
        style={"fontWeight": "500", "fontSize": "0.95rem"},
    )


def Navbar():
    """Build the top navigation bar layout.

    Contains:
        - A ``dcc.Location`` to track the current URL pathname.
        - The app logo (FontAwesome flask icon + title text).
        - A row of navigation links built from ``NAV_LINKS``.

    Returns:
        An ``html.Nav`` Dash component.
    """
    return html.Nav(
        style={"borderBottom": "1px solid rgba(0,0,0,0.05)"},
        children=[
            # Tracks the browser URL so the callback can highlight the active link.
            dcc.Location(id="id-location", refresh=False),
            html.Div(
                style={
                    "width": "100%",
                    "padding": "0 2rem",
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "height": "64px",
                },
                children=[
                    # App logo / brand
                    html.Div(
                        style={"fontWeight": "700", "fontSize": "1.25rem", "color": "var(--primary-color)"},
                        children=[
                            html.I(className="fa-solid fa-flask", style={"marginRight": "0.5rem"}),
                            "EnzymeTK Tool Suite",
                        ],
                    ),
                    # Navigation links container — children are rebuilt by the callback.
                    html.Div(
                        id="id-div-nav-links",
                        style={"display": "flex", "alignItems": "center", "gap": "1.5rem"},
                        children=[make_nav_link(link) for link in NAV_LINKS],
                    ),
                ],
            ),
        ],
    )


@callback(
    Output("id-div-nav-links", "children"),
    Input("id-location", "pathname"),
)
def update_active_link(pathname):
    """Re-render nav links whenever the URL changes, marking the active one."""
    return [make_nav_link(link, active_href=pathname) for link in NAV_LINKS]
