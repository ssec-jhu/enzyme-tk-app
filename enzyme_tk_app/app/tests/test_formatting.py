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
    round_column_values,
    truncate_id,
    validate_top_n,
)

# ── format_timestamp ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("iso_str", "expected"),
    [
        ("2026-03-25T14:32:10", "2026-03-25 14:32:10"),
        ("2026-03-25T14:32:10+00:00", "2026-03-25 14:32:10"),
        ("2026-01-01T00:00:00", "2026-01-01 00:00:00"),
        (None, "—"),
        ("", "—"),
        ("not-a-date", "not-a-date"),
    ],
)
def test_format_timestamp_valid(iso_str, expected):
    """Well-formed ISO strings are formatted as 'YYYY-MM-DD HH:MM:SS'."""
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


@pytest.mark.parametrize(
    ("iso_str", "expected"),
    [
        (_NOW.isoformat(), "24h 0m"),
        (_NOW - timedelta(days=2), "Expired"),
        (_NOW - timedelta(hours=1), "23h 0m"),
    ],
    ids=["recently-submitted", "expired", "naive-timestamp"],
)
def test_expires_in_valid(iso_str, expected):
    """Valid timestamps produce the expected remaining-time string."""
    # Accept both datetime and str; normalise to a naive ISO string
    # so the "naive-timestamp" case drops tzinfo like the original test.
    if isinstance(iso_str, datetime):
        iso_str = iso_str.strftime("%Y-%m-%dT%H:%M:%S")
    assert expires_in(iso_str, now=_NOW, ttl=_TTL) == expected


# ── validate_top_n ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "is_valid"),
    [
        (10, True),
        (1, True),
        (500, True),
        ("50", True),
        (10.0, True),
        (0, False),
        (501, False),
        (-1, False),
        (3.5, False),
        ("3.5", False),
        (None, False),
        ("abc", False),
        ("", False),
    ],
    ids=[
        "mid-range",
        "min-boundary",
        "max-boundary",
        "string-int",
        "whole-float",
        "below-min",
        "above-max",
        "negative",
        "fractional-float",
        "fractional-string",
        "none",
        "non-numeric",
        "empty-string",
    ],
)
def test_validate_top_n(value, is_valid):
    """Returns None for valid inputs and an error string for invalid ones."""
    result = validate_top_n(value)
    if is_valid:
        assert result is None, f"Expected None for valid input {value!r}, got {result!r}"
    else:
        assert isinstance(result, str) and len(result) > 0, f"Expected error message for {value!r}, got {result!r}"


# ── round_column_values ──────────────────────────────────────────────────


def test_round_column_values_rounds_specified_columns():
    """Values in listed columns are rounded to 4 decimal places."""
    import pandas as pd

    df = pd.DataFrame({"score": [1.123456789], "name": ["enzyme"]})
    result = round_column_values(["score"], df)
    assert result["score"].iloc[0] == pytest.approx(1.1235)
    # Non-listed column stays untouched
    assert result["name"].iloc[0] == "enzyme"


def test_round_column_values_ignores_missing_columns():
    """Columns not present in the DataFrame are silently skipped."""
    import pandas as pd

    df = pd.DataFrame({"a": [3.14159]})
    result = round_column_values(["a", "nonexistent"], df)
    assert result["a"].iloc[0] == pytest.approx(3.1416)
    assert list(result.columns) == ["a"]


# ── truncate_id ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("abcdef123456", "...123456"),
        ("abc", "abc"),
    ],
    ids=["long-id", "short-id"],
)
def test_truncate_id(value, expected):
    """truncate_id keeps the last 6 chars with ellipsis or passes through short values."""
    assert truncate_id(value) == expected
