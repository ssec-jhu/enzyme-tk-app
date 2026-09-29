"""Tests for the ``data_warning`` component a tool card shows about its data.

``data_warning(slug)`` returns ``(badge, note, blocked)``.  Two badge states carry
two different meanings, and confusing them is the failure mode these tests exist
for: **blocking** (red) means the tool cannot run and its Run button is disabled,
**advisory** (amber) means one file in ``data/`` was skipped while the tool still
runs perfectly on the rest.

Patching note: the checks are reached through ``utils.data_availability``, which
imports ``CHECK_DATA`` / ``CHECK_DATA_WARNINGS`` *inside* ``check_tool_data`` on
every call — so patching an attribute on this component's own module does nothing.
``conftest.patch_tool_checks`` patches the source registries instead, which is the
one place that reaches the card, the Run gate and the submit guard together.
"""

import dash_bootstrap_components as dbc
import pytest
from dash import html

from enzyme_tk_app.app.components.data_warning import data_warning
from enzyme_tk_app.app.components.icons import ICON_DATA_ADVISORY, ICON_DATA_WARNING
from enzyme_tk_app.app.utils.data_availability import CHECK_FAILED_LABEL, CHECK_FAILED_MESSAGE, DOWNLOAD_SCRIPT

from .conftest import find_components, get_text, patch_tool_checks

SLUG = "demo-tool"

# The two states' CSS classes, as ``05-cards.css`` defines them.  The advisory badge
# keeps the base class and adds a modifier, so it inherits the pill's shape.
BLOCKING_CLASS = "card-data-badge"
ADVISORY_CLASS = "card-data-badge card-data-badge-advisory"


def _badge_span(component):
    """Return the single pill span inside a badge, found by its tooltip-target id."""
    spans = [s for s in find_components(component, html.Span) if getattr(s, "id", None) == f"id-data-warning-{SLUG}"]
    assert len(spans) == 1, f"Expected exactly one badge span, found {len(spans)}"
    return spans[0]


# ── Nothing to report ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("registered_slug", "blocking", "warnings"),
    [
        ("another-tool", ["something"], ["something else"]),
        (SLUG, [], []),
    ],
    ids=["no-check-registered", "checks-report-nothing"],
)
def test_nothing_is_rendered_when_there_is_nothing_to_report(monkeypatch, registered_slug, blocking, warnings):
    """A healthy tool card must carry no badge and no note at all.

    The first case registers the checks under a *different* slug, which is how a
    tool with no ``check_data.py`` looks to this component.
    """
    patch_tool_checks(monkeypatch, registered_slug, blocking=blocking, warnings=warnings)

    warning = data_warning(SLUG)

    assert warning.badge is None, f"{SLUG}: a card with nothing wrong still rendered a badge"
    assert warning.note is None, f"{SLUG}: a card with nothing wrong still rendered a note"
    assert warning.blocked is False


# ── Which badge, and what it says ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("blocking", "warnings", "expected_class", "expected_icon", "expected_blocked"),
    [
        (["a database"], [], BLOCKING_CLASS, ICON_DATA_WARNING, True),
        (["a database"], ["bad.csv skipped"], BLOCKING_CLASS, ICON_DATA_WARNING, True),
        ([], ["bad.csv skipped"], ADVISORY_CLASS, ICON_DATA_ADVISORY, False),
    ],
    ids=["blocking-only", "blocking-outranks-advisory", "advisory-only"],
)
def test_badge_state_separates_a_dead_tool_from_a_skipped_file(
    monkeypatch, blocking, warnings, expected_class, expected_icon, expected_blocked
):
    """The badge's class and icon must say which of the two situations this is.

    Asserted on the class rather than the wording because the class is what colours
    the pill: an advisory file rendered red reads as "this tool is broken", and a
    blocked tool rendered amber reads as "nothing to do here" — both lie about
    whether the Run button will work.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=blocking, warnings=warnings)

    warning = data_warning(SLUG)
    span = _badge_span(warning.badge)

    assert span.className == expected_class, (
        f"{SLUG}: badge colour contradicts whether Run works — blocking={blocking}, warnings={warnings}"
    )
    icons = find_components(warning.badge, html.I)
    assert [getattr(icon, "className", "") for icon in icons] == [expected_icon]
    assert warning.blocked is expected_blocked


@pytest.mark.parametrize(
    ("blocking", "warnings", "expected_text"),
    [
        (["a database"], [], "Missing data"),
        ([], ["bad.csv skipped"], "1 file skipped"),
        ([], ["bad.csv skipped", "worse.csv skipped"], "2 files skipped"),
    ],
    ids=["blocking", "one-file-skipped", "two-files-skipped"],
)
def test_badge_label_reads_correctly_at_a_glance(monkeypatch, blocking, warnings, expected_text):
    """The pill's own words are the summary; the tooltip has the detail.

    The count and its plural are the whole point of the advisory label — "1 files
    skipped" is the kind of thing a scientist screenshots into a bug report.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=blocking, warnings=warnings)

    assert expected_text in get_text(data_warning(SLUG).badge)


