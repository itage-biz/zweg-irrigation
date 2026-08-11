"""Tests for calendar scheduling edge cases."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from custom_components.zweg_irrigation.schedule import first_anchor_after, next_occurrence

KYIV = ZoneInfo("Europe/Kyiv")


def test_spring_dst_gap_uses_first_valid_instant() -> None:
    """A nonexistent local time advances to the first instant after the gap."""
    now = datetime(2026, 3, 28, 12, tzinfo=KYIV)

    anchor = first_anchor_after(now, time(3, 30))

    assert anchor == datetime(2026, 3, 29, 4, 0, tzinfo=KYIV)


def test_fall_dst_repeat_uses_first_occurrence_once() -> None:
    """An ambiguous local time uses fold zero and intervals remain calendar-based."""
    now = datetime(2026, 10, 24, 12, tzinfo=KYIV)

    anchor = first_anchor_after(now, time(3, 30))
    following = next_occurrence(anchor, 1, datetime(2026, 10, 25, 4, tzinfo=KYIV))

    assert anchor.fold == 0
    assert anchor == datetime(2026, 10, 25, 3, 30, tzinfo=KYIV, fold=0)
    assert following == datetime(2026, 10, 26, 3, 30, tzinfo=KYIV)


def test_interval_uses_local_calendar_days() -> None:
    """A two-day interval preserves its local start time across DST."""
    anchor = datetime(2026, 3, 28, 6, 15, tzinfo=KYIV)

    following = next_occurrence(anchor, 2, anchor)

    assert following == datetime(2026, 3, 30, 6, 15, tzinfo=KYIV)
