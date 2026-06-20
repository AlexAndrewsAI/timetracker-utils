"""Datetime utilities module.

Provides functions for converting pandas timestamp columns
between timezones using familiar abbreviations.
"""

import logging
from datetime import date as date_type
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import pandas as pd

logger = logging.getLogger(__name__)

# Mapping from common timezone abbreviations to IANA timezone names.
# Uses zoneinfo from the standard library for reliable tz resolution.
_TZ_ABBREV: dict[str, str] = {
    "ET": "America/New_York",
    "CT": "America/Chicago",
    "MT": "America/Denver",
    "PT": "America/Los_Angeles",
    "AT": "America/Anchorage",
    "HT": "Pacific/Honolulu",
    "UTC": "UTC",
    "GMT": "Europe/London",
    "CET": "Europe/Berlin",
    "IST": "Asia/Kolkata",
    "JST": "Asia/Tokyo",
    "AEST": "Australia/Sydney",
    "NZST": "Pacific/Auckland",
}


def resolve_tz(tz: str) -> ZoneInfo | None:
    """Resolve a timezone abbreviation or IANA name to a ZoneInfo object.

    Checks the built-in abbreviation map first, then tries to find an
    exact match among known IANA timezone names, and finally attempts
    a case-insensitive match.

    Args:
        tz: A timezone abbreviation (e.g. "ET") or IANA name
            (e.g. "America/New_York").

    Returns:
        A ZoneInfo object for the resolved timezone, or None if the
        timezone cannot be resolved.

    """
    # Check built-in abbreviation map first
    if tz.upper() in _TZ_ABBREV:
        iana = _TZ_ABBREV[tz.upper()]
        logger.debug("Resolved abbreviation %r to IANA %r", tz, iana)
        return ZoneInfo(iana)

    # Direct IANA name match
    if tz in available_timezones():
        logger.debug("Resolved IANA timezone %r", tz)
        return ZoneInfo(tz)

    # Case-insensitive IANA match
    tz_lower = tz.lower()
    for tz_name in available_timezones():
        if tz_name.lower() == tz_lower:
            logger.debug("Resolved %r to IANA %r (case-insensitive)", tz, tz_name)
            return ZoneInfo(tz_name)

    logger.warning("Could not resolve timezone: %r", tz)
    return None


def convert_column_tz(
    column: "pd.Series",
    target_tz: str,
) -> "pd.Series":
    """Convert a pandas Series of timestamps to a target timezone.

    The series should contain timezone-aware datetime values (e.g. UTC
    timestamps). The function converts them to the timezone identified
    by ``target_tz``.

    Args:
        column: A pandas Series containing timezone-aware datetime values.
            Timezone-naive values are assumed to be UTC.
        target_tz: The target timezone as an abbreviation (e.g. "ET",
            "PT") or a full IANA timezone name (e.g. "America/New_York").

    Returns:
        A new pandas Series with timestamps converted to the target
        timezone.

    Raises:
        ValueError: If the target timezone cannot be resolved.

    """
    zone = resolve_tz(target_tz)
    if zone is None:
        msg = f"Cannot resolve timezone: {target_tz!r}"
        raise ValueError(msg)

    # Work on a copy so we don't mutate the original
    series = column.copy()

    # If series is timezone-naive, assume UTC
    if series.dt.tz is None:
        series = series.dt.tz_localize("UTC")

    result: pd.Series = series.dt.tz_convert(zone)
    logger.info(
        "Converted %d timestamps from %s to %s",
        len(result),
        series.dt.tz,
        target_tz,
    )
    return result


def _parse_list_field(value: Any) -> list[str]:
    """Parse a list/tags/categories field from the database.

    Handles both Python lists and JSON-serialized strings.

    Returns:
        A list of non-empty string tags/categories.

    """
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return [value.strip()] if value.strip() else []
    return []


