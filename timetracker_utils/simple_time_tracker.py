"""Simple Time Tracker module.

Extends ``BaseTimeEntry`` and ``BaseTimeTracker`` to parse the
Simple Time Tracker CSV export format.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Any, ClassVar, cast

import pandas as pd
from pydantic import Field, field_validator, model_validator

from timetracker_utils.base_tracker import BaseTimeEntry, BaseTimeTracker

logger = logging.getLogger(__name__)

_VALIDATION_ONLY_COLS = {"duration_str", "duration_minutes"}


class SimpleTimeEntry(BaseTimeEntry):
    """A Simple Time Tracker CSV entry."""

    categories: list[str] = Field(
        default_factory=list,
        alias="categories",
        description="comma-delimited category strings from the CSV",
    )
    tags: list[str] = Field(
        default_factory=list,
        alias="record tags",
        description="comma-delimited tag strings from the CSV",
    )
    duration_str: str = Field(
        ...,
        alias="duration",
        description="Raw H:M:S duration string (validation only)",
    )
    duration_minutes: int | None = Field(  # type: ignore[assignment]
        default=None,
        alias="duration minutes",
        description="Duration in minutes (validation cross-check only)",
    )

    model_config = {  # noqa: RUF012
        "populate_by_name": True,
        "extra": "ignore",
    }

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def coerce_duration_minutes(cls, value: Any) -> int | None:
        """Coerce duration_minutes to int from various types."""
        if value is None or value == "":
            return None
        if isinstance(value, str):
            if value.strip() == "":
                return None
            try:
                return int(float(value))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid duration minutes: {value!r}") from exc
        if isinstance(value, (int, float)):
            return int(value)
        return None

    @field_validator("duration_str", mode="before")
    @classmethod
    def parse_duration_hms(cls, value: Any) -> str:
        """Parse and clean duration string from CSV."""
        if value is None:
            return ""
        val = str(value).strip()
        if val.upper() == "N/A" or val == "":
            return ""
        return val

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_datetime(cls, value: str | None) -> datetime | None:
        """Parse datetime from string or return existing datetime.

        Timezone policy: For Simple Time Tracker format, if no explicit timezone
        is specified in the input string, the datetime is kept as naive (treated
        as local/config timezone). If an explicit timezone is present (e.g., 'Z',
        '+00:00', or offset), it is preserved. This differs from BaseTimeEntry
        which normalizes all datetimes to UTC.
        """
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # For STT format: if no timezone is specified, keep the value
            # as naive (treat it as local / config timezone).
            has_explicit_tz = "Z" in value or (value.count("-") > 2 or "+" in value)
            if not has_explicit_tz:
                return dt.replace(tzinfo=None)
            return dt
        except (ValueError, TypeError) as exc:
            msg = f"Invalid datetime value: {value!r}"
            raise ValueError(msg) from exc

    @model_validator(mode="after")
    def validate_duration_crosscheck(self) -> "SimpleTimeEntry":
        """Validate that duration_str and duration_minutes are consistent."""
        dur_str = self.duration_str
        dur_min = self.duration_minutes
        if not dur_str and dur_min is None:
            return self
        parsed_minutes = self._parse_hms_to_minutes(dur_str)
        if (
            parsed_minutes is not None
            and dur_min is not None
            and abs(parsed_minutes - dur_min) > 1.0
        ):
            msg = (
                f"Parsed duration {parsed_minutes:.1f} min does not match "
                f"duration minutes {dur_min} (tolerance: 1 min)"
            )
            raise ValueError(msg)
        return self

    @staticmethod
    def _parse_hms_to_minutes(value: str) -> float | None:
        if not value:
            return None
        parts = value.split(":")
        try:
            if len(parts) == 3:
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 60.0 + minutes + seconds / 60.0
            elif len(parts) == 2:
                return float(parts[0]) + float(parts[1]) / 60.0
            elif len(parts) == 1:
                return float(parts[0]) / 60.0
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid H:M:S duration: {value!r}") from exc
        return None


class SimpleTimeTracker(BaseTimeTracker):
    """Facade over ``BaseTimeTracker`` for the Simple Time Tracker format."""

    _ENTRY_CLASS = SimpleTimeEntry
    _GROUPBY_FIELD = "activity"
    _REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "activity name",
        "time started",
        "time ended",
        "duration",
    }

    def _post_process_entries(self) -> None:
        if not self.entries.empty:
            self.entries = self.entries.drop(
                columns=list(_VALIDATION_ONLY_COLS & set(self.entries.columns)),
                errors="ignore",
            )

    def read_csv_string(self, csv_data: str) -> pd.DataFrame:
        """Read and validate Simple Time Tracker CSV string."""
        cleaned = csv_data.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(cleaned))
        if reader.fieldnames is not None:
            field_names = set(reader.fieldnames)
            missing = self._REQUIRED_COLUMNS - field_names
            if missing:
                msg = f"Missing required STT columns: {', '.join(sorted(missing))}"
                raise ValueError(msg)
        return super().read_csv_string(csv_data)

    def entries_by_activity(self, activity: str) -> pd.DataFrame:
        """Filter entries by activity name."""
        if self.entries.empty:
            return pd.DataFrame()
        return cast(pd.DataFrame, self.entries[self.entries["activity"] == activity])

    def total_hours_by_activity(self) -> dict[str, float]:
        """Total hours grouped by activity name."""
        if self.entries.empty:
            return {}
        grouped = self.entries.groupby("activity")["hours"].sum()
        return {str(name): round(float(total), 4) for name, total in grouped.items()}
