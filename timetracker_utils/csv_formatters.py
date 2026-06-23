"""CSV formatting and export helpers for TimeCop and Simple Time Tracker formats.

Provides functions to format DataFrames as CSV strings/files
for both the TimeCop and Simple Time Tracker export formats.
"""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from timetracker_utils.datetime_utils import resolve_tz

logger = logging.getLogger(__name__)


def _format_datetime_iso(val: object, target_tz: str = "UTC") -> str:
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return ""
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return val
    elif isinstance(val, datetime):
        dt = val
    else:
        return str(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone = resolve_tz(target_tz)
    if zone is not None:
        dt = dt.astimezone(zone)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    millis = f"{dt.microsecond // 1000:03d}"
    offset_seconds = dt.utcoffset()
    if offset_seconds is None:
        offset = "+00:00"
    else:
        total_seconds = int(offset_seconds.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        offset = f"{sign}{hours:02d}:{minutes:02d}"
    return f"{base}.{millis}{offset}"


def _compute_hours(start_time: object, end_time: object) -> str:
    if start_time is None or end_time is None:
        return ""
    if isinstance(start_time, str) and start_time.strip() == "":
        return ""
    if isinstance(end_time, str) and end_time.strip() == "":
        return ""
    try:
        if isinstance(start_time, str):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        elif isinstance(start_time, datetime):
            start_dt = start_time
        else:
            return ""
        if isinstance(end_time, str):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        elif isinstance(end_time, datetime):
            end_dt = end_time
        else:
            return ""
        delta = end_dt - start_dt
        hours = delta.total_seconds() / 3600.0
        return f"{hours:.4f}"
    except (ValueError, TypeError):
        return ""


def _seconds_to_hhmm(total_seconds: float) -> str:
    """Convert seconds to hh:mm string format."""
    total_seconds = max(0.0, total_seconds)
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"


def _format_timecop_csv(
    entries: pd.DataFrame, output_path: Path, timezone: str = "UTC"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "Date",
        "Project",
        "Description",
        "Combined Project & Description",
        "Start Time",
        "End Time",
        "Time (hours)",
        "Notes",
    ]
    if entries.empty:
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
        return
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for _, row in entries.iterrows():
            date = str(row.get("date", ""))
            project = str(row.get("activity", ""))
            description = str(row.get("categories", [""]))
            if isinstance(row.get("categories"), list):
                description = row["categories"][0] if row["categories"] else ""
            description = str(description)
            combined = f"{project}: {description}"
            start_time = row.get("start_time")
            end_time = row.get("end_time")
            notes = str(row.get("notes", ""))
            start_str = _format_datetime_iso(start_time, timezone)
            end_str = _format_datetime_iso(end_time, timezone)
            hours_str = _compute_hours(start_time, end_time)
            writer.writerow(
                [
                    date,
                    project,
                    description,
                    combined,
                    start_str,
                    end_str,
                    hours_str,
                    notes,
                ]
            )


def _format_simple_csv(
    entries: pd.DataFrame, output_path: Path, timezone: str = "UTC"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "activity name",
        "time started",
        "time ended",
        "comment",
        "categories",
        "record tags",
        "duration",
        "duration minutes",
    ]
    if entries.empty:
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
        return
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for _, row in entries.iterrows():
            activity = str(row.get("activity", ""))
            start_time = row.get("start_time")
            end_time = row.get("end_time")
            notes = str(row.get("notes", ""))
            categories = row.get("categories", [])
            if isinstance(categories, list):
                categories_str = ", ".join(categories)
            else:
                categories_str = str(categories)
            tags = row.get("tags", [])
            tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            start_str = _format_simple_datetime(start_time, timezone)
            end_str = _format_simple_datetime(end_time, timezone)
            duration_str, duration_min_str = _compute_simple_duration(
                start_time, end_time
            )
            writer.writerow(
                [
                    activity,
                    start_str,
                    end_str,
                    notes,
                    categories_str,
                    tags_str,
                    duration_str,
                    duration_min_str,
                ]
            )


def _format_simple_datetime(val: object, target_tz: str = "UTC") -> str:
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return ""
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return val
    elif isinstance(val, datetime):
        dt = val
    else:
        return str(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone = resolve_tz(target_tz)
    if zone is not None:
        dt = dt.astimezone(zone)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    millis = f"{dt.microsecond // 1000:03d}"
    offset_seconds = dt.utcoffset()
    if offset_seconds is None:
        offset = "+00:00"
    else:
        total_seconds = int(offset_seconds.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        offset = f"{sign}{hours:02d}:{minutes:02d}"
    return f"{base}.{millis}{offset}"


def _compute_simple_duration(start_time: object, end_time: object) -> tuple[str, str]:
    if start_time is None or end_time is None:
        return "", ""
    try:
        if isinstance(start_time, str):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        elif isinstance(start_time, datetime):
            start_dt = start_time
        else:
            return "", ""
        if isinstance(end_time, str):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        elif isinstance(end_time, datetime):
            end_dt = end_time
        else:
            return "", ""
        delta = end_dt - start_dt
        total_secs = int(delta.total_seconds())
        hours = total_secs // 3600
        remainder = total_secs % 3600
        minutes = remainder // 60
        seconds = remainder % 60
        duration_str = f"{hours}:{minutes}:{seconds}"
        duration_min_str = str(round(hours * 60 + minutes + seconds / 60.0, 4))
        return duration_str, duration_min_str
    except (ValueError, TypeError):
        return "", ""
