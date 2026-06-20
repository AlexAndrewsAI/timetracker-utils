"""Tests for the datetime_utils module."""

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from timetracker_utils.datetime_utils import (
    aggregate_by_date,
    convert_column_tz,
    resolve_tz,
)


def test_resolve_tz_abbreviation_et() -> None:
    """Test that ET resolves to America/New_York."""
    zone = resolve_tz("ET")
    assert zone == ZoneInfo("America/New_York")


def test_resolve_tz_abbreviation_pt() -> None:
    """Test that PT resolves to America/Los_Angeles."""
    zone = resolve_tz("PT")
    assert zone == ZoneInfo("America/Los_Angeles")


def test_resolve_tz_abbreviation_utc() -> None:
    """Test that UTC resolves to UTC."""
    zone = resolve_tz("UTC")
    assert zone == ZoneInfo("UTC")


def test_resolve_tz_abbreviation_case_insensitive() -> None:
    """Test that abbreviation resolution is case-insensitive."""
    zone = resolve_tz("et")
    assert zone == ZoneInfo("America/New_York")


def test_resolve_tz_iana_name() -> None:
    """Test that a full IANA name resolves correctly."""
    zone = resolve_tz("Europe/London")
    assert zone == ZoneInfo("Europe/London")


def test_resolve_tz_unsupported() -> None:
    """Test that an unsupported timezone abbreviation returns None."""
    zone = resolve_tz("XZ")
    assert zone is None


def test_resolve_tz_iana_case_insensitive() -> None:
    """Test that IANA names are matched case-insensitively."""
    zone = resolve_tz("america/new_york")
    assert zone == ZoneInfo("America/New_York")


def test_convert_column_tz_et() -> None:
    """Test converting UTC timestamps to Eastern Time via abbreviation."""
    series = pd.Series(
        pd.to_datetime(
            ["2026-04-13T15:00:00Z", "2026-04-13T16:00:00Z"],
            utc=True,
        )
    )
    result = convert_column_tz(series, "ET")
    assert result.dt.tz == ZoneInfo("America/New_York")
    # ET is UTC-4 in April
    assert result.iloc[0].hour == 11
    assert result.iloc[1].hour == 12


def test_convert_column_tz_iana() -> None:
    """Test converting UTC timestamps to a full IANA timezone."""
    series = pd.Series(
        pd.to_datetime(
            ["2026-04-13T15:00:00Z"],
            utc=True,
        )
    )
    result = convert_column_tz(series, "America/Los_Angeles")
    assert result.dt.tz == ZoneInfo("America/Los_Angeles")
    # PT is UTC-7 in April
    assert result.iloc[0].hour == 8


def test_convert_column_tz_naive_treated_as_utc() -> None:
    """Test that timezone-naive values are assumed to be UTC."""
    series = pd.Series(pd.to_datetime(["2026-04-13T15:00:00", "2026-04-13T16:00:00"]))
    result = convert_column_tz(series, "ET")
    assert result.dt.tz == ZoneInfo("America/New_York")
    assert result.iloc[0].hour == 11


def test_convert_column_tz_does_not_mutate() -> None:
    """Test that the original series is not mutated."""
    series = pd.Series(pd.to_datetime(["2026-04-13T15:00:00Z"], utc=True))
    original = series.copy()
    _ = convert_column_tz(series, "ET")
    assert series.iloc[0] == original.iloc[0]


def test_convert_column_tz_unsupported_raises() -> None:
    """Test that an unsupported timezone raises ValueError."""
    series = pd.Series(pd.to_datetime(["2026-04-13T15:00:00Z"], utc=True))
    with pytest.raises(ValueError, match="Cannot resolve timezone"):
        convert_column_tz(series, "XZ")


def test_convert_column_tz_utc_to_utc() -> None:
    """Test converting to UTC (identity)."""
    series = pd.Series(pd.to_datetime(["2026-04-13T15:00:00Z"], utc=True))
    result = convert_column_tz(series, "UTC")
    assert result.iloc[0].hour == 15


