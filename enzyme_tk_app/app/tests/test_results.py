from dash import html

from enzyme_tk_app.app.components.results_helpers import (
    _pretty_label,
    build_result_input_params,
    build_result_stat_cards,
)

from .conftest import find_components, get_text, make_job

# ---------------------------------------------------------------------------
# build_result_stat_cards
# ---------------------------------------------------------------------------


def test_build_result_stat_cards_returns_none_when_no_stat_cards():
    """Jobs without a ``_stat_cards`` key in the result should produce ``None``."""
    assert build_result_stat_cards(make_job(result={"data": [1, 2]})) is None


def test_build_result_stat_cards_returns_none_when_result_is_none():
    """A job with ``result=None`` should not crash and should return ``None``."""
    assert build_result_stat_cards(make_job(result=None)) is None


def test_build_result_stat_cards_returns_none_for_non_list_stat_cards():
    """``_stat_cards`` must be a list; a string or dict should be treated as absent."""
    assert build_result_stat_cards(make_job(result={"_stat_cards": "not-a-list"})) is None
    assert build_result_stat_cards(make_job(result={"_stat_cards": {"label": "x", "value": "y"}})) is None


def test_build_result_stat_cards_returns_none_for_empty_stat_cards_list():
    """An empty ``_stat_cards`` list produces no cards, so the helper returns ``None``."""
    assert build_result_stat_cards(make_job(result={"_stat_cards": []})) is None


def test_build_result_stat_cards_renders_stat_cards():
    """Each dict in ``_stat_cards`` should produce a stat card with the correct label, value, and count."""
    meta = [
        {"label": "Elapsed", "value": "12.3 s"},
        {"label": "Matches", "value": "42"},
    ]
    component = build_result_stat_cards(make_job(result={"_stat_cards": meta}))

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


def test_build_result_stat_cards_uses_shared_css_classes():
    """The output must use the shared ``jobs-stats-row`` / ``jobs-stat-card`` classes."""
    meta = [{"label": "L", "value": "V"}]
    component = build_result_stat_cards(make_job(result={"_stat_cards": meta}))

    stats_row = [c for c in find_components(component, html.Div) if getattr(c, "className", None) == "jobs-stats-row"]
    assert len(stats_row) == 1, "Expected exactly one jobs-stats-row container"


def test_build_result_stat_cards_skips_non_dict_items():
    """Non-dict entries in ``_stat_cards`` should be silently ignored."""
    meta = [{"label": "Keep", "value": "1"}, "stray-string", 42, None]
    component = build_result_stat_cards(make_job(result={"_stat_cards": meta}))

    cards = [c for c in find_components(component, html.Div) if getattr(c, "className", None) == "jobs-stat-card"]
    assert len(cards) == 1


def test_build_result_stat_cards_returns_none_when_all_items_are_non_dict():
    """If every item in ``_stat_cards`` is non-dict, the result should be ``None``."""
    assert build_result_stat_cards(make_job(result={"_stat_cards": ["a", 1, None]})) is None


def test_build_result_stat_cards_handles_missing_label_or_value_keys():
    """Items missing ``label`` or ``value`` should still render (empty string fallback)."""
    meta = [{"label": "OnlyLabel"}, {"value": "OnlyValue"}, {}]
    component = build_result_stat_cards(make_job(result={"_stat_cards": meta}))

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
    """Framework-internal keys (``_stat_cards``, ``_params_exclude``) must never appear."""
    params = {"visible": "yes", "_stat_cards": "hidden", "_params_exclude": "hidden"}
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
    params = {"_stat_cards": "x"}
    assert build_result_input_params(make_job(params=params)) is None


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
