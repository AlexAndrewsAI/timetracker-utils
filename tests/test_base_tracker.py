"""Tests for the BaseTimeTracker module."""

# mypy: ignore-errors

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from timetracker_utils.base_tracker import BaseTimeEntry, BaseTimeTracker

# ── BaseTimeEntry tests ────────────────────────────────────────────────


def test_base_entry_valid() -> None:
    """Test creating a valid BaseTimeEntry."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
    )
    assert entry.activity == "Test"
    assert entry.hours == 2.5


def test_base_entry_parse_datetime_with_tzinfo() -> None:
    """Test parse_datetime with a datetime that already has tzinfo (line 120)."""
    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    entry = BaseTimeEntry(
        activity="Test",
        start_time=dt,
        end_time="2200-01-15T11:30:00.000Z",
    )
    # Should keep it as UTC
    assert entry.start_time == dt
    assert entry.start_time.tzinfo is not None
    assert str(entry.start_time.tzinfo) == "UTC"


def test_base_entry_parse_datetime_non_utc_tz() -> None:
    """Test parse_datetime with a non-UTC timezone datetime."""
    from datetime import timedelta

    tz_est = timezone(timedelta(hours=-5))
    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=tz_est)
    entry = BaseTimeEntry(
        activity="Test",
        start_time=dt,
        end_time="2200-01-15T11:30:00.000Z",
    )
    # Should convert to UTC (9:00 EST = 14:00 UTC)
    assert entry.start_time.hour == 14
    assert str(entry.start_time.tzinfo) == "UTC"


def test_base_entry_parse_list_fields_list_with_empty_parts() -> None:
    """Test parse_list_fields with list containing empty strings (line 144)."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories=["", "valid", ""],
        tags=[""],
    )
    assert entry.categories == ["valid"]
    assert entry.tags == []


def test_base_entry_parse_list_fields_string_fallback() -> None:
    """Test parse_list_fields with non-list, non-string value (line 148)."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories=42,
    )
    assert entry.categories == ["42"]


def test_base_entry_parse_list_fields_non_string_empty() -> None:
    """Test that empty categories/tags defaults to empty list."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
    )
    assert entry.categories == []


def test_base_entry_hours_negative_raises() -> None:
    """Test that negative hours raises validation error (line 157)."""
    with pytest.raises(ValidationError, match="Hours cannot be negative"):
        BaseTimeEntry(
            activity="Test",
            start_time="2200-01-15T09:00:00.000Z",
            end_time="2200-01-15T11:30:00.000Z",
            hours=-1.0,
        )


def test_base_entry_hours_exceeds_24_raises() -> None:
    """Test that hours > 24 raises validation error (line 162)."""
    with pytest.raises(ValidationError, match="Hours exceed 24"):
        BaseTimeEntry(
            activity="Test",
            start_time="2200-01-15T09:00:00.000Z",
            end_time="2200-01-15T11:30:00.000Z",
            hours=25.0,
        )


def test_base_entry_duration_minutes_calculated() -> None:
    """Test duration_minutes_calculated method (lines 170-174)."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
    )
    result = entry.duration_minutes_calculated()
    assert result is not None
    assert abs(result - 150.0) < 0.01


def test_base_entry_duration_minutes_calculated_no_end_time() -> None:
    """Test duration_minutes_calculated returns None when no end_time."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        hours=1.0,
    )
    # After backfill, end_time is set. Force it to None for testing.
    entry.end_time = None
    result = entry.duration_minutes_calculated()
    assert result is None


def test_base_entry_parse_list_fields_none_value() -> None:
    """Test parse_list_fields with None value."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories=None,
    )
    assert entry.categories == []


def test_base_entry_parse_list_fields_empty_string() -> None:
    """Test parse_list_fields with empty string."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories="",
    )
    assert entry.categories == []


def test_base_entry_parse_list_fields_comma_string() -> None:
    """Test parse_list_fields with comma-separated string."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories="cat1, cat2, cat3",
    )
    assert entry.categories == ["cat1", "cat2", "cat3"]


def test_base_entry_parse_list_fields_comma_string_with_blanks() -> None:
    """Test parse_list_fields with comma-separated string containing blanks."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        categories="cat1, , cat3, ",
    )
    assert entry.categories == ["cat1", "cat3"]


