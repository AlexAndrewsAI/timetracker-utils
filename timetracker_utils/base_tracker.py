"""Base tracker module.

Provides shared Pydantic models and tracker base classes extended
by format-specific implementations (TimeCop, Simple Time Tracker).
"""

import csv
import io
import logging
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=r"Field name \".*\" shadows an attribute.*",
)

logger = logging.getLogger(__name__)


class BaseTimeEntry(BaseModel):
    """Shared base for all time-entry format models."""

    date: str = Field(
        default="",
        description="Date (e.g. '4/13/2026')",
        validation_alias=AliasChoices("date", "Date"),
    )
    activity: str = Field(
        default="",
        description="Activity / project name (DB canonical column)",
        validation_alias=AliasChoices("activity", "activity name", "Project"),
    )
    start_time: datetime = Field(
        ...,
        description="Start timestamp in ISO 8601 format (UTC)",
        validation_alias=AliasChoices("start_time", "Start Time", "time started"),
    )
    end_time: datetime | None = Field(
        default=None,
        description="End timestamp in ISO 8601 format (UTC)",
        validation_alias=AliasChoices("end_time", "End Time", "time ended"),
    )
    hours: float | None = Field(
        default=None,
        description="Duration in hours (derived or provided)",
        validation_alias=AliasChoices("hours", "Time (hours)"),
    )
    notes: str = Field(
        default="",
        description="Optional notes",
        validation_alias=AliasChoices("notes", "Notes"),
    )
    categories: list[str] = Field(
        default_factory=list,
        description="Optional list of category strings",
        validation_alias=AliasChoices("categories", "Description"),
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional list of tag strings",
        validation_alias=AliasChoices("tags", "record tags"),
    )
    model_config = {"populate_by_name": True, "extra": "ignore"}

    # -- validators (declaration order matters for model_validator) --

    @model_validator(mode="after")
    def validate_date_from_start_time(self) -> "BaseTimeEntry":
        """Validate and set the date from the start_time if not already set."""
        if not self.date and self.start_time:
            self.date = (
                f"{self.start_time.month}/{self.start_time.day}/{self.start_time.year}"
            )
        elif self.date and self.start_time:
            expected_date = (
                f"{self.start_time.month}/{self.start_time.day}/{self.start_time.year}"
            )
            if self.date != expected_date:
                msg = (
                    f"Date {self.date!r} does not match start_time date "
                    f"{expected_date!r}"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_end_time_and_hours(self) -> "BaseTimeEntry":
        """Validate and populate end_time and hours fields consistently."""
        if self.end_time is None and self.hours is None:
            msg = "At least one of end_time or hours must be provided"
            raise ValueError(msg)
        if self.end_time is not None and self.hours is None:
            delta = self.end_time - self.start_time
            self.hours = round(delta.total_seconds() / 3600.0, 4)
        elif self.hours is not None and self.end_time is None:
            self.end_time = self.start_time + timedelta(hours=self.hours)
        elif self.end_time is not None and self.hours is not None:
            delta = self.end_time - self.start_time
            expected_hours = delta.total_seconds() / 3600.0
            if abs(self.hours - expected_hours) > 1.0 / 60.0:
                msg = (
                    f"Hours {self.hours} does not match duration "
                    f"({expected_hours:.4f}h) between start and end time"
                )
                raise ValueError(msg)
        return self

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_datetime(
        cls, value: str | None, info: ValidationInfo | None = None
    ) -> datetime | None:
        """Parse a datetime string or return None for empty values.

        Timezone policy: If the datetime string has an explicit timezone
        (Z, +00:00, -04:00, etc.), it is converted to UTC. If no timezone is
        specified, the timezone from the config is assumed and then converted
        to UTC. This ensures consistent UTC representation in the database.

        Args:
            value: The datetime string or datetime object to parse.
            info: Pydantic validation info containing context data.

        Returns:
            A timezone-aware datetime in UTC, or None for empty values.

        """
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                # Naive datetime: assume config timezone and convert to UTC
                default_tz = (
                    info.context.get("default_timezone", "UTC")
                    if info and info.context
                    else "UTC"
                )
                from timetracker_utils.datetime_utils import resolve_tz

                zone = resolve_tz(default_tz)
                if zone is not None:
                    return value.replace(tzinfo=zone).astimezone(timezone.utc)
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                # Naive datetime string: assume config timezone and convert to UTC
                default_tz = (
                    info.context.get("default_timezone", "UTC")
                    if info and info.context
                    else "UTC"
                )
                from timetracker_utils.datetime_utils import resolve_tz

                zone = resolve_tz(default_tz)
                if zone is not None:
                    return dt.replace(tzinfo=zone).astimezone(timezone.utc)
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError) as exc:
            msg = f"Invalid datetime value: {value!r}"
            raise ValueError(msg) from exc

    @field_validator("date", "activity", "notes", mode="before")
    @classmethod
    def coerce_none_to_empty_string(cls, value: str | None) -> str:
        """Coerce None values to an empty string."""
        if value is None:
            return ""
        return value

    @field_validator("categories", "tags", mode="before")
    @classmethod
    def parse_list_fields(cls, value: Any) -> list[str]:
        """Parse comma-separated string or list into a list of strings."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip() != ""]
        if isinstance(value, str):
            parts = value.split(",")
            return [p.strip() for p in parts if p.strip() != ""]
        return [str(value).strip()] if str(value).strip() != [] else []

    @field_validator("hours", mode="before")
    @classmethod
    def validate_hours(cls, value: str | float | None) -> float | None:
        """Validate and round hours; reject negatives and values over 24."""
        if value is None or value == "":
            return None
        if isinstance(value, str):
            if value.strip() == "":
                return None
            value = float(value)
        if value < 0:
            msg = f"Hours cannot be negative: {value}"
            raise ValueError(msg)
        if value > 24:
            msg = f"Hours exceed 24 (likely data error): {value}"
            raise ValueError(msg)
        return round(value + 1e-9, 4)

    # duration_minutes is now a regular field (used by SimpleTimeEntry);
    # the method below is kept for TimeCop backward-compat and is named
    # distinctly to avoid Pydantic shadow warnings.
    def duration_minutes_calculated(self) -> float | None:
        """Calculate duration in minutes from start_time and end_time."""
        seconds = self.duration_seconds()
        if seconds is None:
            return None
        return seconds / 60.0

    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds from start_time to end_time."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()

    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes from start_time and end_time."""
        seconds = self.duration_seconds()
        if seconds is None:
            return None
        return seconds / 60.0


