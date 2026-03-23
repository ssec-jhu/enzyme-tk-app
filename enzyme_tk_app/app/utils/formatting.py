"""Shared formatting helpers for timestamps, durations, and expiry countdowns.

These pure-string utilities are used by several pages (task results, my-tasks
table) to render human-readable dates and times.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from enzyme_tk_app.app.backend.config import JOB_TTL_SECONDS


def format_timestamp(iso_str: str | None) -> str:
    """Format an ISO-8601 timestamp to ``"2026-03-25 14:32"``.

    Args:
        iso_str: ISO-8601 datetime string, or ``None``.

    Returns:
        Formatted string, or ``"—"`` when the input is empty / invalid.
    """
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
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


def expires_in(iso_str: str | None) -> str:
    """Compute how much time remains before a job expires from Redis.

    Args:
        iso_str: The ``submitted_at`` ISO-8601 timestamp.

    Returns:
        Human-readable string like ``"23h 15m"`` or ``"Expired"``.
    """
    if not iso_str:
        return "—"
    try:
        submitted = datetime.fromisoformat(iso_str)
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
        remaining = (submitted + timedelta(seconds=JOB_TTL_SECONDS) - datetime.now(tz=timezone.utc)).total_seconds()
        if remaining <= 0:
            return "Expired"
        return format_duration(int(remaining))
    except (ValueError, TypeError):
        return "—"