def aggregate_by_date(
    entries: pd.DataFrame,
    report_date: date_type,
    timezone: str,
) -> dict[str, Any]:
    """Aggregate time entries for a specific date in the given timezone.

    Entries are filtered to those that overlap with the date in the
    specified timezone. Entries spanning midnight (crossing date
    boundaries in the given timezone) are split and counted toward
    each respective date.

    Args:
        entries: DataFrame with at least ``start_time``, ``end_time``,
            ``activity``, ``tags``, and ``categories`` columns.
            ``start_time`` and ``end_time`` should be timezone-aware
            pandas datetime columns (UTC preferred).
        report_date: The calendar date to report on.
        timezone: The timezone to use for date-boundary determination
            (e.g. ``"ET"``, ``"PT"``, ``"America/New_York"``).

    Returns:
        A dictionary with keys:
        - ``total_seconds``: total time on the date (float, may span
          midnight so could exceed 24h if entries cross date boundary)
        - ``activity_breakdown``: dict mapping activity name to its
          total seconds on that date
        - ``tag_breakdown``: dict mapping tag to its prorated seconds
          (distributed evenly across tags of each entry)
        - ``category_breakdown``: dict mapping category to its prorated
          seconds (distributed evenly across categories)
        - ``is_empty``: True if no entries overlapped with the date

    """
    if entries.empty:
        return {
            "total_seconds": 0.0,
            "activity_breakdown": {},
            "tag_breakdown": {},
            "category_breakdown": {},
            "is_empty": True,
        }

    zone = resolve_tz(timezone)
    if zone is None:
        msg = f"Cannot resolve timezone: {timezone!r}"
        raise ValueError(msg)

    # Build UTC range for the target date in the given timezone
    tz = ZoneInfo(zone.key)
    year, month, day = report_date.year, report_date.month, report_date.day

    # Start of day in the target timezone
    from datetime import datetime

    day_start_local = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
    day_start_local_next = day_start_local + pd.Timedelta(days=1)
    midnight_local = day_start_local_next.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Convert to UTC for filtering
    day_start_utc = day_start_local.astimezone(ZoneInfo("UTC"))
    midnight_utc = midnight_local.astimezone(ZoneInfo("UTC"))

    # Ensure datetime columns are parsed and timezone-aware UTC
    start_col = pd.to_datetime(entries["start_time"], errors="coerce")
    end_col = pd.to_datetime(entries["end_time"], errors="coerce")

    if start_col.dt.tz is None:
        start_col = start_col.dt.tz_localize("UTC")
    if end_col.dt.tz is None:
        end_col = end_col.dt.tz_localize("UTC")

    # Filter entries that overlap with the target date
    # An entry overlaps if start < midnight_utc AND end > day_start_utc
    overlap_mask = (start_col < midnight_utc) & (end_col > day_start_utc)
    candidates = entries.loc[overlap_mask].copy()

    if candidates.empty:
        return {
            "total_seconds": 0.0,
            "activity_breakdown": {},
            "tag_breakdown": {},
            "category_breakdown": {},
            "is_empty": True,
        }

    total_seconds = 0.0
    activity_breakdown: dict[str, float] = {}
    tag_breakdown: dict[str, float] = {}
    category_breakdown: dict[str, float] = {}

    for idx, row in candidates.iterrows():
        row_start = start_col.loc[idx]
        row_end = end_col.loc[idx]

        if pd.isna(row_start) or pd.isna(row_end):
            continue  # pragma: no cover

        row_start_ts = pd.Timestamp(row_start)
        row_end_ts = pd.Timestamp(row_end)

        # Compute portion within the target date
        effective_start = max(row_start_ts, pd.Timestamp(day_start_utc))
        effective_end = min(row_end_ts, pd.Timestamp(midnight_utc))

        # If the entry spans midnight in local time (row_end >= midnight_utc
        # and row_start < midnight_utc), clip effective_end at midnight
        if row_end_ts >= midnight_utc and row_start_ts < midnight_utc:
            effective_end = pd.Timestamp(midnight_utc)

        duration_secs = (effective_end - effective_start).total_seconds()
        if duration_secs <= 0:
            continue  # pragma: no cover

        total_seconds += duration_secs

        # Activity
        activity = str(row.get("activity", "Unknown"))
        activity_breakdown[activity] = (
            activity_breakdown.get(activity, 0.0) + duration_secs
        )

        # Tags (split equally)
        tags = _parse_list_field(row.get("tags", []))
        if tags:
            secs_per_tag = duration_secs / len(tags)
            for tag in tags:
                tag_breakdown[tag] = tag_breakdown.get(tag, 0.0) + secs_per_tag

        # Categories (split equally)
        categories = _parse_list_field(row.get("categories", []))
        if categories:
            secs_per_cat = duration_secs / len(categories)
            for category in categories:
                category_breakdown[category] = (
                    category_breakdown.get(category, 0.0) + secs_per_cat
                )

    return {
        "total_seconds": total_seconds,
        "activity_breakdown": activity_breakdown,
        "tag_breakdown": tag_breakdown,
        "category_breakdown": category_breakdown,
        "is_empty": False,
    }