class BaseTimeTracker:
    """Generic facade for loading time-tracking CSV data."""

    _ENTRY_CLASS: ClassVar[type[BaseTimeEntry]] = BaseTimeEntry
    _GROUPBY_FIELD: ClassVar[str] = "activity"

    def __init__(self, default_timezone: str = "UTC") -> None:
        """Initialize the tracker with an empty DataFrame.

        Args:
            default_timezone: The timezone to assume for naive datetime strings
                (e.g., "ET", "PT", "UTC"). Defaults to "UTC".

        """
        self.entries: pd.DataFrame = pd.DataFrame()
        self.default_timezone: str = default_timezone

    def read_csv(self, path: str | Path) -> pd.DataFrame:
        """Read a CSV file and return a DataFrame of parsed time entries."""
        filepath = Path(path)
        if not filepath.exists():
            msg = f"CSV file not found: {filepath}"
            raise FileNotFoundError(msg)
        logger.info("Reading CSV from %s", filepath)
        content = filepath.read_text(encoding="utf-8")
        return self.read_csv_string(content)

    def read_csv_string(self, csv_data: str) -> pd.DataFrame:
        """Parse a CSV string and return a DataFrame of validated time entries."""
        cleaned = csv_data.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(cleaned))
        if reader.fieldnames is not None:
            known_fields: set[str] = set()
            entry_class = self._ENTRY_CLASS
            for field_name, field_info in entry_class.model_fields.items():
                known_fields.add(field_name)
                if field_info.alias:
                    known_fields.add(field_info.alias)
                if field_info.validation_alias is not None and hasattr(
                    field_info.validation_alias, "choices"
                ):
                    for alias in field_info.validation_alias.choices:
                        known_fields.add(str(alias))
            extra_cols = set(reader.fieldnames) - known_fields
            if extra_cols:
                logger.warning(
                    "Extra columns in CSV that will be ignored: %s",
                    sorted(extra_cols),
                )
        validated_entries = [
            self._ENTRY_CLASS.model_validate(
                row, context={"default_timezone": self.default_timezone}
            )
            for row in reader
        ]
        if validated_entries:
            self.entries = pd.DataFrame(
                [entry.model_dump() for entry in validated_entries]
            )
        else:
            self.entries = pd.DataFrame()
        self._post_process_entries()
        logger.info("Loaded %d time entries", len(self.entries))
        return self.entries

    def _post_process_entries(self) -> None:
        """Remap columns after build as needed by subclasses."""

    def total_hours(self) -> float:
        """Return the total hours summed across all entries."""
        if self.entries.empty:
            return 0.0
        return round(float(self.entries["hours"].sum()), 4)

    def total_hours_by_activity(self) -> dict[str, float]:
        """Return total hours grouped by activity."""
        if self.entries.empty:
            return {}
        group_field = self._GROUPBY_FIELD
        grouped = self.entries.groupby(group_field)["hours"].sum()
        return {str(name): round(float(total), 4) for name, total in grouped.items()}

    def entries_by_activity(self, activity: str) -> pd.DataFrame:
        """Return entries filtered by the given activity name."""
        if self.entries.empty:
            return pd.DataFrame()
        group_field = self._GROUPBY_FIELD
        return self.entries[self.entries[group_field] == activity]  # type: ignore[no-any-return]

    def entries_by_date(self, date: str) -> pd.DataFrame:
        """Return entries filtered by the given date string."""
        if self.entries.empty:
            return pd.DataFrame()
        return self.entries[self.entries["date"] == date]  # type: ignore[no-any-return]
