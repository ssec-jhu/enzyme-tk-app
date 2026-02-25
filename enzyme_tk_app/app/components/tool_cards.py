"""Tool card rendering components.

Provides ``ToolCard`` for individual tool cards and ``ToolGrid``
for the full grid section on the home page.

To add or edit tool cards, see ``tool_registry.py`` — no changes needed here.
"""

from dash import html

from enzyme_tk_app.app.components.tool_registry import TOOLS


def ToolCard(title, description, icon_class, libraries=None):
    """Build a single tool card.

    Args:
        title: Card heading text.
        description: Short description of the tool.
        icon_class: FontAwesome class string for the card icon.
        libraries: Optional list of library/package names shown as badges.

    Returns:
        An ``html.Div`` Dash component styled as a card.
    """
    library_badges = (
        html.Div(
            className="card-badges",
            children=[html.Span(lib, className="badge-lib") for lib in libraries],
        )
        if libraries
        else None
    )

    return html.Div(
        className="card",
        children=[
            # --- Card header: inline icon + title | badges right-aligned ---
            html.Div(
                className="card-top",
                children=[
                    html.H3(
                        children=[html.I(className=icon_class), f" {title}"],
                    ),
                    library_badges,
                ],
            ),
            # --- Card body: description ---
            html.P(description, className="card-desc"),
            # --- Card footer: launch action ---
            html.Span("Launch →", className="card-launch"),
        ],
    )


def ToolGrid():
    """Build the tool card grid section from the tool registry.

    Returns:
        An ``html.Div`` containing a heading and a grid of ``ToolCard`` components.
    """
    return html.Div(
        className="container",
        children=[
            html.Div(
                className="text-center",
                style={"marginBottom": "var(--spacing-lg)"},
                children=[
                    html.H2("Available Tools", id="tools"),
                    html.P("Select a tool to configure parameters and run analysis."),
                ],
            ),
            html.Div(
                className="card-grid",
                children=[
                    ToolCard(
                        tool["title"],
                        tool["desc"],
                        tool["icon"],
                        tool.get("libraries"),
                    )
                    for tool in TOOLS
                ],
            ),
        ],
    )
