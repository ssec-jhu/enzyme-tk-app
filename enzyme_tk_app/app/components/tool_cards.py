"""Tool card rendering components.

Provides ``ToolCard`` for individual tool cards and ``ToolGrid``
for the full grid section on the home page.

To add or edit tool cards, see ``tool_registry.py`` — no changes needed here.
"""

from dash import html

from enzyme_tk_app.app.components.icons import ICON_CARD_TIMER
from enzyme_tk_app.app.components.tool_registry import TOOLS

# Merged .badge + .badge-lib styles (library name pills on each card).
STYLE_BADGE_LIB = {
    "display": "inline-block",
    "padding": "2px 8px",
    "fontSize": "0.7rem",
    "fontWeight": "500",
    "borderRadius": "4px",
    "background": "color-mix(in srgb, var(--accent-color) 12%, transparent)",
    "color": "var(--accent-color)",
    "border": "1px solid color-mix(in srgb, var(--accent-color) 35%, transparent)",
    "fontFamily": "monospace",
}


def ToolCard(title, description, icon_class, libraries=None, est_time=None, link="/"):
    """Build a single tool card.

    Args:
        title: Card heading text.
        description: Short description of the tool.
        icon_class: FontAwesome class string for the card icon.
        libraries: Optional list of library/package names shown as badges.
        est_time: Optional estimated runtime string (e.g. "~20-30 min").
        link: URL the "Launch Tool" button points to.

    Returns:
        An ``html.Div`` Dash component styled as a card.
    """
    library_badges = (
        html.Div(
            style={"display": "flex", "flexWrap": "wrap", "gap": "0.4rem", "marginTop": "0.5rem"},
            children=[html.Span(lib, style=STYLE_BADGE_LIB) for lib in libraries],
        )
        if libraries
        else None
    )

    return html.Div(
        className="card",
        children=[
            html.Div(
                style={"display": "flex", "alignItems": "flex-start", "marginBottom": "1rem"},
                children=[
                    html.Div(
                        className="icon-box",
                        style={"marginBottom": "0", "marginRight": "1rem", "flexShrink": "0"},
                        children=[html.I(className=icon_class)],
                    ),
                    html.Div(
                        style={"flex": "1"},
                        children=[
                            html.H3(
                                title, style={"marginBottom": "0.2rem", "fontSize": "1.25rem", "lineHeight": "1.2"}
                            ),
                            library_badges,
                        ],
                    ),
                ],
            ),
            html.P(description, style={"minHeight": "60px", "flex": "1"}),
            html.Div(
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "1rem",
                    "marginBottom": "0.75rem",
                    "fontSize": "0.75rem",
                    "color": "var(--text-secondary)",
                    "opacity": "0.8",
                },
                children=[
                    html.Span(
                        style={"display": "flex", "alignItems": "center", "gap": "0.4rem"},
                        children=[
                            html.I(className=ICON_CARD_TIMER, style={"fontSize": "0.7rem"}),
                            html.Span(est_time or "TBD"),
                        ],
                    ),
                ],
            ),
            html.A(
                "Launch Tool",
                href=link,
                className="btn btn-outline",
                style={"fontSize": "0.85rem", "width": "100%", "textAlign": "center", "marginTop": "auto"},
            ),
        ],
    )


def ToolGrid():
    """Build the tool card grid section from the tool registry.

    Returns:
        An ``html.Div`` containing a heading and a grid of ``ToolCard`` components.
    """
    return html.Div(
        id="id-div-tools",
        className="container",
        children=[
            html.Div(
                className="text-center",
                style={"marginBottom": "var(--spacing-lg)"},
                children=[
                    html.H2("Available Tools"),
                    html.P("Select a tool to configure parameters and run analysis."),
                ],
            ),
            html.Div(
                className="grid-3",
                children=[
                    ToolCard(
                        tool["title"],
                        tool["desc"],
                        tool["icon"],
                        tool.get("libraries"),
                        tool.get("est_time"),
                        tool.get("link", "/"),
                    )
                    for tool in TOOLS
                ],
            ),
        ],
    )
