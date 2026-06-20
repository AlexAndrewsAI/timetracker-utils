"""Tests for the SimpleTimeTracker module."""

# ruff: noqa: E501 - CSV data lines exceed line length limit
# mypy: ignore-errors

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from timetracker_utils.simple_time_tracker import SimpleTimeEntry, SimpleTimeTracker

SAMPLE_CSV = """\
"activity name","time started","time ended","comment","categories","record tags","duration","duration minutes"
"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","nebula mapping","nebula mapping","","2:30:00","150"
"StellarCartography","2200-01-15T21:00:00.000Z","2200-01-15T22:30:00.000Z","","","","1:30:00","90"
"CrewFitness","2200-01-16T06:00:00.000Z","2200-01-16T07:00:00.000Z","strength training","fitness","","1:00:00","60"
"""


# ── SimpleTimeEntry tests ──────────────────────────────────────────────


def test_simple_time_entry_valid() -> None:
    """Test creating a valid SimpleTimeEntry."""
    entry = SimpleTimeEntry(
        activity="StellarCartography",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes="150",
    )
    assert entry.activity == "StellarCartography"
    assert entry.hours == 2.5
    assert entry.duration_str == "2:30:00"
    assert entry.duration_minutes == 150


def test_simple_time_entry_alias_mapping() -> None:
    """Test field aliases for CSV column names."""
    entry = SimpleTimeEntry(
        **{
            "activity name": "StellarCartography",
            "time started": "2200-01-15T09:00:00.000Z",
            "time ended": "2200-01-15T11:30:00.000Z",
            "duration": "2:30:00",
            "duration minutes": "150",
        }
    )
    assert entry.activity == "StellarCartography"


def test_coerce_duration_minutes_none() -> None:
    """Test coerce_duration_minutes with None."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes=None,
    )
    assert entry.duration_minutes is None


def test_coerce_duration_minutes_empty_string() -> None:
    """Test coerce_duration_minutes with empty string."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes="",
    )
    assert entry.duration_minutes is None


def test_coerce_duration_minutes_whitespace_string() -> None:
    """Test coerce_duration_minutes with whitespace-only string."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes="  ",
    )
    assert entry.duration_minutes is None


def test_coerce_duration_minutes_float_string() -> None:
    """Test coerce_duration_minutes with float string."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes="150.0",
    )
    assert entry.duration_minutes == 150


def test_coerce_duration_minutes_int_value() -> None:
    """Test coerce_duration_minutes with int value."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes=150,
    )
    assert entry.duration_minutes == 150


def test_parse_duration_hms_none() -> None:
    """Test parse_duration_hms with None."""
    result = SimpleTimeEntry.parse_duration_hms(None)
    assert result == ""


def test_parse_duration_hms_na() -> None:
    """Test parse_duration_hms with N/A."""
    result = SimpleTimeEntry.parse_duration_hms("N/A")
    assert result == ""


def test_parse_duration_hms_case_insensitive_na() -> None:
    """Test parse_duration_hms with 'n/a' (lowercase)."""
    result = SimpleTimeEntry.parse_duration_hms("n/a")
    assert result == ""


def test_parse_datetime_none() -> None:
    """Test parse_datetime with None returns None."""
    result = SimpleTimeEntry.parse_datetime(None)
    assert result is None


def test_parse_datetime_empty_string() -> None:
    """Test parse_datetime with empty string returns None."""
    result = SimpleTimeEntry.parse_datetime("")
    assert result is None


def test_parse_datetime_datetime_object() -> None:
    """Test parse_datetime with a datetime object."""
    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    entry = SimpleTimeEntry(
        activity="Test",
        start_time=dt,
        end_time=datetime(2200, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        duration="1:00:00",
        duration_minutes="60",
    )
    assert entry.start_time == dt


def test_parse_datetime_naive_no_tz() -> None:
    """Test parse_datetime with naive datetime (no explicit timezone in string)."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00",
        end_time="2200-01-15T10:00:00",
        duration="1:00:00",
        duration_minutes="60",
    )
    # Naive timestamps should be converted to UTC using the default timezone (UTC)
    assert entry.start_time.tzinfo is not None
    assert entry.start_time.tzinfo == timezone.utc


def test_parse_datetime_naive_zone_none() -> None:
    """Test parse_datetime with naive datetime when resolve_tz returns None (line 99, 110)."""
    from datetime import datetime
    from unittest.mock import patch

    # Test with naive datetime string (line 99)
    with patch("timetracker_utils.datetime_utils.resolve_tz", return_value=None):
        entry = SimpleTimeEntry.model_validate(
            {
                "activity": "Test",
                "start_time": "2200-01-15T09:00:00",
                "end_time": "2200-01-15T10:00:00",
                "duration": "1:00:00",
                "duration_minutes": "60",
            },
            context={"default_timezone": "ET"},
        )
    # Should still work, falling back to UTC
    assert entry.start_time.tzinfo is not None
    assert entry.start_time.tzinfo == timezone.utc

    # Test with naive datetime object (line 110)
    with patch("timetracker_utils.datetime_utils.resolve_tz", return_value=None):
        entry2 = SimpleTimeEntry.model_validate(
            {
                "activity": "Test",
                "start_time": datetime(2200, 1, 15, 9, 0, 0),
                "end_time": "2200-01-15T10:00:00.000Z",
                "duration": "1:00:00",
                "duration_minutes": "60",
            },
            context={"default_timezone": "ET"},
        )
    assert entry2.start_time.tzinfo is not None


