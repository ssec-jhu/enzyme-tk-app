"""Tests for the Timer Tool Template — modal, callbacks, compute, and results."""

import json
from unittest.mock import MagicMock, patch

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pytest
from dash import dcc, html, no_update
from dash.exceptions import PreventUpdate

from enzyme_tk_app.app.tests.conftest import find_components, get_text, make_job
from enzyme_tk_app.app.tools.timer_tool_template import TOOL_DEF

# ---------------------------------------------------------------------------
# Modal structure — timer-specific controls
# ---------------------------------------------------------------------------


def _build_modal():
    """Build and return the Timer modal component."""
    from enzyme_tk_app.app.tools.timer_tool_template.modal import modal  # noqa: PLC0415

    return modal()


def test_modal_contains_duration_input():
    """The modal must contain a number input for duration."""
    m = _build_modal()
    inputs = find_components(m, dbc.Input)
    duration_inputs = [inp for inp in inputs if inp.id == f"id-input-{TOOL_DEF['slug']}-duration"]
    assert len(duration_inputs) == 1
    assert duration_inputs[0].type == "number"


def test_modal_contains_task_name_input():
    """The modal must contain a Task Name text input — it gates submission."""
    m = _build_modal()
    inputs = find_components(m, dbc.Input)
    name_inputs = [inp for inp in inputs if inp.id == f"id-input-{TOOL_DEF['slug']}-task-name"]
    assert len(name_inputs) == 1
    assert name_inputs[0].type == "text"


def test_modal_contains_example_dropdown():
    """The modal must offer its examples through the shared -example dropdown."""
    m = _build_modal()
    dropdowns = find_components(m, dcc.Dropdown)
    example_dropdowns = [d for d in dropdowns if d.id == f"id-dropdown-{TOOL_DEF['slug']}-example"]
    assert len(example_dropdowns) == 1
    # Must have at least 2 examples to be worth a picker.
    assert len(example_dropdowns[0].options) >= 2


def test_modal_contains_checkbox():
    """The modal must contain a Checkbox for simulate-failure."""
    m = _build_modal()
    checks = find_components(m, dbc.Checkbox)
    fail_checks = [c for c in checks if c.id == f"id-check-{TOOL_DEF['slug']}-fail"]
    assert len(fail_checks) == 1


# ---------------------------------------------------------------------------
# Callback logic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "trigger_id, expected",
    [
        (f"id-btn-launch-{TOOL_DEF['slug']}", True),
        (f"id-btn-{TOOL_DEF['slug']}-cancel", False),
        ("id-btn-something-else", False),
    ],
    ids=["launch-opens", "cancel-closes", "unknown-stays-closed"],
)
def test_toggle_modal(trigger_id, expected):
    """The modal must open for launch, close for cancel, stay closed otherwise."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import toggle_timer_modal  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = trigger_id
        assert toggle_timer_modal(1, 0) is expected


def test_populate_example_duration():
    """Selecting an example must set the duration and prefill the Task Name."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import populate_example_duration  # noqa: PLC0415

    duration, task_name = populate_example_duration(30)

    assert duration == 30
    assert task_name == "30-seconds"


def test_populate_example_leaves_task_name_for_unknown_duration():
    """A duration that is not a shipped example fills the input but not the Task Name."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import populate_example_duration  # noqa: PLC0415

    duration, task_name = populate_example_duration(42)

    assert duration == 42
    assert task_name is no_update


@pytest.mark.parametrize("empty_value", [None, "", 0], ids=["none", "empty-string", "zero"])
def test_populate_example_raises_prevent_update(empty_value):
    """Clearing the example dropdown must leave every field alone."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import populate_example_duration  # noqa: PLC0415

    with pytest.raises(PreventUpdate):
        populate_example_duration(empty_value)


@pytest.mark.parametrize(
    "task_name, duration, expected_disabled",
    [
        ("smoke test", 5, False),
        (None, 5, True),
        ("", 5, True),
        ("   ", 5, True),
        # The browser rejects an out-of-range number, so Dash sends None —
        # this is what typing 0 or 500 actually looks like to the callback.
        ("smoke test", None, True),
        # A bare 0 is *present*, just out of range. Unreachable through the
        # UI, but it pins presence-not-truthiness so nobody "simplifies"
        # has_duration to bool(duration).
        ("smoke test", 0, False),
    ],
    ids=["all-valid", "no-name", "blank-name", "whitespace-name", "out-of-range-or-empty", "zero-is-present"],
)
def test_validate_timer_form(task_name, duration, expected_disabled):
    """The Run button must be disabled until every required field has a value."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import validate_timer_form  # noqa: PLC0415

    assert validate_timer_form(task_name, duration) is expected_disabled


def test_submit_requires_a_task_name():
    """A submission with no task name must be refused server-side."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        with pytest.raises(PreventUpdate):
            submit_timer_job(1, 0, "   ", 5, False)


