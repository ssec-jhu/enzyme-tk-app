"""Reusable "Missing data" warning badge for tool cards.

Each tool may register a ``check_data()`` callable via its own
``check_data.py`` submodule; ``data_warning_badge`` looks up the registered
callable for ``slug`` and renders a compact pill badge plus tooltip when
the callable returns a non-empty list of missing-data labels.
"""

import logging

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_DATA_WARNING
from enzyme_tk_app.app.tools import CHECK_DATA

logger = logging.getLogger(__name__)


def data_warning_badge(slug: str):
    """Return a "Missing data" badge for ``slug``, or ``None`` when data is OK.

    A tool registers a check by exporting ``check_data() -> list[str]`` from
    its own ``check_data.py`` submodule (auto-discovered into ``CHECK_DATA``).
    Tools without a registered check are treated as having no data
    dependencies.

    Args:
        slug: Tool slug used to look up the registered check and to build
            the tooltip target id.

    Returns:
        ``None`` if the tool has no registered check or its check returns
        an empty list; otherwise a Dash component (badge + tooltip) listing
        the missing data items.  The badge label always reads "Missing data";
        a failing check is caught defensively and surfaced as a
        "Data check failed" entry in the tooltip list so a buggy tool cannot
        break the home page.
    """
    check_fn = CHECK_DATA.get(slug)
    if check_fn is None:
        return None

    try:
        missing = check_fn()
    except Exception:
        # A buggy check must never break the home page render.  Log the
        # underlying error and surface a generic failure entry instead.
        logger.warning("check_data() raised for tool %s", slug, exc_info=True)
        missing = ["Data check failed"]

    # if there is no missing data, return None, no badge is rendered.
    if not missing:
        return None

    # if there is a missing data, render the badge and tooltip.
    badge_id = f"id-data-warning-{slug}"
    return html.Div(
        children=[
            html.Span(
                id=badge_id,
                className="card-data-badge",
                children=[
                    html.I(className=ICON_DATA_WARNING),
                    html.Span("Missing data"),
                ],
            ),
            dbc.Tooltip(
                html.Ul(
                    [html.Li(label) for label in missing],
                    style={"margin": 0, "paddingLeft": "1.1rem", "textAlign": "left"},
                ),
                target=badge_id,
                placement="top",
            ),
        ],
    )
