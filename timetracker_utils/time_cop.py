"""TimeCop module.

Provides a class that reads CSV time tracking data and validates
entries using Pydantic models.
"""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class TimeEntry(BaseModel):
    """A single time tracking entry.

    Attributes:
        date: The date of the entry (e.g. "4/13/2026").
        project: The project name.
        description: A short description of the task.
        combined: The combined project & description string.
        start_time: The start timestamp in ISO 8601 format.
        end_time: The end timestamp in ISO 8601 format.
        hours: The number of hours for the entry.
        notes: Optional notes.

    """

    date: str = Field(default="", alias="Date", description="The date of the entry")
    project: str = Field(default="", alias="Project", description="The project name")
    description: str = Field(
        default="", alias="Description", description="Short description of the task"
    )
    combined: str = Field(
        default="",
        alias="Combined Project & Description",
        description="Combined project & description string",
    )
    start_time: datetime = Field(
        ..., alias="Start Time", description="Start timestamp in ISO 8601 format"
    )
    end_time: datetime | None = Field(
        default=None, alias="End Time", description="End timestamp in ISO 8601 format"
    )
    hours: float | None = Field(
        default=None, alias="Time (hours)", description="Number of hours for the entry"
    )
    notes: str = Field(default="", alias="Notes", description="Optional notes")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @model_validator(mode="after")
    def validate_date_from_start_time(self) -> "TimeEntry":
        """Validate date against start_time.

        If date is missing, fill it from start_time. If both present,
        validate consistency.

        Returns:
            The validated TimeEntry instance.

        Raises:
            ValueError: If date and start_time are inconsistent.

        """
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
    def validate_end_time_and_hours(self) -> "TimeEntry":
        """Validate and backfill end_time and hours.

        At least one of end_time or hours must be provided.
        - If only end_time: backfill hours from start_time/end_time duration.
        - If only hours: backfill end_time from start_time + hours.
        - If both: validate they are consistent.

        Returns:
            The validated TimeEntry instance.

        Raises:
            ValueError: If neither end_time nor hours is provided, or if they are
                inconsistent.

        """
        if self.end_time is None and self.hours is None:
            msg = "At least one of End Time or Time (hours) must be provided"
            raise ValueError(msg)

        if self.end_time is not None and self.hours is None:
            # Backfill hours from duration
            delta = self.end_time - self.start_time
            self.hours = round(delta.total_seconds() / 3600.0, 4)
        elif self.hours is not None and self.end_time is None:
            # Backfill end_time from start_time + hours
            self.end_time = self.start_time + timedelta(hours=self.hours)
        elif self.end_time is not None and self.hours is not None:
            # Both present: validate consistency (within 1-minute tolerance)
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
    def parse_datetime(cls, value: str | None) -> datetime | None:
        """Parse an ISO 8601 datetime string.

        Args:
            value: The datetime string to parse.

        Returns:
            A timezone-aware datetime object, or None if value is None.

        Raises:
            ValueError: If the value cannot be parsed as a valid ISO 8601 datetime.

        """
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError) as exc:
            msg = f"Invalid datetime value: {value!r}"
            raise ValueError(msg) from exc

    @field_validator(
        "date", "project", "description", "combined", "notes", mode="before"
    )
    @classmethod
    def coerce_none_to_empty_string(cls, value: str | None) -> str:
        """Coerce None to empty string for optional string fields.

        Args:
            value: The string value to coerce.

        Returns:
            The original string, or empty string if value is None.

        """
        if value is None:
            return ""
        return value

    @field_validator("hours", mode="before")
    @classmethod
    def validate_hours(cls, value: str | float | None) -> float | None:
        """Validate hours value is non-negative and within reasonable range.

        Args:
            value: The hours value to validate.

        Returns:
            The validated hours value, or None if value is None or empty string.

        Raises:
            ValueError: If the hours value is negative or unreasonably large.

        """
        if value is None:
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
        return round(value, 4)

    def duration_seconds(self) -> float | None:
        """Calculate the duration between start and end time in seconds.

        Returns:
            The duration in seconds, or None if start or end time is not set.

        """
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()

    def duration_minutes(self) -> float | None:
        """Calculate the duration between start and end time in minutes.

        Returns:
            The duration in minutes, or None if start or end time is not set.

        """
        seconds = self.duration_seconds()
        if seconds is None:
            return None
        return seconds / 60.0


