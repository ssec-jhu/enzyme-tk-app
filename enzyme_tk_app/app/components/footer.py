"""Footer component for the EnzymeTK Tool Suite application.

Renders the page footer with partner institution logos, copyright text,
and social media links.
"""

from dash import html

from enzyme_tk_app.app.components.icons import ICON_SOCIAL_GITHUB

# --- Reusable inline styles ---

# grayscale(1) desaturates logos to gray; opacity dims them for a muted look.
# maxHeight + maxWidth + objectFit keep logos uniformly sized regardless of
# their native aspect ratios.  The .partner-logo CSS class adds a hover
# transition back to full colour.
STYLE_PARTNER_LOGO = {
    "maxHeight": "50px",
    "maxWidth": "160px",
    "objectFit": "contain",
    "filter": "grayscale(1)",
    "opacity": "0.5",
}

STYLE_SOCIAL_LINK = {"fontSize": "2.0rem", "color": "var(--text-secondary)", "lineHeight": "1"}

# Partner institutions with logo images in assets/logo/.
PARTNERS = [
    {"name": "AITHYRA", "src": "/assets/logo/AITHYRA.svg"},
    {"name": "SSEC", "src": "/assets/logo/SSEC.svg"},
    {"name": "ISTA", "src": "/assets/logo/ISTA.svg"},
]


def footer():
    """Build the site footer layout.

    Returns:
        An ``html.Footer`` Dash component containing partner logos,
        a divider, copyright text, and social links.
    """
    # Thin gradient strip replaces a flat border for a polished look.
    gradient_bar = html.Div(
        style={
            "height": "3px",
            "background": "linear-gradient(90deg, var(--primary-color), var(--accent-color), var(--secondary-color))",
        },
    )

    return html.Footer(
        style={
            "background": "var(--bg-surface)",
            "padding": "0",
            "marginTop": "4rem",
        },
        children=[
            gradient_bar,
            html.Div(
                className="container",
                style={"padding": "1.5rem 1rem"},
                children=[
                    # Main row: copyright | partner logos | GitHub link
                    html.Div(
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "flexWrap": "wrap",
                            "gap": "1rem",
                        },
                        children=[
                            # Left: copyright + tagline
                            html.Div(
                                children=[
                                    html.P(
                                        "© 2026 EnzymeTK Tool Suite.",
                                        style={
                                            "fontSize": "0.85rem",
                                            "margin": "0",
                                            "color": "var(--text-secondary)",
                                        },
                                    ),
                                    html.P(
                                        "Open-source enzyme engineering tools",
                                        style={
                                            "fontSize": "0.72rem",
                                            "margin": "0.2rem 0 0 0",
                                            "color": "var(--text-secondary)",
                                            "opacity": "0.6",
                                        },
                                    ),
                                ],
                            ),
                            # Centre: partner logos with hover class
                            html.Div(
                                style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "gap": "2rem",
                                    "justifyContent": "center",
                                },
                                children=[
                                    html.Img(
                                        src=p["src"],
                                        alt=p["name"],
                                        className="partner-logo",
                                        style=STYLE_PARTNER_LOGO,
                                    )
                                    for p in PARTNERS
                                ],
                            ),
                            # Right: GitHub link with hover class
                            html.A(
                                html.I(className=ICON_SOCIAL_GITHUB),
                                href="https://github.com/ssec-jhu/enzyme-tk-app",
                                target="_blank",
                                rel="noopener noreferrer",
                                className="footer-social",
                                style=STYLE_SOCIAL_LINK,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
