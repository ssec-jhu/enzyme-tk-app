"""Modal layout for the Timer tool.

This modal appears when the user clicks the Launch button on the Timer tool card.
It collects the number of seconds the background task should sleep for.
"""

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.tools.timer_tool_template import TOOL_DEF

# Pre-defined quick-select durations shown as radio options.
QUICK_DURATIONS = [
    {"label": "5 seconds", "value": 5},
    {"label": "15 seconds", "value": 15},
    {"label": "30 seconds", "value": 30},
    {"label": "60 seconds", "value": 60},
]


def modal():
    """Build the Timer modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Duration in seconds (number input)
        - Quick-select radio buttons for common durations
        - Option to simulate a mid-run failure (for testing)
    """
    return dbc.Modal(
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle(
                    children=[
                        html.I(
                            className=TOOL_DEF["icon"],
                            style={"marginRight": "0.5rem", "color": "var(--primary-color)"},
                        ),
                        TOOL_DEF["title"],
                    ]
                ),
                close_button=True,
            ),
            dbc.ModalBody(
                children=[
                    # Duration Input
                    dbc.Label("Duration (seconds)", className="form-label"),
                    dbc.Input(
                        id=f"id-input-{TOOL_DEF['slug']}-duration",
                        type="number",
                        min=1,
                        max=300,
                        step=1,
                        value=5,
                        placeholder="Enter duration in seconds (1–300)",
                        className="mb-3 themed-control",
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
                                id=f"id-radio-{TOOL_DEF['slug']}-quick",
                                options=[{"label": d["label"], "value": d["value"]} for d in QUICK_DURATIONS],
                                value=5,
                                inline=True,
                                className="mt-1 themed-control",
                            ),
                        ],
                    ),
                    # Simulate failure toggle
                    html.Div(
                        className="mb-3",
                        children=[
                            dbc.Checkbox(
                                id=f"id-check-{TOOL_DEF['slug']}-fail",
                                label="Simulate failure (throws exception halfway through)",
                                value=False,
                                className="themed-control",
                            ),
                        ],
                    ),
                    # Status / job ID placeholder
                    html.Div(id=f"id-div-{TOOL_DEF['slug']}-results"),
                ],
            ),
            dbc.ModalFooter(
                children=[
                    dbc.Button(
                        "Close",
                        id=f"id-btn-{TOOL_DEF['slug']}-cancel",
                        color="secondary",
                        outline=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Start Timer",
                        id=f"id-btn-{TOOL_DEF['slug']}-submit",
                        color="primary",
                    ),
                ],
            ),
        ],
    )
