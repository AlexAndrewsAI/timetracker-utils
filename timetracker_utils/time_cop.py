"""TimeCop module.

Extends ``BaseTimeEntry`` and ``BaseTimeTracker`` to parse the
TimeCop-format CSV export.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import ClassVar, cast

import pandas as pd
from pydantic import Field

from timetracker_utils.base_tracker import BaseTimeEntry, BaseTimeTracker

logger = logging.getLogger(__name__)


class TimeEntry(BaseTimeEntry):
    """A TimeCop-format time tracking entry."""

    project: str = Field(
        default="",
        alias="Project",
        description="TimeCop project name (mapped to DB activity column)",
    )
    description: str = Field(
        default="",
        alias="Description",
        description="TimeCop description (mapped to DB categories list)",
    )
    combined: str = Field(
        default="",
        alias="Combined Project & Description",
        description="Pre-computed combined column; ignored at runtime",
    )

    model_config: ClassVar[dict[str, str]] = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class TimeCop(BaseTimeTracker):
    """Facade over ``BaseTimeTracker`` that reads TimeCop-format CSV data."""

    _ENTRY_CLASS = TimeEntry
    _GROUPBY_FIELD = "project"
    # "End Time" is optional because the base validator can derive it from
    # the provided "Time (hours)" column.  Requiring it would prevent the
    # back-fill behaviour exercised in the test suite.
    _REQUIRED_COLUMNS: ClassVar[set[str]] = {
        "Start Time",
        "Time (hours)",
    }

    def read_csv_string(self, csv_data: str) -> pd.DataFrame:
        """Read and validate TimeCop CSV string."""
        cleaned = csv_data.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(cleaned))
        if reader.fieldnames is not None:
            field_names = set(reader.fieldnames)
            missing = self._REQUIRED_COLUMNS - field_names
            if missing:
                msg = f"Missing required TimeCop columns: {', '.join(sorted(missing))}"
                raise ValueError(msg)
        return super().read_csv_string(csv_data)

    def _post_process_entries(self) -> None:
        if not self.entries.empty:
            if "project" in self.entries.columns:
                self.entries["activity"] = self.entries["project"]
            if "description" in self.entries.columns:
                self.entries["categories"] = self.entries["description"].apply(
                    lambda x: [str(x)] if str(x).strip() else []
                )

    def entries_by_project(self, project: str) -> pd.DataFrame:
        """Filter entries by project name."""
        if self.entries.empty:
            return pd.DataFrame()
        return cast(pd.DataFrame, self.entries[self.entries["project"] == project])

    def total_hours_by_project(self) -> dict[str, float]:
        """Total hours grouped by project name."""
        if self.entries.empty:
            return {}
        grouped = self.entries.groupby("project")["hours"].sum()
        return {str(name): round(float(total), 4) for name, total in grouped.items()}
