"""Hero banner component for the landing page.

Renders the main hero section with an accent-colored headline,
description, call-to-action buttons, and a decorative protein
background image with feature badges.
"""

from dash import html


def hero():
    """Build the hero banner layout.

    Returns:
        An ``html.Div`` Dash component styled as the hero section.
    """
    return html.Div(
        className="hero",
        children=[
            # Full-width protein structure background image
            html.Div(className="hero-protein-bg"),
            # Centred content overlay
            html.Div(
                className="hero-content",
                children=[
                    # Left side: Text content
                    html.Div(
                        className="hero-text",
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
                                        href="/#tools",
                                        className="btn btn-primary",
                                    ),
                                    html.A(
                                        "View My Tasks",
                                        href="#",
                                        className="btn btn-outline",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # Right side: Decorative graphic
                    html.Div(
                        className="hero-graphic",
                        children=[
                            html.Div(className="hero-protein-graphic"),
                        ],
                    ),
                    # Diagonal feature badges (positioned within hero bounds)
                    html.Div(
                        className="hero-badges",
                        children=[
                            html.Div(
                                className="hero-badge",
                                children=[
                                    html.I(className="fa-brands fa-osi"),
                                    html.Span("Open Source"),
                                ],
                            ),
                            html.Div(
                                className="hero-badge",
                                children=[
                                    html.I(className="fa-brands fa-python"),
                                    html.Span("Python-Powered"),
                                ],
                            ),
                            html.Div(
                                className="hero-badge",
                                children=[
                                    html.I(className="fa-solid fa-globe"),
                                    html.Span("Browser-Based"),
                                ],
                            ),
                            html.Div(
                                className="hero-badge",
                                children=[
                                    html.I(className="fa-solid fa-bolt"),
                                    html.Span("Async Processing"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