@pytest.mark.parametrize(
    ("blocking", "warnings"),
    [
        (["one missing database"], []),
        (["one missing database"], ["bad.csv — missing columns: EC number"]),
        ([], ["a.csv skipped", "b.csv skipped"]),
    ],
    ids=["blocking-only", "blocking-listed-before-warning", "warnings-only"],
)
def test_tooltip_lists_every_label_with_blocking_first(monkeypatch, blocking, warnings):
    """One tooltip line per reported label, what stops the tool before what annoys it.

    The order is the reading order: someone hovering a red badge wants the reason
    Run is dead, not a note about an unrelated file they can ignore.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=blocking, warnings=warnings)

    badge = data_warning(SLUG).badge
    listed = [get_text(item) for item in find_components(badge, html.Li)]

    assert listed == [*blocking, *warnings], f"{SLUG}: tooltip dropped or reordered a reported label"


def test_tooltip_is_anchored_to_the_badge(monkeypatch):
    """The tooltip is bound by ``target=``, so the id it names must be the badge's.

    Nothing else links the two — a renamed badge id leaves a tooltip that never
    opens, and no callback would fail to report it.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=["a database"])

    badge = data_warning(SLUG).badge
    tooltips = find_components(badge, dbc.Tooltip)

    assert len(tooltips) == 1
    assert tooltips[0].target == _badge_span(badge).id


# ── The visible note ────────────────────────────────────────────────────────────


def test_blocked_card_shows_a_note_naming_the_data_path_and_the_script(monkeypatch):
    """A blocked tool gets a *visible* line, not just a tooltip.

    A tooltip is invisible on a touch screen and easy to miss with a mouse, so the
    one case where the user has something to do — run the download script — says so
    on the card itself.  The note carries the ``data/`` path rather than the full
    label because the label is already in the tooltip directly above it.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=["Reaction databases (data/reactions/)"])

    warning = data_warning(SLUG)

    assert warning.note is not None, "A blocked tool must explain itself on the card"
    assert warning.note.className == "card-data-note"
    note_text = get_text(warning.note)
    assert "data/reactions/" in note_text
    assert DOWNLOAD_SCRIPT in note_text


def test_advisory_card_shows_no_note(monkeypatch):
    """An unusable file must not send the user to the download script.

    ``download_data.py`` fetches reference data; it is no remedy at all for a file
    with the wrong columns, and printing it here would send someone off to
    re-download several gigabytes over a typo in a header row.
    """
    patch_tool_checks(monkeypatch, SLUG, warnings=["bad.csv — missing columns: EC number"])

    assert data_warning(SLUG).note is None


# ── A check that raises ─────────────────────────────────────────────────────────


def test_a_raising_check_renders_the_blocking_badge(monkeypatch):
    """A broken check degrades to the red badge, never to silence.

    Whether the data is there is unknown at that point, and the Run gate reads the
    same fallback — a card that stayed quiet while Run was disabled would leave the
    user with a dead button and no explanation anywhere.  The note says the check
    broke instead of offering the download script, which would not fix it.
    """

    def raises():
        raise RuntimeError("boom")

    patch_tool_checks(monkeypatch, SLUG, blocking=raises)

    warning = data_warning(SLUG)

    assert warning.blocked is True
    assert _badge_span(warning.badge).className == BLOCKING_CLASS
    assert CHECK_FAILED_LABEL in get_text(warning.badge)
    assert get_text(warning.note) == CHECK_FAILED_MESSAGE
    assert DOWNLOAD_SCRIPT not in get_text(warning.note)
