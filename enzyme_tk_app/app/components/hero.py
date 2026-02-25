"""Hero banner component for the landing page.

Renders the main hero section with a headline, description, call-to-action buttons,
a decorative protein background image, and key statistics.
"""

from dash import html


def Hero():
    """Build the hero banner layout.

    Returns:
        An ``html.Div`` Dash component styled as the hero section.
    """
    # Stats data displayed as cards on the right side of the hero.
    stats = [
        {"value": "12,847", "label": "Total Analyses"},
        {"value": "23", "label": "Processing"},
        {"value": "12,824", "label": "Completed"},
    ]

    return html.Div(
        className="hero",
        style={"padding": "3rem 0 2.5rem 0", "position": "relative", "overflow": "hidden"},
        children=[
            # Subtle protein background image
            html.Div(
                style={
                    "position": "absolute",
                    "top": "50%",
                    "right": "-5%",
                    "transform": "translateY(-50%)",
                    "width": "450px",
                    "height": "450px",
                    "backgroundImage": "url('https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Myoglobin.png/800px-Myoglobin.png')",
                    "backgroundSize": "contain",
                    "backgroundRepeat": "no-repeat",
                    "backgroundPosition": "center",
                    "opacity": "0.08",
                    "pointerEvents": "none",
                    "zIndex": "0",
                }
            ),
            html.Div(
                className="container",
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "gap": "3rem",
                    "position": "relative",
                    "zIndex": "1",
                },
                children=[
                    # Left side - Text content
                    html.Div(
                        style={"flex": "1", "maxWidth": "550px"},
                        children=[
                            html.H1(
                                "Advanced Bioinformatics Processing",
                                style={"marginBottom": "0.75rem", "textAlign": "left"},
                            ),
                            html.P(
                                "A comprehensive suite of powerful algorithms for genomic analysis, "
                                "structural biology, and molecular dynamics.",
                                style={
                                    "fontSize": "1.05rem",
                                    "lineHeight": "1.6",
                                    "marginBottom": "1.5rem",
                                    "textAlign": "left",
                                },
                            ),
                            html.Div(
                                children=[
                                    html.A(
                                        "Explore Tools",
                                        href="/#id-div-tools",
                                        className="btn btn-primary",
                                        style={"marginRight": "0.75rem"},
                                    ),
                                    html.A("Documentation", href="#", className="btn btn-outline"),
                                ]
                            ),
                        ],
                    ),
                    # Right side - Stats
                    html.Div(
                        style={"display": "flex", "gap": "1rem", "flexShrink": "0"},
                        children=[
                            html.Div(
                                style={
                                    "background": "var(--bg-surface)",
                                    "borderRadius": "12px",
                                    "padding": "1.25rem 1.5rem",
                                    "textAlign": "center",
                                    "minWidth": "110px",
                                    "boxShadow": "var(--shadow-sm)",
                                    "border": "1px solid var(--border-color)",
                                },
                                children=[
                                    html.Div(
                                        stat["value"],
                                        style={
                                            "fontSize": "1.5rem",
                                            "fontWeight": "700",
                                            "color": "var(--accent-color)",
                                            "lineHeight": "1.2",
                                        },
                                    ),
                                    html.Div(
                                        stat["label"],
                                        style={
                                            "fontSize": "0.75rem",
                                            "color": "var(--text-secondary)",
                                            "marginTop": "0.25rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.05em",
                                        },
                                    ),
                                ],
                            )
                            for stat in stats
                        ],
                    ),
                ],
            ),
        ],
    )
