"""Tests for the Timer Tool Template — modal, callbacks, compute, and results."""

import json
from unittest.mock import MagicMock, patch

import dash_bootstrap_components as dbc
import pytest
from dash import html

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


def test_modal_contains_radio_items():
    """The modal must contain RadioItems for quick-select."""
    m = _build_modal()
    radios = find_components(m, dbc.RadioItems)
    quick_radios = [r for r in radios if r.id == f"id-radio-{TOOL_DEF['slug']}-quick"]
    assert len(quick_radios) == 1
    # Must have at least 2 quick-select options
    assert len(quick_radios[0].options) >= 2


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


@pytest.mark.parametrize("quick_value", [5, 15, 30, 60])
def test_sync_quick_select_to_input(quick_value):
    """Selecting a quick duration must set the duration input to the same value."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import sync_quick_select_to_input  # noqa: PLC0415

    assert sync_quick_select_to_input(quick_value) == quick_value


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
        result = submit_timer_job(0, 1, 5, False)
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
    """Invalid or out-of-range durations must produce a validation error."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
        result = submit_timer_job(1, 0, duration, False)
    assert expected_fragment in result


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
            result = submit_timer_job(1, 0, 10, False)

    # Verify the scheduler was called with the right arguments
    mock_scheduler.submit_job.assert_called_once_with(
        tool_slug=TOOL_DEF["slug"],
        params={"seconds": 10, "simulate_failure": False},
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
            result = submit_timer_job(1, 0, 5, True)

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
    """results_layout must render a table even if data list is empty."""
    from dash import dash_table  # noqa: PLC0415

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
    tables = find_components(layout, dash_table.DataTable)
    # Empty data still produces a table (with zero rows)
    assert len(tables) == 1
    assert len(tables[0].data) == 0


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
    """The 'Timer Set to' stat card must reflect the requested_seconds scalar."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 42})

    stat_card_timer = next(m for m in result["_stat_cards"] if m["label"] == "Timer Set to")
    assert stat_card_timer["value"] == "42s"
    assert result["requested_seconds"] == 42


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
            result = submit_timer_job(1, 0, duration, False)

    assert job_id in result
    mock_scheduler.submit_job.assert_called_once()