def test_base_entry_hours_float_rounding() -> None:
    """Test that hours are properly rounded."""


# ── BaseTimeTracker tests ──────────────────────────────────────────────


def test_base_tracker_total_hours_by_activity_with_data() -> None:
    """Test total_hours_by_activity with non-empty entries (lines 246-251)."""
    import pandas as pd

    tracker = BaseTimeTracker()
    tracker.entries = pd.DataFrame(
        {
            "activity": ["A", "A", "B"],
            "hours": [1.0, 2.0, 3.0],
        }
    )
    tracker.total_hours_by_activity()


def test_base_entry_parse_datetime_naive_datetime_object() -> None:
    """Test parse_datetime with naive datetime object (tzinfo is None, line 120)."""
    from datetime import datetime

    entry = BaseTimeEntry(
        activity="Test",
        start_time=datetime(2200, 1, 15, 9, 0, 0),  # naive datetime
        end_time="2200-01-15T11:30:00.000Z",
    )
    # Naive datetime should be assumed UTC
    assert entry.start_time.tzinfo is not None


def test_base_entry_hours_empty_string_returns_none() -> None:
    """Test hours validator with empty string (line 157)."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        hours="",
    )
    # hours should be computed from end_time - start_time
    assert entry.hours == 2.5


def test_base_tracker_total_hours_by_activity_empty() -> None:
    """Test total_hours_by_activity with empty entries returns {}."""
    tracker = BaseTimeTracker()
    assert tracker.total_hours_by_activity() == {}


def test_base_tracker_entries_by_activity_with_data() -> None:
    """Test entries_by_activity with non-empty entries (lines 254-257)."""
    import pandas as pd

    tracker = BaseTimeTracker()
    tracker.entries = pd.DataFrame(
        {
            "activity": ["A", "A", "B"],
            "hours": [1.0, 2.0, 3.0],
        }
    )
    result = tracker.entries_by_activity("A")
    assert len(result) == 2


def test_base_tracker_entries_by_activity_empty() -> None:
    """Test entries_by_activity with empty entries returns empty DataFrame."""
    tracker = BaseTimeTracker()
    result = tracker.entries_by_activity("Any")
    assert result.empty


def test_base_tracker_total_hours_with_data() -> None:
    """Test total_hours with non-empty entries."""
    import pandas as pd

    tracker = BaseTimeTracker()
    tracker.entries = pd.DataFrame(
        {
            "activity": ["A", "B"],
            "hours": [1.5, 2.5],
        }
    )
    assert tracker.total_hours() == 4.0


def test_base_tracker_total_hours_empty() -> None:
    """Test total_hours with empty entries returns 0.0."""
    tracker = BaseTimeTracker()
    assert tracker.total_hours() == 0.0


def test_base_tracker_entries_by_date_with_data() -> None:
    """Test entries_by_date with non-empty entries."""
    import pandas as pd

    tracker = BaseTimeTracker()
    tracker.entries = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/15/2200", "1/16/2200"],
            "activity": ["A", "B", "C"],
            "hours": [1.0, 2.0, 3.0],
        }
    )
    result = tracker.entries_by_date("1/15/2200")
    assert len(result) == 2


def test_base_tracker_entries_by_date_empty() -> None:
    """Test entries_by_date with empty entries returns empty DataFrame."""
    tracker = BaseTimeTracker()
    result = tracker.entries_by_date("1/1/2000")
    assert result.empty

    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T10:00:00.000Z",
        hours=1.0000000001,
    )
    assert entry.hours == 1.0


def test_base_entry_validate_date_no_start_time() -> None:
    """Test that date is auto-filled from start_time."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
    )
    assert entry.date == "1/15/2200"


def test_base_entry_hours_crosscheck_passes() -> None:
    """Test hours and end_time crosscheck passes when close enough."""
    entry = BaseTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T10:00:00.000Z",
        hours=1.0,
    )
    assert entry.hours == 1.0


def test_base_entry_hours_crosscheck_mismatch_raises() -> None:
    """Test hours and end_time crosscheck raises when mismatch."""
    with pytest.raises(ValidationError, match="does not match duration"):
        BaseTimeEntry(
            activity="Test",
            start_time="2200-01-15T09:00:00.000Z",
            end_time="2200-01-15T10:00:00.000Z",
            hours=2.0,
        )
