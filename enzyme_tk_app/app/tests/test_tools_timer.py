"""Tests for the Timer Tool Template — modal, callbacks, compute, and results."""

import json
from unittest.mock import MagicMock, patch

import dash_bootstrap_components as dbc
import pytest
from dash import html

from enzyme_tk_app.app.tests.conftest import find_components, get_text, make_job
from enzyme_tk_app.app.tools.timer_tool_template import TOOL_DEF

# ---------------------------------------------------------------------------
# TOOL_DEF basics
# ---------------------------------------------------------------------------


def test_tool_def_slug():
    """The slug must be 'timer-tool-template'."""
    assert TOOL_DEF["slug"] == "timer-tool-template"


def test_tool_def_title():
    """The title must be a non-empty string."""
    assert isinstance(TOOL_DEF["title"], str) and TOOL_DEF["title"].strip()


def test_tool_def_has_max_duration():
    """The timer tool sets a custom max_duration (not the default 3600)."""
    assert "max_duration" in TOOL_DEF
    assert TOOL_DEF["max_duration"] == 600


def test_tool_def_folder_name_matches_slug():
    """The folder name (timer_tool_template) must equal slug with hyphens → underscores."""
    expected_folder = TOOL_DEF["slug"].replace("-", "_")
    assert expected_folder == "timer_tool_template"


# ---------------------------------------------------------------------------
# Modal structure
# ---------------------------------------------------------------------------


def _build_modal():
    """Build and return the Timer modal component."""
    from enzyme_tk_app.app.tools.timer_tool_template.modal import modal  # noqa: PLC0415

    return modal()


def test_modal_returns_dbc_modal():
    """modal() must return a dbc.Modal."""
    m = _build_modal()
    assert isinstance(m, dbc.Modal)


def test_modal_id_follows_convention():
    """The modal ID must be 'id-modal-timer-tool-template'."""
    m = _build_modal()
    assert m.id == f"id-modal-{TOOL_DEF['slug']}"


def test_modal_is_large_and_centered():
    """The modal must use size='lg' and centered=True per create-modal agent."""
    m = _build_modal()
    assert m.size == "lg"
    assert m.centered is True


def test_modal_body_has_p4_class():
    """ModalBody must include className='p-4' per create-modal agent."""
    m = _build_modal()
    bodies = find_components(m, dbc.ModalBody)
    assert len(bodies) == 1
    assert "p-4" in (bodies[0].className or "")


def test_modal_has_two_sections():
    """The modal body must contain two bg-light sections."""
    m = _build_modal()
    body = find_components(m, dbc.ModalBody)[0]
    # Sections are html.Div children with className containing "bg-light"
    sections = [
        child
        for child in (body.children or [])
        if isinstance(child, html.Div) and "bg-light" in (getattr(child, "className", "") or "")
    ]
    assert len(sections) == 2, f"Expected 2 bg-light sections, found {len(sections)}"


def test_modal_section_headers_exist():
    """Each section must have an H6 header with uppercase class."""
    m = _build_modal()
    headers = find_components(m, html.H6)
    assert len(headers) >= 2, "Expected at least 2 section headers (H6)"
    for h in headers:
        assert "text-uppercase" in (h.className or ""), f"Header missing text-uppercase: {get_text(h)}"


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


def test_modal_contains_results_div():
    """The modal must contain a results placeholder div."""
    m = _build_modal()
    divs = find_components(m, html.Div)
    result_divs = [d for d in divs if getattr(d, "id", None) == f"id-div-{TOOL_DEF['slug']}-results"]
    assert len(result_divs) == 1


def test_modal_footer_has_two_buttons():
    """The footer must have exactly two buttons: Close and Start Timer."""
    m = _build_modal()
    footer = find_components(m, dbc.ModalFooter)[0]
    buttons = find_components(footer, dbc.Button)
    assert len(buttons) == 2
    # First button is Close (secondary outline), second is Submit (primary)
    assert buttons[0].color == "secondary"
    assert buttons[1].color == "primary"


