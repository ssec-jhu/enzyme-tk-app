"""Tool card rendering components.

Provides ``tool_card`` for individual tool cards and ``tool_grid``
for the full grid section on the home page.

To add or edit tools, create a new sub-package under ``tools/`` — no
changes needed here.  See ``enzyme_tk_app.app.tools`` for details.
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.data_warning import data_warning_badge
from enzyme_tk_app.app.tools import TOOLS

# Matches the old .badge-lib CSS — kept co-located with the only consumer.
# Explicit hex values (accent #D69E2E at 12%/35% mixed with white) because
# dbc.Badge sets background via Bootstrap !important — we override with className="".
STYLE_BADGE_LIB = {
    "backgroundColor": "#FBF5E4",
    "color": "#D69E2E",
    "border": "1px solid #F0D78C",
    "fontFamily": "monospace",
    "fontSize": "0.7rem",
    "fontWeight": "500",
    "padding": "2px 8px",
}


def tool_card(slug, title, description, icon_class, libraries=None):
    """Build a single tool card.

    Args:
        slug: URL-safe identifier used for the launch button ID.
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
            children=[dbc.Badge(lib, pill=True, color="", style=STYLE_BADGE_LIB) for lib in libraries],
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
            # --- Card footer: missing-data badge (left) | launch action (right) ---
            html.Div(
                children=[
                    html.Div(data_warning_badge(slug)),
                    dbc.Button(
                        "Launch →",
                        id=f"id-btn-launch-{slug}",
                        color="link",
                        className="card-launch",
                        # Override .card-launch.btn layout rules that fight the flex
                        # row: drop its top margin and self-alignment so the button
                        # sits centered in the footer row instead of pinned bottom-right.
                        style={"marginLeft": "auto", "marginTop": 0, "alignSelf": "auto"},
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    # Vertical spacing now lives on the footer container instead of
                    # the button, so the badge and button stay aligned on the row.
                    "marginTop": "0.75rem",
                },
            ),
        ],
    )


def tool_grid():
    """Build the tool card grid section from the tool registry.

    Returns:
        An ``html.Div`` containing a heading and a grid of ``tool_card`` components.
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
                    tool_card(
                        tool["slug"],
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