def test_parse_datetime_naive_zone_not_none() -> None:
    """Test parse_datetime with naive datetime when resolve_tz returns zone (lines 94-99)."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    test_zone = timezone(timedelta(hours=-5))
    with patch("timetracker_utils.datetime_utils.resolve_tz", return_value=test_zone):
        entry = SimpleTimeEntry.model_validate(
            {
                "activity": "Test",
                "start_time": datetime(2200, 1, 15, 9, 0, 0),  # naive datetime object
                "end_time": "2200-01-15T10:00:00.000Z",
                "duration": "1:00:00",
                "duration_minutes": "60",
            },
            context={"default_timezone": "ET"},
        )
    # Should convert to UTC
    assert entry.start_time.tzinfo is not None


def test_parse_datetime_explicit_timezone() -> None:
    """Test parse_datetime with explicit timezone in string (e.g. +05:00)."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00+05:00",
        end_time="2200-01-15T10:00:00+05:00",
        duration="1:00:00",
        duration_minutes="60",
    )
    assert entry.start_time is not None


def test_parse_datetime_invalid_raises() -> None:
    """Test parse_datetime with invalid string raises ValueError (line 113)."""
    with pytest.raises(ValidationError, match="Invalid datetime"):
        SimpleTimeEntry(
            activity="Test",
            start_time="not-a-datetime",
            duration="1:00:00",
            duration_minutes="60",
        )


def test_validate_duration_crosscheck_mismatch_raises() -> None:
    """Test crosscheck raises when duration and minutes don't match."""
    with pytest.raises(ValidationError, match="does not match"):
        SimpleTimeEntry(
            activity="Test",
            start_time="2200-01-15T09:00:00.000Z",
            end_time="2200-01-15T10:00:00.000Z",
            duration="2:00:00",
            duration_minutes="150",
        )


def test_parse_hms_to_minutes_3_parts() -> None:
    """Test _parse_hms_to_minutes with H:M:S format."""
    result = SimpleTimeEntry._parse_hms_to_minutes("2:30:00")
    assert result == 150.0


def test_parse_hms_to_minutes_2_parts() -> None:
    """Test _parse_hms_to_minutes with M:S format."""
    result = SimpleTimeEntry._parse_hms_to_minutes("30:00")
    assert result == 30.0


def test_coerce_duration_minutes_unexpected_type() -> None:
    """Test coerce_duration_minutes with unexpected type returns None (line 63)."""
    result = SimpleTimeEntry.coerce_duration_minutes([1, 2, 3])
    assert result is None


def test_parse_hms_to_minutes_empty_string() -> None:
    """Test _parse_hms_to_minutes with empty string returns None."""
    result = SimpleTimeEntry._parse_hms_to_minutes("")
    assert result is None


def test_parse_hms_to_minutes_1_part() -> None:
    """Test _parse_hms_to_minutes with seconds-only format."""
    result = SimpleTimeEntry._parse_hms_to_minutes("3600")
    assert result == 60.0


# ── SimpleTimeTracker tests ────────────────────────────────────────────


def test_read_csv_string() -> None:
    """Test reading CSV string into SimpleTimeTracker."""
    tracker = SimpleTimeTracker()
    entries = tracker.read_csv_string(SAMPLE_CSV)
    assert len(entries) == 3
    assert isinstance(entries, pd.DataFrame)
    assert "activity" in entries.columns
    assert "categories" in entries.columns


def test_read_csv_string_empty_csv() -> None:
    """Test reading header-only CSV returns empty DataFrame."""
    tracker = SimpleTimeTracker()
    header_only = (
        "activity name,time started,time ended,comment,categories,"
        "record tags,duration,duration minutes\n"
    )
    entries = tracker.read_csv_string(header_only)
    assert entries.empty


def test_read_csv_string_missing_required_column() -> None:
    """Test reading CSV missing a required column raises ValueError."""
    tracker = SimpleTimeTracker()
    bad_csv = (
        "activity name,time started,comment\n"
        '"Test","2200-01-15T09:00:00.000Z","notes"\n'
    )
    with pytest.raises(ValueError, match="Missing required STT columns"):
        tracker.read_csv_string(bad_csv)


def test_read_csv_string_with_bom() -> None:
    """Test reading CSV with BOM strips it."""
    tracker = SimpleTimeTracker()
    bom_csv = "\ufeff" + SAMPLE_CSV
    entries = tracker.read_csv_string(bom_csv)
    assert len(entries) == 3


def test_read_csv_file(tmp_path: Path) -> None:
    """Test reading CSV from a file path."""
    csv_path = tmp_path / "stt_entries.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    tracker = SimpleTimeTracker()
    entries = tracker.read_csv(str(csv_path))
    assert len(entries) == 3


