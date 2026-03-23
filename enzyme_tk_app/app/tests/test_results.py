from dash import html

from enzyme_tk_app.app.components.results_helpers import (
    _LONG_VALUE_THRESHOLD,
    _pretty_label,
    build_result_input_params,
    build_result_meta,
)

from .conftest import find_components, get_text, make_job

# ---------------------------------------------------------------------------
# build_result_meta
# ---------------------------------------------------------------------------


def test_build_result_meta_returns_none_when_no_meta():
    """Jobs without a ``_meta`` key in the result should produce ``None``."""
    assert build_result_meta(make_job(result={"data": [1, 2]})) is None


def test_build_result_meta_returns_none_when_result_is_none():
    """A job with ``result=None`` should not crash and should return ``None``."""
    assert build_result_meta(make_job(result=None)) is None


def test_build_result_meta_returns_none_for_non_list_meta():
    """``_meta`` must be a list; a string or dict should be treated as absent."""
    assert build_result_meta(make_job(result={"_meta": "not-a-list"})) is None
    assert build_result_meta(make_job(result={"_meta": {"label": "x", "value": "y"}})) is None


def test_build_result_meta_returns_none_for_empty_meta_list():
    """An empty ``_meta`` list produces no cards, so the helper returns ``None``."""
    assert build_result_meta(make_job(result={"_meta": []})) is None


def test_build_result_meta_renders_stat_cards():
    """Each dict in ``_meta`` should produce a stat card with the correct label, value, and count."""
    meta = [
        {"label": "Elapsed", "value": "12.3 s"},
        {"label": "Matches", "value": "42"},
    ]
    component = build_result_meta(make_job(result={"_meta": meta}))

    assert component is not None
    text = get_text(component)
    assert "Summary" in text
    assert "Elapsed" in text
    assert "12.3 s" in text
    assert "Matches" in text
    assert "42" in text

    # Card count must match the number of meta items.
    cards = [c for c in find_components(component, html.Div) if getattr(c, "className", None) == "jobs-stat-card"]
    assert len(cards) == 2


def test_build_result_meta_uses_shared_css_classes():
    """The output must use the shared ``jobs-stats-row`` / ``jobs-stat-card`` classes."""
    meta = [{"label": "L", "value": "V"}]
    component = build_result_meta(make_job(result={"_meta": meta}))

    stats_row = [c for c in find_components(component, html.Div) if getattr(c, "className", None) == "jobs-stats-row"]
    assert len(stats_row) == 1, "Expected exactly one jobs-stats-row container"


def test_build_result_meta_skips_non_dict_items():
    """Non-dict entries in ``_meta`` should be silently ignored."""
    meta = [{"label": "Keep", "value": "1"}, "stray-string", 42, None]
    component = build_result_meta(make_job(result={"_meta": meta}))

    cards = [c for c in find_components(component, html.Div) if getattr(c, "className", None) == "jobs-stat-card"]
    assert len(cards) == 1


def test_build_result_meta_returns_none_when_all_items_are_non_dict():
    """If every item in ``_meta`` is non-dict, the result should be ``None``."""
    assert build_result_meta(make_job(result={"_meta": ["a", 1, None]})) is None


def test_build_result_meta_handles_missing_label_or_value_keys():
    """Items missing ``label`` or ``value`` should still render (empty string fallback)."""
    meta = [{"label": "OnlyLabel"}, {"value": "OnlyValue"}, {}]
    component = build_result_meta(make_job(result={"_meta": meta}))

    assert component is not None
    text = get_text(component)
    assert "OnlyLabel" in text
    assert "OnlyValue" in text


# ---------------------------------------------------------------------------
# build_result_input_params
# ---------------------------------------------------------------------------


def test_build_input_params_returns_none_for_empty_params():
    """No params → ``None``; the section should not render at all."""
    assert build_result_input_params(make_job(params={})) is None


def test_build_input_params_returns_none_when_params_is_none():
    """``params=None`` (e.g. if the job was never submitted) → ``None``."""
    job = make_job()
    job.params = None  # type: ignore[assignment]
    assert build_result_input_params(job) is None


