"""Tests for ``utils/data_availability.py`` — the one answer the card and the modal share.

``check_tool_data(slug)`` runs a tool's registered checks and splits what they say
into *blocking* (the tool cannot run) and *warnings* (something is unusable but the
tool runs anyway).  ``validate_tool_data(slug)`` turns only the blocking half into
a message, in the message-or-``None`` shape every other submit-path validator uses.

Two failure modes these tests exist for: an advisory item that ends up blocking
switches off a tool that works, and a check that raises must never take the home
page or a modal with it.

The checks are registered through ``conftest.patch_tool_checks``, which patches the
registries on ``enzyme_tk_app.app.tools`` — the dicts ``check_tool_data`` imports
inside itself on every call.
"""

from pathlib import Path

import pytest

from enzyme_tk_app.app.utils.data_availability import (
    CHECK_FAILED_LABEL,
    CHECK_FAILED_MESSAGE,
    DOWNLOAD_SCRIPT,
    check_tool_data,
    missing_data_paths,
    validate_tool_data,
)

from .conftest import patch_tool_checks

SLUG = "demo-tool"


def _raises():
    """A registered check with a bug in it."""
    raise RuntimeError("boom")


# ── check_tool_data ─────────────────────────────────────────────────────────────


def test_a_tool_with_no_registered_check_reports_nothing(monkeypatch):
    """A tool with no ``check_data.py`` has no data dependencies and is never gated.

    Registering checks under another slug is what that looks like from here — the
    lookup must miss rather than pick up a neighbour's answer.
    """
    patch_tool_checks(monkeypatch, "another-tool", blocking=["something"], warnings=["something else"])

    assert check_tool_data(SLUG) == ([], [])


def test_the_two_channels_come_back_separately(monkeypatch):
    """Blocking and advisory labels must not be merged, and must not swap places.

    Everything downstream reads the difference: the badge's colour, whether the
    card shows a note, and whether Run is disabled at all.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=["a missing database"], warnings=["bad.csv skipped"])

    blocking, warnings = check_tool_data(SLUG)

    assert blocking == ["a missing database"], (
        f"{SLUG}: an advisory label reaching the blocking channel disables a working tool"
    )
    assert warnings == ["bad.csv skipped"], (
        f"{SLUG}: a blocking label reaching the advisory channel leaves Run enabled with no data"
    )


# ── validate_tool_data ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("registered_slug", "blocking", "warnings"),
    [
        ("another-tool", ["something"], []),
        (SLUG, [], []),
        (SLUG, [], ["bad.csv — missing columns: EC number"]),
    ],
    ids=["no-check-registered", "check-reports-nothing", "advisory-only"],
)
def test_nothing_blocking_means_the_tool_can_run(monkeypatch, registered_slug, blocking, warnings):
    """``None`` is "submit away" — and an advisory item must not withhold it.

    The advisory case is the one that matters: one malformed file beside a usable
    database is a tool that works, and a message here would disable it.
    """
    patch_tool_checks(monkeypatch, registered_slug, blocking=blocking, warnings=warnings)

    assert validate_tool_data(SLUG) is None


def test_the_message_names_every_missing_path_and_the_script(monkeypatch):
    """A blocked tool gets one message naming what to fetch and how to fetch it.

    Both missing items are named — reporting only the first would send the user
    through the download twice — and the script is what makes the message
    actionable instead of an apology.
    """
    patch_tool_checks(
        monkeypatch,
        SLUG,
        blocking=["Reaction database CSVs (data/reactions/*.csv)", "UniMol weights (data/unimol_weights/)"],
    )

    message = validate_tool_data(SLUG)

    assert "data/reactions/*.csv" in message
    assert "data/unimol_weights/" in message
    assert DOWNLOAD_SCRIPT in message


def test_the_download_script_the_message_names_exists():
    """The script the message sends people to must actually be in the repo.

    Nothing imports it — it ships in its own image — so a rename would leave every
    blocked tool printing instructions that go nowhere, with no other test failing.
    """
    repo_root = Path(__file__).resolve().parents[3]

    assert (repo_root / DOWNLOAD_SCRIPT).is_file(), f"{DOWNLOAD_SCRIPT} is named in the UI but not in the repo"


# ── missing_data_paths ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Reaction database CSVs (data/reactions/*.csv)", "data/reactions/*.csv"),
        (
            "Sequence databases (data/sequences/*.csv, *.tsv) with columns Entry, Sequence, EC number",
            "data/sequences/*.csv, *.tsv",
        ),
        ("ProstT5 model weights (downloaded separately)", "ProstT5 model weights (downloaded separately)"),
        ("Something with no parentheses at all", "Something with no parentheses at all"),
    ],
    ids=["path-at-the-end", "path-mid-label", "parenthetical-without-a-path", "no-parentheses"],
)
def test_the_path_is_lifted_out_of_a_label_when_there_is_one(label, expected):
    """The note and the modal message want the path; the tooltip keeps the full label.

    The last two cases are the fallback: a future tool may word its check without a
    parenthetical path, and saying too much beats a card that says nothing at all.
    """
    assert missing_data_paths([label]) == [expected]


# ── A check with a bug in it ────────────────────────────────────────────────────


def test_a_raising_blocking_check_is_reported_not_propagated(monkeypatch, caplog):
    """A broken check must surface as a message, never as an exception.

    The app installs no Dash ``on_error`` handler, so an exception escaping here is
    an HTTP 500 on the submit round-trip instead of a line in the modal — and on the
    home page it would take out the whole card grid.  It is treated as blocking
    because what the data looks like is precisely what is unknown.  The log entry is
    the only place the real traceback survives, so it names the tool.
    """
    patch_tool_checks(monkeypatch, SLUG, blocking=_raises)

    with caplog.at_level("WARNING"):
        blocking, _warnings = check_tool_data(SLUG)
        message = validate_tool_data(SLUG)

    assert blocking == [CHECK_FAILED_LABEL]
    assert message == CHECK_FAILED_MESSAGE
    assert DOWNLOAD_SCRIPT not in message, "Downloading data does not fix a check that raises"
    assert any(SLUG in record.message for record in caplog.records), (
        f"The traceback for {SLUG}'s broken check was swallowed without a log entry"
    )


def test_a_raising_advisory_check_does_not_block_the_tool(monkeypatch):
    """A bug in the *advisory* check must not switch off a tool that runs.

    The two channels are run by the same defensive helper, so it would be easy for
    a failure in the optional one to be reported as though the data were missing.
    """
    patch_tool_checks(monkeypatch, SLUG, warnings=_raises)

    blocking, warnings = check_tool_data(SLUG)

    assert blocking == []
    assert warnings == [CHECK_FAILED_LABEL]
    assert validate_tool_data(SLUG) is None