def _make_entry(
    start_str: str,
    end_str: str,
    activity: str = "Coding",
    tags: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict:
    """Create a dict simulating a database entry row."""
    return {
        "activity": activity,
        "start_time": start_str,
        "end_time": end_str,
        "tags": tags or [],
        "categories": categories or [],
    }


def test_aggregate_by_date_empty_df() -> None:
    """Empty DataFrame returns is_empty=True."""
    result = aggregate_by_date(pd.DataFrame(), date(2200, 1, 15), "ET")
    assert result["is_empty"] is True
    assert result["total_seconds"] == 0.0
    assert result["activity_breakdown"] == {}
    assert result["tag_breakdown"] == {}
    assert result["category_breakdown"] == {}


def test_aggregate_by_date_no_matching_entries() -> None:
    """Entries exist but not for the target date."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:00:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    # Query for a different date
    result = aggregate_by_date(entries, date(2200, 1, 16), "ET")
    assert result["is_empty"] is True
    assert result["total_seconds"] == 0.0


def test_aggregate_by_date_single_entry() -> None:
    """A single entry fully within the day."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:30:00+00:00",
                "tags": ["work"],
                "categories": ["development"],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["is_empty"] is False
    # 2.5 hours = 9000 seconds
    assert result["total_seconds"] == 9000.0
    assert result["activity_breakdown"] == {"Coding": 9000.0}
    assert result["tag_breakdown"] == {"work": 9000.0}
    assert result["category_breakdown"] == {"development": 9000.0}


def test_aggregate_by_date_multiple_entries() -> None:
    """Multiple entries on the same day."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:00:00+00:00",
                "tags": [],
                "categories": [],
            },
            {
                "activity": "Review",
                "start_time": "2200-01-15T14:00:00+00:00",
                "end_time": "2200-01-15T15:30:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["is_empty"] is False
    # 2h + 1.5h = 3.5h = 12600 seconds
    assert result["total_seconds"] == 12600.0
    assert result["activity_breakdown"] == {"Coding": 7200.0, "Review": 5400.0}


def test_aggregate_by_date_entry_spans_midnight() -> None:
    """Entry spanning midnight in ET is split correctly.

    Entry: start=2200-01-15T22:00:00+00:00 (5pm ET),
    end=2200-01-16T05:00:00+00:00 (midnight ET)
    In ET: 17:00 to 00:00 on Jan 15 = 7 hours on Jan 15.
    """
    entries = pd.DataFrame(
        [
            {
                "activity": "LateWork",
                "start_time": "2200-01-15T22:00:00+00:00",
                "end_time": "2200-01-16T05:00:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    # Query Jan 15 in ET
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["is_empty"] is False
    # 7 hours = 25200 seconds
    assert result["total_seconds"] == 25200.0
    assert result["activity_breakdown"] == {"LateWork": 25200.0}

    # Query Jan 16 in ET - no overlap with this entry
    result = aggregate_by_date(entries, date(2200, 1, 16), "ET")
    assert result["is_empty"] is True


def test_aggregate_by_date_entry_starts_before_ends_after_midnight() -> None:
    """Entry fully within next day (starts after midnight in ET)."""
    # Start: 2200-01-16T02:00:00+00:00 = 2200-01-15 21:00 ET (9pm Jan 15)
    # End: 2200-01-16T05:00:00+00:00 = 2200-01-16 00:00 ET (midnight Jan 16)
    entries = pd.DataFrame(
        [
            {
                "activity": "NightShift",
                "start_time": "2200-01-16T02:00:00+00:00",
                "end_time": "2200-01-16T05:00:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    # 2026-01-16T02:00:00+00:00 UTC = 2026-01-15 21:00:00 ET (9pm ET on Jan 15!)
    # 2026-01-16T05:00:00+00:00 UTC = 2026-01-16 00:00:00 ET (midnight Jan 16)
    # This entry is entirely within Jan 15 in ET!
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["is_empty"] is False
    # 3 hours = 10800 seconds
    assert result["total_seconds"] == 10800.0


def test_aggregate_by_date_with_multiple_tags() -> None:
    """Multiple tags are split evenly across the duration."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:00:00+00:00",
                "tags": ["work", "urgent"],
                "categories": [],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    # 2 hours = 7200 seconds, each tag gets 3600
    assert result["tag_breakdown"] == {"work": 3600.0, "urgent": 3600.0}


def test_aggregate_by_date_with_multiple_categories() -> None:
    """Multiple categories are split evenly."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T10:00:00+00:00",
                "tags": [],
                "categories": ["dev", "review"],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    # 1 hour = 3600 seconds, each category gets 1800
    assert result["category_breakdown"] == {"dev": 1800.0, "review": 1800.0}


def test_aggregate_by_date_utc_timezone() -> None:
    """With UTC timezone, filtering is direct UTC comparison."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:00:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "UTC")
    assert result["is_empty"] is False
    assert result["total_seconds"] == 7200.0


def test_aggregate_by_date_invalid_timezone() -> None:
    """Invalid timezone raises ValueError."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T11:00:00+00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    with pytest.raises(ValueError, match="Cannot resolve timezone"):
        aggregate_by_date(entries, date(2200, 1, 15), "XZ")


def test_aggregate_by_date_tags_as_json_strings() -> None:
    """Tags stored as JSON strings are parsed correctly."""
    import json

    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T10:00:00+00:00",
                "tags": json.dumps(["work", "urgent"]),
                "categories": json.dumps(["dev"]),
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["tag_breakdown"] == {"work": 1800.0, "urgent": 1800.0}
    assert result["category_breakdown"] == {"dev": 3600.0}


def test_aggregate_by_date_tags_as_single_string() -> None:
    """Tags stored as a single string (not JSON) are treated as one tag."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00+00:00",
                "end_time": "2200-01-15T10:00:00+00:00",
                "tags": "single_tag",
                "categories": "single_category",
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    # Single tag gets full duration
    assert result["tag_breakdown"] == {"single_tag": 3600.0}
    assert result["category_breakdown"] == {"single_category": 3600.0}


def test_aggregate_by_date_naive_timestamps() -> None:
    """Timezone-naive timestamp strings are treated as UTC (lines 213, 215)."""
    entries = pd.DataFrame(
        [
            {
                "activity": "Coding",
                "start_time": "2200-01-15T09:00:00",
                "end_time": "2200-01-15T11:00:00",
                "tags": [],
                "categories": [],
            },
        ]
    )
    result = aggregate_by_date(entries, date(2200, 1, 15), "ET")
    assert result["is_empty"] is False
    # 2 hours = 7200 seconds
    assert result["total_seconds"] == 7200.0


def test_parse_list_field_non_list_non_string() -> None:
    """_parse_list_field with a non-list, non-string value returns [] (line 140)."""
    from timetracker_utils.datetime_utils import _parse_list_field

    assert _parse_list_field(42) == []
    assert _parse_list_field(3.14) == []
    assert _parse_list_field(None) == []
