"""Database module.

Provides a Pydantic model for activity entries and a ``Database``
class that writes validated entries to a SQLite database with
merge semantics.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Columns that are computed at runtime and not persisted to the database
_DROP_COLUMNS = {"combined", "hours"}

# Columns that form the merge key (identifying a unique activity)
_MERGE_KEY_COLUMNS = ["start_time", "end_time", "project", "description"]

# Columns that can be silently filled in (merged) when the old value is blank
_MERGEABLE_COLUMNS = ["date", "notes"]


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
    start_time: datetime = Field(..., description="Start timestamp in ISO 8601 format")
    end_time: datetime | None = Field(
        default=None, description="End timestamp in ISO 8601 format"
    )
    notes: str = Field(default="", description="Optional notes about the activity")


def _is_blank(value: Any) -> bool:
    """Check whether a value is considered blank (empty string or None).

    Args:
        value: The value to check.

    Returns:
        True if the value is None or an empty string.

    """
    return value is None or (isinstance(value, str) and value.strip() == "")


def _format_row_for_display(row: dict[str, Any]) -> str:
    """Format a row dictionary into a human-readable string for conflict output.

    Args:
        row: A dictionary of column values.

    Returns:
        A formatted string representation.

    """
    parts = []
    for col in ["date", "project", "description", "start_time", "end_time", "notes"]:
        val = row.get(col, "")
        parts.append(f"{col}={val!r}")
    return "  " + ", ".join(parts)


class MergeConflictError(Exception):
    """Raised when a merge conflict is detected during database write."""

    def __init__(self, message: str, conflicts: list[dict[str, Any]]) -> None:
        """Initialize the exception.

        Args:
            message: A human-readable error message.
            conflicts: A list of conflicting row dictionaries (old entries).

        """
        super().__init__(message)
        self.conflicts = conflicts


class Database:
    """Handles persistence of activity entries to a SQLite database.

    Supports merging new entries into an existing database rather than
    overwriting it entirely.

    Attributes:
        entries: A pandas DataFrame of database-ready activity entries.

    """

    def __init__(self) -> None:
        """Initialize an empty Database instance."""
        self.entries: pd.DataFrame = pd.DataFrame()

    def write(
        self,
        df: pd.DataFrame,
        db_path: str | Path,
        max_conflict_display: int = 100,
    ) -> None:
        """Write a DataFrame to the SQLite database, merging with existing data.

        Merge rules:

        1. **Duplicate row:** If an incoming row is identical to an existing
           row (all columns match), it is silently dropped.

        2. **Blank-fill merge:** If an incoming row has the same key
           (``start_time``, ``end_time``, ``project``, ``description``) as
           an existing row, and the existing row has blank values (empty
           string or ``None``) in the mergeable columns (``date``, ``notes``)
           where the incoming row has non-blank values, the existing row is
           updated with the incoming values.

        3. **Conflict:** If an incoming row has the same key as an existing
           row, but the existing row has non-blank values that differ from
           the incoming values in a mergeable column, a
           :class:`MergeConflictError` is raised. The error message lists up
           to *max_conflict_display* conflicting entries.

        Drops computed columns (``combined``, ``hours``), validates each row
        through :class:`ActivityEntry`, and persists to an ``activities`` table.

        Args:
            df: The source DataFrame (typically from TimeCop).
            db_path: Path to the SQLite database file.
            max_conflict_display: Maximum number of conflicting entries to
                display in the error message (default 100). A value of 0
                suppresses the conflict list.

        Raises:
            MergeConflictError: If unresolvable merge conflicts are detected.

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
            incoming_df = pd.DataFrame([entry.model_dump() for entry in validated])
        else:
            incoming_df = pd.DataFrame()

        # Normalise column types for consistent comparison
        incoming_df = self._normalise_dataframe(incoming_df)

        conn = sqlite3.connect(str(db))
        try:
            existing_df = self._read_existing(conn)
            existing_df = self._normalise_dataframe(existing_df)

            if existing_df.empty:
                # No existing data — just write the incoming data
                merged_df = incoming_df
                new_count = len(incoming_df)
                skipped_count = 0
                updated_count = 0
            else:
                merged_df, new_count, skipped_count, updated_count = (
                    self._merge_dataframes(
                        existing_df, incoming_df, max_conflict_display
                    )
                )

            # Write the merged result
            if merged_df.empty:
                conn.execute("DROP TABLE IF EXISTS activities")
                conn.execute(
                    "CREATE TABLE activities ("
                    "date TEXT, project TEXT, description TEXT, "
                    "start_time TEXT, end_time TEXT, notes TEXT)"
                )
            else:
                merged_df.to_sql("activities", conn, if_exists="replace", index=False)

            self.entries = merged_df
            written_count = new_count + updated_count
            logger.info(
                "Wrote %d entries to database %s (%d new, %d updated, %d skipped)",
                written_count,
                db,
                new_count,
                updated_count,
                skipped_count,
            )
        finally:
            conn.close()

    def read(self, db_path: str | Path) -> pd.DataFrame:
        """Read all entries from the database.

        Args:
            db_path: Path to the SQLite database file.

        Returns:
            A DataFrame of all entries in the database, or an empty
            DataFrame if the table does not exist or has no data.

        """
        db = Path(db_path)
        if not db.exists():
            logger.info("Database %s does not exist, returning empty DataFrame", db)
            self.entries = pd.DataFrame()
            return self.entries

        conn = sqlite3.connect(str(db))
        try:
            result = self._read_existing(conn)
            self.entries = result
            logger.info("Read %d entries from database %s", len(result), db)
            return result
        finally:
            conn.close()

    @staticmethod
    def _normalise_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise column types for consistent comparison.

        Converts datetime columns to string representations and fills
        missing values with empty strings.

        Args:
            df: The DataFrame to normalise.

        Returns:
            A normalised DataFrame with consistent types.

        """
        if df.empty:
            return df

        df = df.copy()

        # Convert datetime columns to ISO string for consistent comparison
        for col in ["start_time", "end_time"]:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].apply(
                    lambda x: x.isoformat() if pd.notna(x) else None
                )

        # Ensure all expected columns exist
        expected_cols = [
            "date",
            "project",
            "description",
            "start_time",
            "end_time",
            "notes",
        ]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = "" if col != "end_time" else None

        return df

    @staticmethod
    def _read_existing(conn: sqlite3.Connection) -> pd.DataFrame:
        """Read existing data from the activities table.

        Args:
            conn: An open SQLite connection.

        Returns:
            A DataFrame of existing entries, or an empty DataFrame if the
            table does not exist or has no data.

        """
        try:
            result_df = pd.read_sql_query(
                "SELECT date, project, description, start_time, end_time, notes "
                "FROM activities",
                conn,
            )
            return result_df
        except pd.errors.DatabaseError:
            return pd.DataFrame()

    @staticmethod
    def _merge_dataframes(
        existing: pd.DataFrame,
        incoming: pd.DataFrame,
        max_conflict_display: int,
    ) -> tuple[pd.DataFrame, int, int, int]:
        """Merge an incoming DataFrame into an existing DataFrame.

        Args:
            existing: The existing data from the database.
            incoming: The new data to merge in.
            max_conflict_display: Maximum number of conflicts to list.

        Returns:
            A tuple of (merged DataFrame, new rows count, updated rows count,
            skipped (identical) rows count).

        Raises:
            MergeConflictError: If unresolvable conflicts are detected.

        """
        if incoming.empty:
            return existing, 0, 0, 0

        # Build a key column for matching
        def _make_key(row: pd.Series) -> str:
            parts = []
            for col in _MERGE_KEY_COLUMNS:
                val = row.get(col)
                if pd.isna(val):
                    parts.append("")
                else:
                    parts.append(str(val))
            return "|".join(parts)

        existing = existing.reset_index(drop=True)
        incoming = incoming.reset_index(drop=True)

        existing["_merge_key"] = existing.apply(_make_key, axis=1)
        incoming["_merge_key"] = incoming.apply(_make_key, axis=1)

        # Separate incoming rows into: new, identical, blank-fill, conflict
        new_rows: list[pd.DataFrame] = []
        conflicts: list[dict[str, Any]] = []
        new_count = 0
        skipped_count = 0
        updated_count = 0

        for inc_idx, inc_row in incoming.iterrows():
            inc_key = inc_row["_merge_key"]

            # Find matching existing row(s)
            match_mask = existing["_merge_key"] == inc_key
            match_indices = existing.index[match_mask].tolist()

            if not match_indices:
                # No match — this is a new row
                new_rows.append(
                    incoming.iloc[[inc_idx]].drop(columns=["_merge_key"])  # type: ignore[index]
                )
                new_count += 1
                continue

            # There could be multiple matches; handle each independently
            # (though in practice the key should be unique)
            resolved = False
            for match_idx in match_indices:
                old_row = existing.loc[match_idx]

                # Check if identical
                if Database._rows_identical(old_row, inc_row, include_key=False):
                    # Rule 1: silently drop the incoming row
                    # Keep the existing row as-is
                    skipped_count += 1
                    resolved = True
                    break

                # Check if this is a blank-fill merge (Rule 2)
                if Database._is_blank_fill(old_row, inc_row):
                    # Rule 2: replace old with new data
                    for col in _MERGEABLE_COLUMNS:
                        new_val = inc_row.get(col)
                        if not _is_blank(new_val):
                            existing.at[match_idx, col] = new_val
                    updated_count += 1
                    resolved = True
                    break

                # Check for conflict (Rule 3)
                if Database._is_conflict(old_row, inc_row):
                    # Record the conflict using the old row data
                    conflict_row = {
                        col: old_row.get(col, "") for col in _MERGEABLE_COLUMNS
                    }
                    for col in _MERGE_KEY_COLUMNS:
                        conflict_row[col] = old_row.get(col, "")
                    conflicts.append(conflict_row)
                    resolved = True
                    break

            if not resolved:
                # No matching logic applied — treat as new row (shouldn't happen)
                logger.warning(
                    "Unresolved merge for row with key %s — treating as new",
                    inc_key,
                )
                new_rows.append(
                    incoming.iloc[[inc_idx]].drop(columns=["_merge_key"])  # type: ignore[index]
                )

        if conflicts:
            # Use a set to deduplicate by the merge key
            seen_keys: set[str] = set()
            unique_conflicts: list[dict[str, Any]] = []
            for c in conflicts:
                key = "|".join(str(c.get(col, "")) for col in _MERGE_KEY_COLUMNS)
                if key not in seen_keys:
                    seen_keys.add(key)
                    unique_conflicts.append(c)

            display_conflicts = (
                unique_conflicts[:max_conflict_display]
                if max_conflict_display > 0
                else []
            )
            total_conflicts = len(unique_conflicts)
            conflict_msgs = []
            for c in display_conflicts:
                conflict_msgs.append(_format_row_for_display(c))
            conflict_detail = "\n".join(conflict_msgs)
            if total_conflicts > max_conflict_display > 0:
                remaining = total_conflicts - max_conflict_display
                conflict_detail += f"\n  ... and {remaining} more conflicts."

            suffix = "y" if total_conflicts == 1 else "ies"
            prefix = "y has" if total_conflicts == 1 else "ies have"
            msg = (
                f"Merge conflict detected for {total_conflicts} entr{suffix}. "
                f"The following entr{prefix} the same "
                "start_time, end_time, project, and description "
                f"but conflicting non-blank values:\n"
                f"{conflict_detail}"
            )
            raise MergeConflictError(msg, unique_conflicts)

        # Build the result: existing rows + new rows
        result = existing.drop(columns=["_merge_key"])
        if new_rows:
            new_concat = pd.concat(new_rows, ignore_index=True)
            result = pd.concat([result, new_concat], ignore_index=True)

        # Ensure we return a DataFrame (mypy: drop() returns DataFrame)
        return result, new_count, skipped_count, updated_count  # type: ignore[no-any-return]

    @staticmethod
    def _rows_identical(
        row_a: pd.Series,
        row_b: pd.Series,
        include_key: bool = True,
    ) -> bool:
        """Check if two rows are identical across all columns.

        Args:
            row_a: First row to compare.
            row_b: Second row to compare.
            include_key: If True, also compare key columns.

        Returns:
            True if the rows are identical.

        """
        cols = _MERGEABLE_COLUMNS + (_MERGE_KEY_COLUMNS if include_key else [])
        for col in cols:
            val_a = row_a.get(col)
            val_b = row_b.get(col)
            # Normalise NaN/None to the same representation
            if pd.isna(val_a) and pd.isna(val_b):
                continue
            if val_a != val_b:
                return False
        return True

    @staticmethod
    def _is_blank_fill(old_row: pd.Series, new_row: pd.Series) -> bool:
        """Check if a new row is a valid blank-fill merge of an old row.

        The key columns must match (caller ensures this), and for each
        mergeable column, the old value must be blank when the new value
        is non-blank. If the old value is non-blank and differs from the
        new value, this is not a blank-fill.

        Args:
            old_row: The existing row from the database.
            new_row: The incoming row.

        Returns:
            True if the new row can be merged via blank-fill.

        """
        for col in _MERGEABLE_COLUMNS:
            old_val = old_row.get(col)
            new_val = new_row.get(col)
            if _is_blank(old_val):
                # Old is blank — new can fill it (even if new is also blank)
                continue
            # Old is non-blank
            if pd.isna(new_val) or _is_blank(new_val):
                # New is blank — old stays, this is not a blank-fill
                return False
            if str(old_val) != str(new_val):
                # Both non-blank and different — not a blank-fill
                return False
        # All mergeable columns either matched or were blank-fillable
        return True

    @staticmethod
    def _is_conflict(old_row: pd.Series, new_row: pd.Series) -> bool:
        """Check if a new row conflicts with an old row.

        A conflict occurs when the key columns match (caller ensures this)
        and at least one mergeable column has non-blank values that differ.

        Args:
            old_row: The existing row from the database.
            new_row: The incoming row.

        Returns:
            True if there is a conflict.

        """
        for col in _MERGEABLE_COLUMNS:
            old_val = old_row.get(col)
            new_val = new_row.get(col)
            if _is_blank(old_val) or _is_blank(new_val):
                # At least one is blank — no conflict possible
                continue
            if str(old_val) != str(new_val):
                # Both non-blank and different — conflict!
                return True
        return False
