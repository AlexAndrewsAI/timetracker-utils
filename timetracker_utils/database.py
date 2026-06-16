"""Database module.

Provides a Pydantic model for activity entries and a ``Database``
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


class ActivityEntry(BaseModel):
    """A single activity entry suitable for database persistence.

    Omits computed columns (``combined``, ``hours``) that are derived
    at import time from the original CSV data.

    Attributes:
        date: The date of the activity (e.g. "4/13/2026").
        project: The project or category name.
        description: A short description of the activity.
        start_time: The start timestamp in ISO 8601 format.
        end_time: The end timestamp in ISO 8601 format.
        notes: Optional notes about the activity.

    """

    date: str = Field(default="", description="The date of the activity")
    project: str = Field(default="", description="The project or category name")
    description: str = Field(
        default="", description="Short description of the activity"
    )
    start_time: datetime = Field(
        ..., description="Start timestamp in ISO 8601 format"
    )
    end_time: datetime | None = Field(
        default=None, description="End timestamp in ISO 8601 format"
    )
    notes: str = Field(default="", description="Optional notes about the activity")


class Database:
    """Handles persistence of activity entries to a SQLite database.

    Attributes:
        entries: A pandas DataFrame of database-ready activity entries.

    """

    def __init__(self) -> None:
        """Initialize an empty Database instance."""
        self.entries: pd.DataFrame = pd.DataFrame()

    def write(self, df: pd.DataFrame, db_path: str | Path) -> None:
        """Write a DataFrame to the SQLite database, wiping any existing data.

        Drops computed columns (``combined``, ``hours``), validates each row
        through :class:`ActivityEntry`, and persists to an ``activities`` table.

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

        # Validate each row through ActivityEntry
        validated = []
        for _, row in df.iterrows():
            validated.append(
                ActivityEntry(**row.to_dict())  # type: ignore[arg-type]
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
                conn.execute("DROP TABLE IF EXISTS activities")
                conn.execute(
                    "CREATE TABLE activities ("
                    "date TEXT, project TEXT, description TEXT, "
                    "start_time TEXT, end_time TEXT, notes TEXT)"
                )
            else:
                self.entries.to_sql(
                    "activities", conn, if_exists="replace", index=False
                )
            logger.info(
                "Wrote %d entries to database %s", len(self.entries), db
            )
        finally:
            conn.close()
