"""Tests for enzyme_tk_app.app.utils.formatting.

Covers the four public helpers: format_timestamp, compute_duration,
format_duration, and expires_in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from enzyme_tk_app.app.utils.formatting import (
    compute_duration,
    expires_in,
    format_duration,
    format_timestamp,
)

# ── format_timestamp ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("iso_str", "expected"),
    [
        ("2026-03-25T14:32:10", "2026-03-25 14:32"),
        ("2026-03-25T14:32:10+00:00", "2026-03-25 14:32"),
        ("2026-01-01T00:00:00", "2026-01-01 00:00"),
    ],
    ids=["naive", "tz-aware", "midnight"],
)
def test_format_timestamp_valid(iso_str, expected):
    """Well-formed ISO strings are formatted as 'YYYY-MM-DD HH:MM'."""
    assert format_timestamp(iso_str) == expected


@pytest.mark.parametrize(
    ("iso_str", "expected"),
    [
        (None, "—"),
        ("", "—"),
        ("not-a-date", "not-a-date"),
    ],
    ids=["none", "empty", "invalid"],
)
def test_format_timestamp_fallback(iso_str, expected):
    """None/empty returns em-dash; unparseable strings are returned as-is."""
    assert format_timestamp(iso_str) == expected


# ── format_duration ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (5, "5s"),
        (59, "59s"),
        (120, "2m"),
        (150, "2m"),
        (3600, "1h 0m"),
        (3660, "1h 1m"),
        (7200, "2h 0m"),
        (5400, "1h 30m"),
    ],
    ids=["0s", "5s", "59s", "2m", "2m-30s-rounded", "1h", "1h1m", "2h", "1h30m"],
)
def test_format_duration_rounded(seconds, expected):
    """Default (non-precise) mode rounds to the nearest whole unit."""
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "0.0s"),
        (5.3, "5.3s"),
        (59.9, "59.9s"),
        (120, "2m 0s"),
        (135, "2m 15s"),
    ],
    ids=["0.0s", "5.3s", "59.9s", "2m-0s", "2m-15s"],
)
def test_format_duration_precise(seconds, expected):
    """Precise mode keeps fractional seconds and shows seconds in minutes range."""
    assert format_duration(seconds, precise=True) == expected


# ── compute_duration ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("started", "completed", "expected"),
    [
        ("2026-03-25T10:00:00", "2026-03-25T10:00:05.3", "5.3s"),
        ("2026-03-25T10:00:00", "2026-03-25T10:02:15", "2m 15s"),
        ("2026-03-25T10:00:00", "2026-03-25T10:00:00", "0.0s"),
    ],
    ids=["seconds", "minutes", "zero"],
)
def test_compute_duration_valid(started, completed, expected):
    """Valid timestamp pairs produce a human-readable duration string."""
    assert compute_duration(started, completed) == expected


@pytest.mark.parametrize(
    ("started", "completed"),
    [
        (None, "2026-03-25T10:00:05"),
        ("2026-03-25T10:00:00", None),
        (None, None),
        ("", "2026-03-25T10:00:05"),
        ("bad", "also-bad"),
        ("2026-03-25T10:05:00", "2026-03-25T10:00:00"),
    ],
    ids=["no-start", "no-end", "both-none", "empty-start", "invalid", "negative"],
)
def test_compute_duration_returns_dash(started, completed):
    """Missing, invalid, or negative inputs all return em-dash."""
    assert compute_duration(started, completed) == "—"


# ── expires_in ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "iso_str",
    [None, "", "garbage"],
    ids=["none", "empty", "invalid"],
)
def test_expires_in_returns_dash(iso_str):
    """None, empty, or unparseable input returns em-dash."""
    assert expires_in(iso_str) == "—"


def test_expires_in_recently_submitted():
    """A job submitted just now has nearly a full TTL remaining."""
    now = datetime.now(tz=timezone.utc)
    result = expires_in(now.isoformat())
    # Should show approximately 24 h (JOB_TTL_SECONDS defaults to 86400)
    assert "h" in result, f"Expected hours in result, got: {result}"


def test_expires_in_expired():
    """A job submitted more than JOB_TTL_SECONDS ago shows 'Expired'."""
    long_ago = datetime.now(tz=timezone.utc) - timedelta(days=2)
    assert expires_in(long_ago.isoformat()) == "Expired"


def test_expires_in_naive_timestamp():
    """Naive timestamps (no tzinfo) are treated as UTC."""
    one_hour_ago = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    naive_iso = one_hour_ago.strftime("%Y-%m-%dT%H:%M:%S")
    result = expires_in(naive_iso)
    assert "h" in result, f"Expected hours in result, got: {result}"
    assert result != "Expired"
