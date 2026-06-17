"""TimeCop module.

Extends ``BaseTimeEntry`` and ``BaseTimeTracker`` to parse the
TimeCop-format CSV export.
"""

import logging
from typing import TYPE_CHECKING

from pydantic import Field

from timetracker_utils.base_tracker import BaseTimeEntry, BaseTimeTracker

if TYPE_CHECKING:
    import pandas as pd

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

    model_config = {"populate_by_name": True, "extra": "ignore"}


class TimeCop(BaseTimeTracker):
    """Facade over ``BaseTimeTracker`` that reads TimeCop-format CSV data."""

    _ENTRY_CLASS = TimeEntry
    _GROUPBY_FIELD = "project"

    def _post_process_entries(self) -> None:
        if not self.entries.empty:
            if "project" in self.entries.columns:
                self.entries["activity"] = self.entries["project"]
            if "description" in self.entries.columns:
                self.entries["categories"] = self.entries["description"].apply(
                    lambda x: [str(x)] if str(x).strip() else []
                )

    def entries_by_project(self, project: str) -> "pd.DataFrame":
        import pandas as pd

        if self.entries.empty:
            return pd.DataFrame()
        return self.entries[self.entries["project"] == project]

    def total_hours_by_project(self) -> dict[str, float]:

        if self.entries.empty:
            return {}
        grouped = self.entries.groupby("project")["hours"].sum()
        return {str(name): round(float(total), 4) for name, total in grouped.items()}
