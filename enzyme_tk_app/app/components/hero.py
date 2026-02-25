"""Hero banner component for the landing page.

Renders the main hero section with an accent-colored headline,
description, call-to-action buttons, feature pills, and a decorative protein
background image.
"""

from dash import html

from enzyme_tk_app.app.components.icons import ICON_HERO_ASYNC, ICON_HERO_PYTHON


def Hero():
    """Build the hero banner layout.

    Returns:
        An ``html.Div`` Dash component styled as the hero section.
    """
    # Feature pills displayed at the bottom of the hero.
    features = [
        {"icon": ICON_HERO_PYTHON, "label": "Python-Powered Tools"},
        {"icon": ICON_HERO_ASYNC, "label": "Async Job Processing"},
    ]

    return html.Div(
        className="hero",
        children=[
            # Full-width protein structure background image
            html.Div(className="hero-protein-bg"),
            # Centred content overlay
            html.Div(
                className="hero-content",
                children=[
                    html.H1(
                        className="hero-headline",
                        children=[
                            "Accelerate Your ",
                            html.Span("Protein", className="accent"),
                            html.Br(),
                            html.Span("Engineering", className="accent"),
                            " Workflow",
                        ],
                    ),
                    # Subtitle
                    html.P(
                        "A unified platform for computational enzyme design. "
                        "Run reaction similarities, structure predictions, directed "
                        "evolution, and more — all powered by leading Python packages.",
                        className="hero-subtitle",
                    ),
                    # CTA buttons
                    html.Div(
                        className="hero-actions",
                        children=[
                            html.A(
                                children=["Explore Tools  →"],
                                href="/#id-div-tools",
                                className="btn btn-primary",
                            ),
                            html.A(
                                "View My Jobs",
                                href="#",
                                className="btn btn-outline",
                            ),
                        ],
                    ),
                    # Feature pills
                    html.Div(
                        className="hero-features",
                        children=[
                            html.Div(
                                className="hero-feature-pill",
                                children=[
                                    html.I(className=f"{feat['icon']}"),
                                    feat["label"],
                                ],
                            )
                            for feat in features
                        ],
                    ),
                ],
            ),
        ],
    )
