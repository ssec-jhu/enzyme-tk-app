"""Tests for the reusable ``data_warning_badge`` component."""

import dash_bootstrap_components as dbc
import pytest
from dash import html

from enzyme_tk_app.app.components import data_warning as dw
from enzyme_tk_app.app.components.data_warning import data_warning_badge
from enzyme_tk_app.app.components.icons import ICON_DATA_WARNING

from .conftest import find_components, get_text


def test_returns_none_when_no_check_registered(monkeypatch):
    monkeypatch.setattr(dw, "CHECK_DATA", {})
    assert data_warning_badge("anything") is None


def test_returns_none_when_check_returns_empty_list(monkeypatch):
    monkeypatch.setattr(dw, "CHECK_DATA", {"foo": lambda: []})
    assert data_warning_badge("foo") is None


def test_returns_component_with_label_and_tooltip(monkeypatch):
    monkeypatch.setattr(dw, "CHECK_DATA", {"foo": lambda: ["thing one", "thing two"]})
    component = data_warning_badge("foo")
    assert component is not None

    text = get_text(component)
    assert "Missing data" in text
    assert "thing one" in text
    assert "thing two" in text

    # Warning icon present.
    icons = find_components(component, html.I)
    assert any(ICON_DATA_WARNING in (getattr(i, "className", "") or "") for i in icons)

    # Tooltip targets the badge id.
    tooltips = find_components(component, dbc.Tooltip)
    assert len(tooltips) == 1
    assert tooltips[0].target == "id-data-warning-foo"


def test_failing_check_renders_fallback_badge(monkeypatch, caplog):
    def raises():
        raise RuntimeError("boom")

    monkeypatch.setattr(dw, "CHECK_DATA", {"foo": raises})

    with caplog.at_level("WARNING"):
        component = data_warning_badge("foo")

    assert component is not None
    assert "Data check failed" in get_text(component)
    assert any("foo" in rec.message for rec in caplog.records)


@pytest.mark.parametrize("missing", [["a"], ["a", "b", "c"]])
def test_one_list_item_per_missing_label(monkeypatch, missing):
    monkeypatch.setattr(dw, "CHECK_DATA", {"foo": lambda: missing})
    component = data_warning_badge("foo")
    list_items = find_components(component, html.Li)
    assert len(list_items) == len(missing)
