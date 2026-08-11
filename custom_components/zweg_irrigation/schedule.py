"""Calendar-based scheduling helpers."""

from __future__ import annotations

from datetime import datetime, time, timedelta, tzinfo


def resolve_local_time(local_time: datetime, timezone: tzinfo) -> datetime:
    """Resolve a local wall time, choosing the first valid instant.

    Ambiguous autumn times use ``fold=0``. Imaginary spring-forward times are
    advanced to the first valid local minute after the gap.
    """
    candidate = local_time.replace(tzinfo=timezone, fold=0)
    while True:
        round_trip = datetime.fromtimestamp(candidate.timestamp(), tz=timezone)
        if round_trip.replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return candidate
        candidate = (candidate.replace(tzinfo=None) + timedelta(minutes=1)).replace(
            tzinfo=timezone,
            fold=0,
        )


def first_anchor_after(now: datetime, start_time: time) -> datetime:
    """Return the first scheduled local occurrence strictly after ``now``."""
    local_now = now.astimezone(now.tzinfo)
    if local_now.tzinfo is None:
        raise ValueError("A timezone-aware time is required")
    candidate = resolve_local_time(datetime.combine(local_now.date(), start_time), local_now.tzinfo)
    if candidate <= now:
        candidate = resolve_local_time(
            datetime.combine(local_now.date() + timedelta(days=1), start_time),
            local_now.tzinfo,
        )
    return candidate


def next_occurrence(anchor: datetime, interval_days: int, now: datetime) -> datetime:
    """Return the first calendar interval occurrence strictly after ``now``."""
    occurrence = anchor
    if anchor.tzinfo is None:
        raise ValueError("A timezone-aware anchor is required")
    while occurrence <= now:
        local = occurrence.astimezone(anchor.tzinfo)
        occurrence = resolve_local_time(
            datetime.combine(
                local.date() + timedelta(days=interval_days), local.timetz().replace(tzinfo=None)
            ),
            anchor.tzinfo,
        )
    return occurrence