def test_submit_clears_results_on_launch():
    """Re-opening the modal must clear the stale results placeholder without calling the scheduler."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    with (
        patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
        patch(
            "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
        ) as mock_get_sched,
    ):
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        result = submit_timer_job(0, 1, "smoke test", 5, False)
    assert result == ""
    mock_get_sched.assert_not_called()


@pytest.mark.parametrize(
    "duration, expected_fragment",
    [
        ("abc", "Invalid"),
        ("", "Invalid"),
        (None, "Invalid"),
        (0, "between 1 and 300"),
        (-1, "between 1 and 300"),
        (301, "between 1 and 300"),
        (999, "between 1 and 300"),
    ],
    ids=["non-numeric", "empty-string", "none", "zero", "negative", "over-max", "way-over-max"],
)
def test_submit_rejects_bad_duration(duration, expected_fragment):
    """Invalid or out-of-range durations must produce a validation error.

    The task name is valid throughout — these cases must reach the duration
    validator's message, not the task-name ``PreventUpdate`` guard above it.
    """
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_timer_job(1, 0, "smoke test", duration, False)
    assert expected_fragment in result


def test_submit_is_refused_at_the_active_job_limit(monkeypatch):
    """At the cap, the callback returns the message and never reaches submit_job.

    The import-walk in ``test_tools.py`` proves every tool imports the validator; only
    this proves the guard actually sits *before* the submit, on a real callback.

    Patches ``submission_limits.get_task_scheduler`` — the binding the limiter itself
    resolves — not the tool's ``callbacks.get_task_scheduler``, which every other submit
    test patches and which would leave the limiter reaching for real Redis.
    """
    from enzyme_tk_app.app.app import server  # noqa: PLC0415
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415
    from enzyme_tk_app.app.utils import submission_limits  # noqa: PLC0415

    monkeypatch.setattr(submission_limits, "PRODUCTION_MODE", True)
    monkeypatch.setattr(submission_limits, "MAX_ACTIVE_JOBS_PER_SESSION", 3)

    limiter_scheduler = MagicMock()
    limiter_scheduler.count_active_jobs.return_value = 3
    tool_scheduler = MagicMock()

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-at-cap"
        with (
            patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.utils.submission_limits.get_task_scheduler",
                return_value=limiter_scheduler,
            ),
            patch(
                "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
                return_value=tool_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_timer_job(1, 0, "at the cap", 10, False)

    assert "3" in result
    assert "Cancel" in result
    tool_scheduler.submit_job.assert_not_called()


def test_submit_calls_scheduler():
    """A valid submission must call scheduler.submit_job with correct params."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-123"

    # Use a real Flask request context so ``flask.g`` is available.
    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with (
            patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_timer_job(1, 0, "  smoke test  ", 10, False)

    # Verify the scheduler was called with the right arguments — task_name is
    # stripped, and comes first so it heads the Input Parameters table.
    mock_scheduler.submit_job.assert_called_once_with(
        tool_slug=TOOL_DEF["slug"],
        params={"task_name": "smoke test", "seconds": 10, "simulate_failure": False},
        session_id="sess-test",
    )
    assert "job-123" in result
    assert "10s" in result


def test_submit_with_simulate_failure_flag():
    """When simulate_failure is True, the confirmation message AND scheduler params must reflect it."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-456"

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-test"
        with (
            patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_timer_job(1, 0, "smoke test", 5, True)

    assert "simulate failure" in result
    # Verify simulate_failure=True was passed through to the scheduler.
    call_kwargs = mock_scheduler.submit_job.call_args[1]
    assert call_kwargs["params"]["simulate_failure"] is True


# ---------------------------------------------------------------------------
# Compute function
# ---------------------------------------------------------------------------


def test_compute_run_returns_expected_keys():
    """compute.run() must return _stat_cards, _params_exclude."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    # Use 0 seconds to avoid sleeping
    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1, "simulate_failure": False})

    assert "_stat_cards" in result, "Result must contain '_stat_cards' for stat cards"
    assert "_params_exclude" in result, "Result must contain '_params_exclude'"
    assert "dataframe" in result, "Result must contain 'dataframe'"


def test_compute_run_stat_cards_is_list_of_dicts():
    """_stat_cards must be a list of dicts with 'label' and 'value' keys."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    stat_cards = result["_stat_cards"]
    assert isinstance(stat_cards, list)
    assert len(stat_cards) >= 2, "Expected at least 2 stat card items"
    for item in stat_cards:
        assert "label" in item, f"Stat card item missing 'label': {item}"
        assert "value" in item, f"Stat card item missing 'value': {item}"


def test_compute_run_params_exclude_is_list():
    """_params_exclude must be a list of strings."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    exclude = result["_params_exclude"]
    assert isinstance(exclude, list)
    for key in exclude:
        assert isinstance(key, str)


