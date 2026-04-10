"""Shared formatting and validation helpers.

Contains pure-string utilities used by several pages (task results, my-tasks
table) to render human-readable dates and times, as well as common input
validation helpers shared across tool callbacks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from enzyme_tk_app.app.backend.config import JOB_TTL_SECONDS


def format_timestamp(iso_str: str | None) -> str:
    """Format an ISO-8601 timestamp to ``"2025-10-13 09:20:29"``.

    Args:
        iso_str: ISO-8601 datetime string, or ``None``.

    Returns:
        Formatted string, or ``"—"`` when the input is empty / invalid.
    """
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_str


def compute_duration(started: str | None, completed: str | None) -> str:
    """Compute the wall-clock duration between two ISO timestamps.

    Args:
        started: ISO-8601 start timestamp.
        completed: ISO-8601 end timestamp.

    Returns:
        Human-readable duration like ``"5.3s"`` or ``"2m 15s"``, or ``"—"``.
    """
    if not started or not completed:
        return "—"
    try:
        delta = (datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds()
    except (ValueError, TypeError):
        return "—"
    if delta < 0:
        return "—"
    return format_duration(delta, precise=True)


def format_duration(seconds: float | int, *, precise: bool = False) -> str:
    """Format a duration in seconds to a compact string.

    Args:
        seconds: Duration in seconds.
        precise: If ``True``, keep fractional seconds (``"5.3s"``) and
            show seconds in the minutes range (``"2m 15s"``).  Otherwise
            round to the nearest whole unit (``"5s"``, ``"2m"``).

    Returns:
        E.g. ``"10m"``, ``"1h 0m"``, or ``"5.3s"`` when *precise*.
    """
    if seconds < 60:
        return f"{seconds:.1f}s" if precise else f"{int(seconds)}s"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s" if precise else f"{minutes}m"


def expires_in(
    iso_str: str | None,
    *,
    now: datetime | None = None,
    ttl: int | None = None,
) -> str:
    """Compute how much time remains before a job expires from Redis.

    Args:
        iso_str: The ``submitted_at`` ISO-8601 timestamp.
        now: Optional reference time (defaults to ``datetime.now(UTC)``).
            Useful for deterministic testing.
        ttl: Optional TTL override in seconds (defaults to
            ``JOB_TTL_SECONDS`` from config).

    Returns:
        Human-readable string like ``"23h 15m"`` or ``"Expired"``.
    """
    if not iso_str:
        return "—"
    try:
        submitted = datetime.fromisoformat(iso_str)
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
        effective_ttl = ttl if ttl is not None else JOB_TTL_SECONDS
        effective_now = now if now is not None else datetime.now(tz=timezone.utc)
        remaining = (submitted + timedelta(seconds=effective_ttl) - effective_now).total_seconds()
        if remaining <= 0:
            return "Expired"
        return format_duration(int(remaining))
    except (ValueError, TypeError):
        return "—"


def round_column_values(list_of_columns, df):
    """Round values in specified columns of a DataFrame to 4 decimal places."""
    for col in list_of_columns:
        if col in df.columns:
            df[col] = df[col].round(4)

    return df


# ── Input validation ─────────────────────────────────────────────────────


def validate_top_n(value: object) -> str | None:
    """Validate a Top-N input value.

    Args:
        value: The raw value from the ``dbc.Input`` component (may be
            ``None``, a string, or a number).

    Returns:
        An error message string if validation fails, or ``None`` when the
        value is a valid integer in the range ``[1, 500]``.
    """
    min_n = 1
    max_n = 500

    try:
        n = int(value)
    except (TypeError, ValueError):
        return f"Invalid Top N \u2014 please enter a number between {min_n} and {max_n}."

    if n < min_n or n > max_n:
        return f"Top N must be between {min_n} and {max_n}."

    return None