def test_build_input_params_renders_label_value_rows():
    """Each parameter should appear as a human-friendly label with its value, one row per param."""
    params = {"protein_sequence": "MKFL", "temperature": "37"}
    component = build_result_input_params(make_job(params=params))

    assert component is not None
    text = get_text(component)
    assert "Input Parameters" in text
    assert "Protein Sequence" in text
    assert "MKFL" in text
    assert "Temperature" in text
    assert "37" in text

    # Row count must match the number of visible parameters.
    rows = find_components(component, html.Tr)
    assert len(rows) == 2


def test_build_input_params_hides_internal_keys():
    """Framework-internal keys (``_meta``, ``_params_exclude``) must never appear."""
    params = {"visible": "yes", "_meta": "hidden", "_params_exclude": "hidden"}
    component = build_result_input_params(make_job(params=params))

    text = get_text(component)
    assert "Visible" in text
    # Internal keys must not produce any table row.
    rows = find_components(component, html.Tr)
    assert len(rows) == 1


def test_build_input_params_respects_params_exclude_from_result():
    """Tool-specified ``_params_exclude`` in the result dict should suppress those params."""
    params = {"keep_me": "yes", "hide_me": "secret"}
    result = {"_params_exclude": ["hide_me"]}
    component = build_result_input_params(make_job(params=params, result=result))

    text = get_text(component)
    assert "Keep Me" in text
    assert "secret" not in text

    rows = find_components(component, html.Tr)
    assert len(rows) == 1


def test_build_input_params_returns_none_when_all_params_excluded():
    """If every parameter is excluded, the section should not render."""
    params = {"_meta": "x"}
    assert build_result_input_params(make_job(params=params)) is None


def test_build_input_params_value_class_depends_on_length():
    """Short values get ``jobs-params-value``; values at or above the threshold get ``jobs-params-value-long``."""
    short_val = "short"
    exact_val = "B" * _LONG_VALUE_THRESHOLD  # exactly at threshold → long
    over_val = "A" * (_LONG_VALUE_THRESHOLD + 1)  # above threshold → long

    # Short value → plain class.
    short_component = build_result_input_params(make_job(params={"name": short_val}))
    plain_cells = [
        c for c in find_components(short_component, html.Td) if getattr(c, "className", None) == "jobs-params-value"
    ]
    assert len(plain_cells) == 1

    # Value at exact threshold → long class.
    exact_component = build_result_input_params(make_job(params={"seq": exact_val}))
    long_exact = [
        c
        for c in find_components(exact_component, html.Td)
        if getattr(c, "className", None) == "jobs-params-value-long"
    ]
    assert len(long_exact) == 1

    # Value above threshold → long class.
    over_component = build_result_input_params(make_job(params={"seq": over_val}))
    long_over = [
        c for c in find_components(over_component, html.Td) if getattr(c, "className", None) == "jobs-params-value-long"
    ]
    assert len(long_over) == 1


def test_build_input_params_non_string_values_are_stringified():
    """Non-string param values (ints, lists, bools) should be converted to strings."""
    params = {"count": 42, "active": True, "tags": ["a", "b"]}
    component = build_result_input_params(make_job(params=params))

    text = get_text(component)
    assert "42" in text
    assert "True" in text
    assert "['a', 'b']" in text


# ---------------------------------------------------------------------------
# _pretty_label — internal helper
# ---------------------------------------------------------------------------


def test_pretty_label_snake_case():
    """``protein_sequence`` → ``Protein Sequence``."""
    assert _pretty_label("protein_sequence") == "Protein Sequence"


def test_pretty_label_kebab_case():
    """``max-duration`` → ``Max Duration``."""
    assert _pretty_label("max-duration") == "Max Duration"


def test_pretty_label_single_word():
    """A single-word key should just be title-cased."""
    assert _pretty_label("temperature") == "Temperature"


def test_pretty_label_already_titlecase():
    """Already well-formatted keys should pass through unchanged."""
    assert _pretty_label("Name") == "Name"