def test_compute_run_dataframe_shape():
    """The dataframe payload must have 'columns' and 'data' keys."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    df = result["dataframe"]
    assert "columns" in df
    assert "data" in df
    assert isinstance(df["columns"], list)
    assert isinstance(df["data"], list)
    assert len(df["data"]) == 20, "Default row count should be 20"
    # Each row must have the same keys as columns
    for row in df["data"]:
        assert set(row.keys()) == set(df["columns"])


def test_compute_run_simulate_failure_raises():
    """When simulate_failure is True, run() must raise RuntimeError."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with (
        patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"),
        pytest.raises(RuntimeError, match="Simulated failure"),
    ):
        run({"seconds": 2, "simulate_failure": True})


@pytest.mark.parametrize("n_rows", [1, 5, 20, 50, 100])
def test_generate_random_dataframe_custom_rows(n_rows):
    """_generate_random_dataframe must respect the n_rows argument."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import _generate_random_dataframe  # noqa: PLC0415

    df = _generate_random_dataframe(n_rows=n_rows)
    assert len(df) == n_rows


# ---------------------------------------------------------------------------
# Results layout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result_dict",
    [
        {},
        None,
        {"dataframe": {"columns": ["a", "b"]}},
        {"dataframe": {"data": [{"a": 1}]}},
    ],
    ids=["empty-dict", "none-result", "missing-data-key", "missing-columns-key"],
)
def test_results_layout_shows_fallback_for_bad_payload(result_dict):
    """results_layout must show 'No tabular data' for missing or malformed payloads."""
    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    job = make_job(result=result_dict)
    layout = results_layout(job)
    assert isinstance(layout, html.Div)
    text = get_text(layout)
    assert "No tabular data" in text


def test_results_layout_with_empty_data_list():
    """results_layout must render a grid even if data list is empty."""
    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    job = make_job(
        result={
            "dataframe": {
                "columns": ["sample_id"],
                "data": [],
            },
        },
    )
    layout = results_layout(job)
    # ``build_ag_grid`` wraps the grid in a Div with the CSV-export toolbar.
    grids = find_components(layout, dag.AgGrid)
    # Empty data still produces a grid (with zero rows)
    assert len(grids) == 1
    assert len(grids[0].rowData) == 0


# ---------------------------------------------------------------------------
# Behavioral & edge-case tests
# ---------------------------------------------------------------------------
# These tests go beyond line coverage to verify behavioral contracts,
# boundary conditions, and data-quality invariants that matter for
# correctness and robustness.


# ── Compute — JSON serviceability contract ──────────────────────────────


def test_compute_result_is_json_serializable():
    """The entire return dict must be JSON-serializable — backend requirement.

    Large results are offloaded to disk as JSON; if the dict contains
    non-serializable objects (e.g. bare datetime, numpy arrays) the
    pipeline breaks silently.
    """
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 5, "simulate_failure": False})

    # json.dumps will raise TypeError for non-serializable values.
    serialised = json.dumps(result)
    assert isinstance(serialised, str)


# ── Compute — meta values are consistent with scalar values ─────────────


def test_compute_stat_cards_timer_label_matches_requested_seconds():
    """The 'Timer Set to' stat card must reflect the requested seconds param."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 42})

    stat_card_timer = next(m for m in result["_stat_cards"] if m["label"] == "Timer Set to")
    assert stat_card_timer["value"] == "42s"
    # requested_seconds is no longer echoed in result — it's auto-displayed from job.params
    assert "requested_seconds" not in result


def test_compute_stat_cards_rows_generated_matches_dataframe_length():
    """The 'Rows Generated' stat card must match the actual data row count."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    stat_card_rows = next(m for m in result["_stat_cards"] if m["label"] == "Rows Generated")
    actual_rows = len(result["dataframe"]["data"])
    assert stat_card_rows["value"] == str(actual_rows)


# ── Compute — _params_exclude hides simulate_failure ─────────────────────


def test_compute_params_exclude_hides_simulate_failure():
    """simulate_failure is a developer flag and must be excluded from result display."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    assert "simulate_failure" in result["_params_exclude"]


# ── Compute — simulate_failure error includes context ────────────────────


def test_compute_simulate_failure_message_includes_requested_seconds():
    """The RuntimeError message must include the requested duration for debugging."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with (
        patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"),
        pytest.raises(RuntimeError, match=r"requested 10s"),
    ):
        run({"seconds": 10, "simulate_failure": True})


# ── Callbacks — boundary duration values ──────────────────────────────────


@pytest.mark.parametrize(
    "duration, job_id",
    [(1, "job-min"), (300, "job-max")],
    ids=["min-boundary", "max-boundary"],
)
def test_submit_accepts_boundary_duration(duration, job_id):
    """Boundary durations (1 and 300) must be accepted and submitted."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = job_id

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-boundary"
        with (
            patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_timer_job(1, 0, "smoke test", duration, False)

    assert job_id in result
    mock_scheduler.submit_job.assert_called_once()
