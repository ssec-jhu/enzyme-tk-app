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
        (None, "—"),
        ("", "—"),
        ("not-a-date", "not-a-date"),
    ],
)
def test_format_timestamp_valid(iso_str, expected):
    """Well-formed ISO strings are formatted as 'YYYY-MM-DD HH:MM'."""
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

# Fixed reference point and TTL used by all expires_in tests.
# Passed via keyword args (dependency injection) — no mocking needed.
_NOW = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
_TTL = 86400  # 24 h


@pytest.mark.parametrize(
    "iso_str",
    [None, "", "garbage"],
    ids=["none", "empty", "invalid"],
)
def test_expires_in_returns_dash(iso_str):
    """None, empty input returns em-dash."""
    assert expires_in(iso_str) == "—"


def test_expires_in_recently_submitted():
    """A job submitted at 'now' has a full 24 h TTL remaining."""
    assert expires_in(_NOW.isoformat(), now=_NOW, ttl=_TTL) == "24h 0m"


def test_expires_in_expired():
    """A job submitted more than TTL seconds ago shows 'Expired'."""
    long_ago = _NOW - timedelta(days=2)
    assert expires_in(long_ago.isoformat(), now=_NOW, ttl=_TTL) == "Expired"


def test_expires_in_naive_timestamp():
    """Naive timestamps (no tzinfo) are treated as UTC."""
    one_hour_ago = _NOW - timedelta(hours=1)
    naive_iso = one_hour_ago.strftime("%Y-%m-%dT%H:%M:%S")
    assert expires_in(naive_iso, now=_NOW, ttl=_TTL) == "23h 0m"