def test_read_csv_file_not_found() -> None:
    """Test reading from non-existent file raises FileNotFoundError."""
    tracker = SimpleTimeTracker()
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        tracker.read_csv("/nonexistent/path.csv")


def test_total_hours() -> None:
    """Test total hours calculation."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    total = tracker.total_hours()
    assert abs(total - 5.0) < 0.001  # 2.5 + 1.5 + 1.0


def test_total_hours_when_empty() -> None:
    """Test total_hours returns 0.0 when no entries loaded."""
    tracker = SimpleTimeTracker()
    assert tracker.total_hours() == 0.0


def test_total_hours_by_activity() -> None:
    """Test total hours grouped by activity."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    by_activity = tracker.total_hours_by_activity()
    assert "StellarCartography" in by_activity
    assert "CrewFitness" in by_activity
    assert abs(by_activity["StellarCartography"] - 4.0) < 0.001  # 2.5 + 1.5


def test_total_hours_by_activity_when_empty() -> None:
    """Test total_hours_by_activity returns empty dict when no entries."""
    tracker = SimpleTimeTracker()
    assert tracker.total_hours_by_activity() == {}


def test_entries_by_activity() -> None:
    """Test filtering entries by activity name."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    cartography_entries = tracker.entries_by_activity("StellarCartography")
    assert len(cartography_entries) == 2
    assert all(cartography_entries["activity"] == "StellarCartography")


def test_entries_by_activity_nonexistent() -> None:
    """Test filtering by an activity that doesn't exist."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    entries = tracker.entries_by_activity("Nonexistent")
    assert entries.empty


def test_entries_by_activity_when_empty() -> None:
    """Test entries_by_activity returns empty DataFrame when no entries loaded."""
    tracker = SimpleTimeTracker()
    entries = tracker.entries_by_activity("Any")
    assert entries.empty


def test_entries_by_date() -> None:
    """Test filtering entries by date."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    entries = tracker.entries_by_date("1/15/2200")
    assert len(entries) == 2


def test_entries_by_date_when_empty() -> None:
    """Test entries_by_date returns empty DataFrame when no entries."""
    tracker = SimpleTimeTracker()
    entries = tracker.entries_by_date("1/1/2000")
    assert entries.empty


def test_extra_columns_logged_as_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Test that extra columns in CSV are logged as a warning."""
    caplog.set_level(logging.WARNING)
    tracker = SimpleTimeTracker()
    csv_with_extra = (
        "activity name,time started,time ended,comment,categories,"
        "record tags,duration,duration minutes,Location\n"
        '"Test","2200-01-15T09:00:00.000Z","2200-01-15T10:00:00.000Z",'
        '"work","","","1:00:00","60","Office"\n'
    )
    entries = tracker.read_csv_string(csv_with_extra)
    assert len(entries) == 1
    assert any("Extra columns" in record.message for record in caplog.records)


def test_post_process_drops_validation_cols() -> None:
    """Test that validation-only columns are dropped after processing."""
    tracker = SimpleTimeTracker()
    tracker.read_csv_string(SAMPLE_CSV)
    assert "duration_str" not in tracker.entries.columns
    assert "duration_minutes" not in tracker.entries.columns


def test_validate_duration_crosscheck_empty_duration_none_minutes() -> None:
    """Test crosscheck with empty duration_str and None duration_minutes (line 122)."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T10:00:00.000Z",
        duration="",
        duration_minutes=None,
    )
    # Should return self without error
    assert entry.duration_str == ""
    assert entry.duration_minutes is None


def test_parse_hms_to_minutes_invalid() -> None:
    """Test _parse_hms_to_minutes with invalid format raises."""
    with pytest.raises(ValueError, match="Invalid H:M:S duration"):
        SimpleTimeEntry._parse_hms_to_minutes("abc")


def test_parse_hms_to_minutes_too_many_parts() -> None:
    """Test _parse_hms_to_minutes with >3 parts returns None."""
    result = SimpleTimeEntry._parse_hms_to_minutes("1:2:3:4")
    assert result is None


def test_coerce_duration_minutes_float_value() -> None:
    """Test coerce_duration_minutes with float value."""
    entry = SimpleTimeEntry(
        activity="Test",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        duration="2:30:00",
        duration_minutes=150.7,
    )
    assert entry.duration_minutes == 150


def test_coerce_duration_minutes_invalid_string() -> None:
    """Test coerce_duration_minutes with invalid string raises ValueError."""
    with pytest.raises(ValidationError, match="Invalid duration minutes"):
        SimpleTimeEntry(
            activity="Test",
            start_time="2200-01-15T09:00:00.000Z",
            end_time="2200-01-15T11:30:00.000Z",
            duration="2:30:00",
            duration_minutes="not-a-number",
        )


def test_coerce_duration_minutes_bool() -> None:
    """Test coerce_duration_minutes with bool (isinstance of int)."""
    result = SimpleTimeEntry.coerce_duration_minutes(False)
    assert result == 0  # bool is subclass of int, so False -> 0
