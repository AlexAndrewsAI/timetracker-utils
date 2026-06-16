"""Database module.

Provides a Pydantic model for database-ready time entries and a ``Database``
class that writes validated entries to a SQLite database.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Columns that are computed at runtime and not persisted to the database
_DROP_COLUMNS = {"combined", "hours"}


class TimeEntryDb(BaseModel):
    """A time tracking entry suitable for database persistence.

    This model mirrors :class:`timetracker_utils.time_cop.TimeEntry` but
    omits computed columns (``combined``, ``hours``).

    Attributes:
        date: The date of the entry (e.g. "4/13/2026").
        project: The project name.
        description: A short description of the task.
        start_time: The start timestamp in ISO 8601 format.
        end_time: The end timestamp in ISO 8601 format.
        notes: Optional notes.

    """

    date: str = Field(default="", description="The date of the entry")
    project: str = Field(default="", description="The project name")
    description: str = Field(
        default="", description="Short description of the task"
    )
    start_time: datetime = Field(
        ..., description="Start timestamp in ISO 8601 format"
    )
    end_time: datetime | None = Field(
        default=None, description="End timestamp in ISO 8601 format"
    )
    notes: str = Field(default="", description="Optional notes")


class Database:
    """Handles persistence of time entries to a SQLite database.

    Attributes:
        entries: A pandas DataFrame of database-ready time entries.

    """

    def __init__(self) -> None:
        """Initialize an empty Database instance."""
        self.entries: pd.DataFrame = pd.DataFrame()

    def write(self, df: pd.DataFrame, db_path: str | Path) -> None:
        """Write a DataFrame to the SQLite database, wiping any existing data.

        Drops computed columns (``combined``, ``hours``), validates each row
        through :class:`TimeEntryDb`, and persists to a ``time_entries`` table.

        Args:
            df: The source DataFrame (typically from TimeCop).
            db_path: Path to the SQLite database file.

        """
        db = Path(db_path)
        db.parent.mkdir(parents=True, exist_ok=True)

        # Drop computed columns not needed in the database
        cols_to_drop = _DROP_COLUMNS & set(df.columns)
        if cols_to_drop:
            df = df.drop(columns=list(cols_to_drop))

        # Validate each row through TimeEntryDb
        validated = []
        for _, row in df.iterrows():
            validated.append(
                TimeEntryDb(**row.to_dict())  # type: ignore[arg-type]
            )

        if validated:
            self.entries = pd.DataFrame(
                [entry.model_dump() for entry in validated]
            )
        else:
            self.entries = pd.DataFrame()

        conn = sqlite3.connect(str(db))
        try:
            if self.entries.empty:
                conn.execute("DROP TABLE IF EXISTS time_entries")
                conn.execute(
                    "CREATE TABLE time_entries ("
                    "date TEXT, project TEXT, description TEXT, "
                    "start_time TEXT, end_time TEXT, notes TEXT)"
                )
            else:
                self.entries.to_sql(
                    "time_entries", conn, if_exists="replace", index=False
                )
            logger.info(
                "Wrote %d entries to database %s", len(self.entries), db
            )
        finally:
            conn.close()