class TimeCop:
    """Reads and validates CSV time tracking data.

    Provides methods to load CSV data and access validated time entries.

    Attributes:
        entries: A pandas DataFrame of validated time entries.

    """

    def __init__(self) -> None:
        """Initialize an empty TimeCop instance."""
        self.entries: pd.DataFrame = pd.DataFrame()

    def read_csv(self, path: str | Path) -> pd.DataFrame:
        """Read and validate entries from a CSV file.

        Args:
            path: Path to the CSV file.

        Returns:
            A pandas DataFrame of validated time entries.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            csv.Error: If the CSV file cannot be parsed.
            ValidationError: If any entry fails Pydantic validation.

        """
        filepath = Path(path)
        if not filepath.exists():
            msg = f"CSV file not found: {filepath}"
            raise FileNotFoundError(msg)

        logger.info("Reading CSV from %s", filepath)
        content = filepath.read_text(encoding="utf-8")
        return self.read_csv_string(content)

    def read_csv_string(self, csv_data: str) -> pd.DataFrame:
        """Read and validate entries from a CSV string.

        Args:
            csv_data: The CSV data as a string.

        Returns:
            A pandas DataFrame of validated time entries.

        Raises:
            csv.Error: If the CSV data cannot be parsed.

        """
        # Strip BOM if present (UTF-8 BOM: \ufeff)
        cleaned = csv_data.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(cleaned))

        # Warn about extra columns that will be ignored
        if reader.fieldnames is not None:
            known_fields: set[str] = set()
            for field_name in TimeEntry.model_fields:
                field_info = TimeEntry.model_fields[field_name]
                known_fields.add(field_name)
                if field_info.alias:
                    known_fields.add(field_info.alias)
            extra_cols = set(reader.fieldnames) - known_fields
            if extra_cols:
                logger.warning(
                    "Extra columns in CSV that will be ignored: %s",
                    sorted(extra_cols),
                )

        validated_entries = [TimeEntry.model_validate(row) for row in reader]
        if validated_entries:
            self.entries = pd.DataFrame(
                [entry.model_dump() for entry in validated_entries]
            )
        else:
            self.entries = pd.DataFrame()
        logger.info("Loaded %d time entries", len(self.entries))
        return self.entries

    def total_hours(self) -> float:
        """Calculate the total hours across all entries.

        Returns:
            The sum of hours for all entries.

        """
        if self.entries.empty:
            return 0.0
        return round(float(self.entries["hours"].sum()), 4)

    def total_hours_by_project(self) -> dict[str, float]:
        """Calculate total hours grouped by project.

        Returns:
            A dictionary mapping project names to total hours.

        """
        if self.entries.empty:
            return {}
        grouped = self.entries.groupby("project")["hours"].sum()
        result: dict[str, float] = {
            str(project): round(float(hours), 4) for project, hours in grouped.items()
        }
        return result

    def entries_by_project(self, project: str) -> pd.DataFrame:
        """Get all entries for a specific project.

        Args:
            project: The project name to filter by.

        Returns:
            A pandas DataFrame of entries matching the project.

        """
        if self.entries.empty:
            return pd.DataFrame()
        result: pd.DataFrame = self.entries[self.entries["project"] == project]
        return result

    def entries_by_date(self, date: str) -> pd.DataFrame:
        """Get all entries for a specific date.

        Args:
            date: The date string to filter by (e.g. "4/13/2026").

        Returns:
            A pandas DataFrame of entries matching the date.

        """
        if self.entries.empty:
            return pd.DataFrame()
        result: pd.DataFrame = self.entries[self.entries["date"] == date]
        return result
