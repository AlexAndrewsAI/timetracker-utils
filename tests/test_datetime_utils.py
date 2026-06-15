"""Tests for the datetime_utils module."""

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from timetracker_utils.datetime_utils import convert_column_tz, resolve_tz


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
