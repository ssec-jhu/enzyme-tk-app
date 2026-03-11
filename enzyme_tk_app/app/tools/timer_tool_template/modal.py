"""Modal layout for the Timer tool.

This modal appears when the user clicks the Launch button on the Timer tool card.
It collects the number of seconds the background task should sleep for.
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.components.icons import ICON_TOOL_TIMER

# Pre-defined quick-select durations shown as radio options.
QUICK_DURATIONS = [
    {"label": "5 seconds", "value": 5},
    {"label": "15 seconds", "value": 15},
    {"label": "30 seconds", "value": 30},
    {"label": "60 seconds", "value": 60},
]


def Modal():
    """Build the Timer modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Duration in seconds (number input)
        - Quick-select radio buttons for common durations
    """
    return dbc.Modal(
        id="id-modal-timer-tool-template",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle(
                    children=[
                        html.I(
                            className=ICON_TOOL_TIMER,
                            style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                        ),
                        "Timer Task",
                    ]
                ),
                close_button=True,
            ),
            dbc.ModalBody(
                children=[
                    # Duration Input
                    dbc.Label("Duration (seconds)", className="form-label"),
                    dbc.Input(
                        id="id-input-timer-tool-template-duration",
                        type="number",
                        min=1,
                        max=300,
                        step=1,
                        value=5,
                        placeholder="Enter duration in seconds (1–300)",
                        className="mb-3",
                    ),
                    # Quick-select radio buttons
                    html.Div(
                        className="mb-3",
                        children=[
                            html.Small(
                                "Quick select:",
                                style={"color": "var(--text-tertiary)"},
                            ),
                            dbc.RadioItems(
                                id="id-radio-timer-tool-template-quick",
                                options=[{"label": d["label"], "value": d["value"]} for d in QUICK_DURATIONS],
                                value=5,
                                inline=True,
                                className="mt-1",
                            ),
                        ],
                    ),
                    # Results placeholder
                    html.Div(id="id-div-timer-tool-template-results"),
                ],
            ),
            dbc.ModalFooter(
                children=[
                    dbc.Button(
                        "Cancel",
                        id="id-btn-timer-tool-template-cancel",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Start Timer",
                        id="id-btn-timer-tool-template-submit",
                        color="primary",
                    ),
                ],
            ),
        ],
    )
