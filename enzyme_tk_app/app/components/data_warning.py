"""The data warning a tool card shows: a badge, its tooltip, and a visible note.

``data_warning(slug)`` runs the tool's registered checks **once** through
``utils/data_availability.py`` — the same module every tool's submit path reads,
so the card and the modal can never disagree about what is missing — and returns
everything the card needs to render.

Two states, because they mean different things to the person reading the grid:

- **blocking** (red, "Missing data") — the tool cannot run.  Its Run button is
  disabled and its modal says why.  The card also carries a *visible* note
  naming what is absent and the script that fetches it, because a tooltip is
  invisible on a touch screen and easy to skip with a mouse.
- **advisory** (amber, "N file(s) skipped") — something in ``data/`` is unusable
  but the tool runs on what is left.  Badge and tooltip only: no note, because
  ``download_data.py`` is not the remedy for a file with the wrong columns.
"""

from typing import NamedTuple

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_DATA_ADVISORY, ICON_DATA_WARNING
from enzyme_tk_app.app.utils.data_availability import (
    CHECK_FAILED_LABEL,
    CHECK_FAILED_MESSAGE,
    DOWNLOAD_SCRIPT,
    check_tool_data,
    missing_data_paths,
)


class DataWarning(NamedTuple):
    """What a tool card shows about its data.

    Attributes:
        badge: The pill plus its tooltip, or ``None`` when there is nothing to report.
        note: The visible reason line, or ``None`` unless the tool is blocked.
        blocked: ``True`` when the tool is missing data it cannot run without.
    """

    badge: object | None
    note: object | None
    blocked: bool


def _badge(slug: str, labels: list[str], blocked: bool):
    """Build the pill and the tooltip listing *labels*."""
    badge_id = f"id-data-warning-{slug}"
    if blocked:
        class_name, icon, text = "card-data-badge", ICON_DATA_WARNING, "Missing data"
    else:
        # Every advisory label is one skipped file, so the count is the useful part.
        class_name = "card-data-badge card-data-badge-advisory"
        icon = ICON_DATA_ADVISORY
        text = f"{len(labels)} file skipped" if len(labels) == 1 else f"{len(labels)} files skipped"

    return html.Div(
        children=[
            html.Span(
                id=badge_id,
                className=class_name,
                children=[html.I(className=icon), html.Span(text)],
            ),
            dbc.Tooltip(
                html.Ul(
                    [html.Li(label) for label in labels],
                    style={"margin": 0, "paddingLeft": "1.1rem", "textAlign": "left"},
                ),
                target=badge_id,
                placement="top",
            ),
        ],
    )


def data_warning(slug: str) -> DataWarning:
    """Return the badge, note and blocked flag for *slug*'s tool card.

    Args:
        slug: Tool slug, used to look up the registered checks and to build the
            tooltip target id.

    Returns:
        A :class:`DataWarning`.  A tool with no registered check, or one whose
        checks report nothing, gets ``(None, None, False)``.
    """
    blocking, warnings = check_tool_data(slug)
    if not blocking and not warnings:
        return DataWarning(None, None, False)

    # Blocking first: what stops the tool reads before what merely annoys it.
    badge = _badge(slug, [*blocking, *warnings], blocked=bool(blocking))
    if not blocking:
        return DataWarning(badge, None, False)

    # The note names the paths only — the human-readable labels are in the tooltip
    # right above it, and a card has no room to say the same thing twice.
    if CHECK_FAILED_LABEL in blocking:
        note = html.Div(CHECK_FAILED_MESSAGE, className="card-data-note")
    else:
        note = html.Div(
            className="card-data-note",
            children=[
                f"Requires {', '.join(missing_data_paths(blocking))}. Download using ",
                html.Code(DOWNLOAD_SCRIPT),
                ".",
            ],
        )
    return DataWarning(badge, note, True)
