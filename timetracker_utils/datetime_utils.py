"""Datetime utilities module.

Provides functions for converting pandas timestamp columns
between timezones using familiar abbreviations.
"""

import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, available_timezones

if TYPE_CHECKING:
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