def test_modal_all_controls_have_themed_class():
    """Every form control must include the 'themed-control' CSS class."""
    m = _build_modal()
    # Check Input, RadioItems, Checkbox
    for component_type in (dbc.Input, dbc.RadioItems, dbc.Checkbox):
        controls = find_components(m, component_type)
        for ctrl in controls:
            class_name = getattr(ctrl, "className", "") or ""
            assert "themed-control" in class_name, (
                f"{type(ctrl).__name__} (id={getattr(ctrl, 'id', '?')}) missing 'themed-control'"
            )


def test_modal_title_comes_from_tool_def():
    """The modal header must display TOOL_DEF['title']."""
    m = _build_modal()
    # ModalTitle is nested inside ModalHeader; its children list
    # contains an html.I icon and the title string.
    titles = find_components(m, dbc.ModalTitle)
    assert len(titles) == 1
    title_children = titles[0].children
    # The title string is the last child (after the icon element)
    assert TOOL_DEF["title"] in title_children


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
    """Re-opening the modal must clear the stale results placeholder."""
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = f"id-btn-launch-{TOOL_DEF['slug']}"
        result = submit_timer_job(0, 1, 5, False)
    assert result == ""


@pytest.mark.parametrize(
    "duration, expected_fragment",
    [
        ("abc", "Invalid"),
        (None, "Invalid"),
        (0, "between 1 and 300"),
        (-1, "between 1 and 300"),
        (301, "between 1 and 300"),
        (999, "between 1 and 300"),
    ],
    ids=["non-numeric", "none", "zero", "negative", "over-max", "way-over-max"],
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
    """When simulate_failure is True, the confirmation message should note it."""
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


# ---------------------------------------------------------------------------
# Compute function
# ---------------------------------------------------------------------------


def test_compute_run_returns_expected_keys():
    """compute.run() must return _meta, _params_exclude, dataframe, and scalars."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    # Use 0 seconds to avoid sleeping
    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1, "simulate_failure": False})

    assert "_meta" in result, "Result must contain '_meta' for stat cards"
    assert "_params_exclude" in result, "Result must contain '_params_exclude'"
    assert "dataframe" in result, "Result must contain 'dataframe'"
    assert "requested_seconds" in result
    assert "actual_elapsed" in result


def test_compute_run_meta_is_list_of_dicts():
    """_meta must be a list of dicts with 'label' and 'value' keys."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    meta = result["_meta"]
    assert isinstance(meta, list)
    assert len(meta) >= 2, "Expected at least 2 meta items"
    for item in meta:
        assert "label" in item, f"Meta item missing 'label': {item}"
        assert "value" in item, f"Meta item missing 'value': {item}"


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


def test_generate_random_dataframe_columns():
    """The generated DataFrame must have the expected column names."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import _generate_random_dataframe  # noqa: PLC0415

    df = _generate_random_dataframe(n_rows=3)
    expected_cols = {"sample_id", "activity_score", "stability_score", "temperature_c", "yield_pct"}
    assert set(df.columns) == expected_cols


def test_generate_random_dataframe_id_format():
    """Each sample_id must match the pattern PREFIX-NNN."""
    import re  # noqa: PLC0415

    from enzyme_tk_app.app.tools.timer_tool_template.compute import _generate_random_dataframe  # noqa: PLC0415

    df = _generate_random_dataframe(n_rows=10)
    pattern = re.compile(r"^(ENZ|MUT|WT|VAR)-\d{3}$")
    for sample_id in df["sample_id"]:
        assert pattern.match(sample_id), f"Unexpected sample_id format: {sample_id}"


# ---------------------------------------------------------------------------
# Results layout
# ---------------------------------------------------------------------------


def test_results_layout_with_valid_dataframe():
    """results_layout must render a DataTable when dataframe data is present."""
    from dash import dash_table  # noqa: PLC0415

    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    job = make_job(
        result={
            "dataframe": {
                "columns": ["sample_id", "activity_score"],
                "data": [
                    {"sample_id": "ENZ-001", "activity_score": 42.5},
                    {"sample_id": "MUT-002", "activity_score": 88.1},
                ],
            },
        },
    )
    layout = results_layout(job)
    assert isinstance(layout, html.Div)
    tables = find_components(layout, dash_table.DataTable)
    assert len(tables) == 1, "Expected exactly one DataTable"
    assert len(tables[0].data) == 2


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


# ── Compute — JSON serialisability contract ──────────────────────────────


def test_compute_result_is_json_serialisable():
    """The entire return dict must be JSON-serialisable — backend requirement.

    Large results are offloaded to disk as JSON; if the dict contains
    non-serialisable objects (e.g. bare datetime, numpy arrays) the
    pipeline breaks silently.
    """
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 5, "simulate_failure": False})

    # json.dumps will raise TypeError for non-serialisable values.
    serialised = json.dumps(result)
    assert isinstance(serialised, str)


# ── Compute — meta values are consistent with scalar values ─────────────


def test_compute_meta_timer_label_matches_requested_seconds():
    """The 'Timer Set to' meta card must reflect the requested_seconds scalar."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 42})

    meta_timer = next(m for m in result["_meta"] if m["label"] == "Timer Set to")
    assert meta_timer["value"] == "42s"
    assert result["requested_seconds"] == 42


def test_compute_meta_rows_generated_matches_dataframe_length():
    """The 'Rows Generated' meta card must match the actual data row count."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    meta_rows = next(m for m in result["_meta"] if m["label"] == "Rows Generated")
    actual_rows = len(result["dataframe"]["data"])
    assert meta_rows["value"] == str(actual_rows)


# ── Compute — _params_exclude hides simulate_failure ─────────────────────


def test_compute_params_exclude_hides_simulate_failure():
    """simulate_failure is a developer flag and must be excluded from result display."""
    from enzyme_tk_app.app.tools.timer_tool_template.compute import run  # noqa: PLC0415

    with patch("enzyme_tk_app.app.tools.timer_tool_template.compute.time.sleep"):
        result = run({"seconds": 1})

    assert "simulate_failure" in result["_params_exclude"]


# ── Compute — DataFrame value ranges ─────────────────────────────────────


def test_compute_dataframe_value_ranges():
    """Generated data values must stay within documented bounds.

    The random generator produces:
    - activity_score:   0.5 – 150.0
    - stability_score: 35.0 – 85.0
    - temperature_c:     20 – 80
    - yield_pct:        5.0 – 98.0
    """
    from enzyme_tk_app.app.tools.timer_tool_template.compute import _generate_random_dataframe  # noqa: PLC0415

    # Generate many rows to increase the chance of catching an out-of-range bug.
    df = _generate_random_dataframe(n_rows=200)

    assert df["activity_score"].between(0.5, 150.0).all()
    assert df["stability_score"].between(35.0, 85.0).all()
    assert df["temperature_c"].between(20, 80).all()
    assert df["yield_pct"].between(5.0, 98.0).all()


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


def test_submit_truncates_float_duration():
    """A float duration like 5.7 should be truncated to 5 (int conversion)."""
    from enzyme_tk_app.app.app import server  # noqa: PLC0415
    from enzyme_tk_app.app.tools.timer_tool_template.callbacks import submit_timer_job  # noqa: PLC0415

    mock_scheduler = MagicMock()
    mock_scheduler.submit_job.return_value = "job-float"

    with server.test_request_context():
        from flask import g  # noqa: PLC0415

        g.session_id = "sess-float"
        with (
            patch("enzyme_tk_app.app.tools.timer_tool_template.callbacks.ctx") as mock_ctx,
            patch(
                "enzyme_tk_app.app.tools.timer_tool_template.callbacks.get_task_scheduler",
                return_value=mock_scheduler,
            ),
        ):
            mock_ctx.triggered_id = f"id-btn-{TOOL_DEF['slug']}-submit"
            result = submit_timer_job(1, 0, 5.7, False)

    # int(5.7) = 5, so the job should be submitted with seconds=5
    call_kwargs = mock_scheduler.submit_job.call_args[1]
    assert call_kwargs["params"]["seconds"] == 5
    assert "job-float" in result


# ── Results — DataTable configuration ────────────────────────────────────


def test_results_datatable_has_sorting_and_filtering():
    """The DataTable must enable native sorting and filtering for interactivity."""
    from dash import dash_table  # noqa: PLC0415

    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    job = make_job(
        result={
            "dataframe": {
                "columns": ["sample_id", "activity_score"],
                "data": [{"sample_id": "ENZ-001", "activity_score": 42.5}],
            },
        },
    )
    layout = results_layout(job)
    tables = find_components(layout, dash_table.DataTable)
    assert len(tables) == 1
    table = tables[0]

    assert table.sort_action == "native", "Sort must be enabled"
    assert table.filter_action == "native", "Filter must be enabled"
    assert table.page_size == 10, "Page size should default to 10"


def test_results_datatable_uses_shared_style_constants():
    """The DataTable must use shared TABLE_STYLE_* constants for consistent theming."""
    from dash import dash_table  # noqa: PLC0415

    from enzyme_tk_app.app.components.results_helpers import (  # noqa: PLC0415
        TABLE_STYLE_CELL,
        TABLE_STYLE_DATA_CONDITIONAL,
        TABLE_STYLE_HEADER,
        TABLE_STYLE_TABLE,
    )
    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    job = make_job(
        result={
            "dataframe": {
                "columns": ["col_a"],
                "data": [{"col_a": 1}],
            },
        },
    )
    layout = results_layout(job)
    table = find_components(layout, dash_table.DataTable)[0]

    assert table.style_table == TABLE_STYLE_TABLE
    assert table.style_header == TABLE_STYLE_HEADER
    assert table.style_cell == TABLE_STYLE_CELL
    assert table.style_data_conditional == TABLE_STYLE_DATA_CONDITIONAL


def test_results_datatable_column_ids_match_data_keys():
    """Each DataTable column 'id' must match the keys in the data rows."""
    from dash import dash_table  # noqa: PLC0415

    from enzyme_tk_app.app.tools.timer_tool_template.results import results_layout  # noqa: PLC0415

    cols = ["sample_id", "activity_score", "yield_pct"]
    job = make_job(
        result={
            "dataframe": {
                "columns": cols,
                "data": [{"sample_id": "A", "activity_score": 1.0, "yield_pct": 50.0}],
            },
        },
    )
    layout = results_layout(job)
    table = find_components(layout, dash_table.DataTable)[0]

    col_ids = [c["id"] for c in table.columns]
    assert col_ids == cols, "Column IDs must match the column names from compute output"


# ── Results — partial / malformed dataframe payload ──────────────────────
# (covered by test_results_layout_shows_fallback_for_bad_payload above)


# ── Modal — default values are sensible ──────────────────────────────────


def test_modal_duration_input_defaults():
    """The duration input must have sensible defaults: value=5, min=1, max=300, step=1."""
    m = _build_modal()
    inputs = find_components(m, dbc.Input)
    duration_input = next(i for i in inputs if i.id == f"id-input-{TOOL_DEF['slug']}-duration")

    assert duration_input.value == 5, "Default duration should be 5 seconds"
    assert duration_input.min == 1, "Minimum should be 1 second"
    assert duration_input.max == 300, "Maximum should be 300 seconds"
    assert duration_input.step == 1, "Step should be 1 second"


def test_modal_quick_select_default_matches_duration_input():
    """The quick-select radio default must match the duration input default."""
    m = _build_modal()
    inputs = find_components(m, dbc.Input)
    duration_input = next(i for i in inputs if i.id == f"id-input-{TOOL_DEF['slug']}-duration")

    radios = find_components(m, dbc.RadioItems)
    quick_radio = next(r for r in radios if r.id == f"id-radio-{TOOL_DEF['slug']}-quick")

    assert quick_radio.value == duration_input.value, (
        "Quick-select default must match duration input default to avoid confusing the user"
    )


def test_modal_simulate_failure_defaults_to_off():
    """The simulate-failure checkbox must default to False (unchecked)."""
    m = _build_modal()
    checks = find_components(m, dbc.Checkbox)
    fail_check = next(c for c in checks if c.id == f"id-check-{TOOL_DEF['slug']}-fail")
    assert fail_check.value is False
