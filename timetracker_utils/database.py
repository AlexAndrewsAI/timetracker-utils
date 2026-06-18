"""Database module for persistent activity entry storage.

Provides ActivityEntry model and Database class for SQLite persistence
with merge conflict detection and resolution.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_DROP_COLUMNS = {"combined", "hours"}
_MERGE_KEY_COLUMNS = ["start_time", "end_time", "activity"]
_MERGEABLE_COLUMNS = ["date", "notes", "categories", "tags"]


class ActivityEntry(BaseModel):
    """A persistent activity entry (Database schema)."""

    date: str = Field(default="", description="The date of the activity")
    activity: str = Field(default="", description="The activity / project name")
    start_time: datetime = Field(..., description="Start timestamp in ISO 8601 format")
    end_time: datetime | None = Field(
        default=None, description="End timestamp in ISO 8601 format"
    )
    notes: str = Field(default="", description="Notes about the activity")
    categories: list[str] = Field(
        default_factory=list, description="List of category strings"
    )
    tags: list[str] = Field(default_factory=list, description="List of tag strings")
    model_config = {"populate_by_name": True, "extra": "ignore"}

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_datetime(cls, value: Any) -> datetime | None:
        """Parse datetime from string or return existing datetime."""
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                msg = f"Invalid datetime value: {value!r}"
                raise ValueError(msg) from exc
        msg = f"Invalid datetime type: {type(value).__name__}"
        raise TypeError(msg)


class MergeConflictError(Exception):
    """Raised when a merge conflict is detected during database write."""

    def __init__(self, message: str, conflicts: list[dict[str, Any]]) -> None:
        """Initialize MergeConflictError with message and conflict details.

        Args:
            message: Error message describing the conflict.
            conflicts: List of dictionaries containing conflicting row data.

        """
        super().__init__(message)
        self.conflicts = conflicts


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _serialise_lists(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["categories", "tags"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: (
                    json.dumps(x)
                    if isinstance(x, list) and len(x) > 0
                    else ("" if _is_blank(x) else str(x))
                )
            )
    return df


def _deserialise_lists(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["categories", "tags"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: (
                    json.loads(x)
                    if isinstance(x, str) and x.startswith("[")
                    else ([] if _is_blank(x) else [str(x)])
                )
            )
    return df


def _format_row_for_display(row: dict[str, Any]) -> str:
    parts = []
    for col in [
        "date",
        "activity",
        "start_time",
        "end_time",
        "notes",
        "categories",
        "tags",
    ]:
        val = row.get(col, "")
        parts.append(f"{col}={val!r}")
    return "  " + ", ".join(parts)


class Database:
    """Handles persistence of activity entries to a SQLite database."""

    def __init__(self) -> None:
        """Initialize Database with empty entries DataFrame."""
        self.entries: pd.DataFrame = pd.DataFrame()

    def write(
        self,
        df: pd.DataFrame,
        db_path: str | Path,
        max_conflict_display: int = 100,
    ) -> None:
        """Write DataFrame to SQLite database with merge conflict detection.

        Args:
            df: DataFrame of activity entries to write.
            db_path: Path to SQLite database file.
            max_conflict_display: Maximum number of conflicts to display in error.

        """
        db = Path(db_path)
        db.parent.mkdir(parents=True, exist_ok=True)
        cols_to_drop = _DROP_COLUMNS & set(df.columns)
        if cols_to_drop:
            df = df.drop(columns=list(cols_to_drop))
        validated = []
        for _, row in df.iterrows():
            validated.append(ActivityEntry(**row.to_dict()))  # type: ignore[arg-type]
        if validated:
            incoming_df = pd.DataFrame([entry.model_dump() for entry in validated])
        else:
            incoming_df = pd.DataFrame()
        incoming_df = self._normalise_dataframe(incoming_df)
        incoming_df = _serialise_lists(incoming_df)
        conn = sqlite3.connect(str(db))
        try:
            existing_df = self._read_existing(conn)
            existing_df = self._normalise_dataframe(existing_df)
            existing_df = _serialise_lists(existing_df)
            if existing_df.empty:
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
            if merged_df.empty:
                conn.execute("DROP TABLE IF EXISTS activities")
                conn.execute(
                    "CREATE TABLE activities ("
                    "date TEXT, activity TEXT, start_time TEXT, "
                    "end_time TEXT, notes TEXT, categories TEXT, tags TEXT)"
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
        """Read activity entries from SQLite database.

        Args:
            db_path: Path to SQLite database file.

        Returns:
            DataFrame of activity entries, or empty DataFrame if file doesn't exist.

        """
        db = Path(db_path)
        if not db.exists():
            logger.info("Database %s does not exist, returning empty DataFrame", db)
            self.entries = pd.DataFrame()
            return self.entries
        conn = sqlite3.connect(str(db))
        try:
            result_df = self._read_existing(conn)
            result_df = self._normalise_dataframe(result_df)
            result_df = _deserialise_lists(result_df)
            self.entries = result_df
            logger.info("Read %d entries from database %s", len(result_df), db)
            return result_df
        finally:
            conn.close()

    @staticmethod
    def _normalise_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        for col in ["start_time", "end_time"]:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].apply(
                    lambda x: x.isoformat() if pd.notna(x) else None
                )
        expected_cols = [
            "date",
            "activity",
            "start_time",
            "end_time",
            "notes",
            "categories",
            "tags",
        ]
        for col in expected_cols:
            if col not in df.columns:
                if col in {"categories", "tags"}:
                    df[col] = [[] for _ in range(len(df))]
                elif col == "end_time":
                    df[col] = [None] * len(df)
                else:
                    df[col] = [""] * len(df)
        return df

    @staticmethod
    def _read_existing(conn: sqlite3.Connection) -> pd.DataFrame:
        try:
            result_df = pd.read_sql_query(
                "SELECT date, activity, start_time, end_time, notes, categories, tags "
                "FROM activities",
                conn,
            )
            return result_df
        except pd.errors.DatabaseError:
            return pd.DataFrame()

    @staticmethod
    def _rows_identical(
        row_a: pd.Series, row_b: pd.Series, include_key: bool = True
    ) -> bool:
        cols = _MERGEABLE_COLUMNS + (_MERGE_KEY_COLUMNS if include_key else [])
        for col in cols:
            val_a = row_a.get(col)
            val_b = row_b.get(col)
            if pd.isna(val_a) and pd.isna(val_b):
                continue
            if val_a != val_b:
                return False
        return True

    @staticmethod
    def _is_blank_fill(old_row: pd.Series, new_row: pd.Series) -> bool:
        for col in _MERGEABLE_COLUMNS:
            old_val = old_row.get(col)
            new_val = new_row.get(col)
            if _is_blank(old_val):
                continue
            if pd.isna(new_val) or _is_blank(new_val):
                return False
            if str(old_val) != str(new_val):
                return False
        return True

    @staticmethod
    def _is_conflict(old_row: pd.Series, new_row: pd.Series) -> bool:
        for col in _MERGEABLE_COLUMNS:
            old_val = old_row.get(col)
            new_val = new_row.get(col)
            if _is_blank(old_val) or _is_blank(new_val):
                continue
            if str(old_val) != str(new_val):
                return True
        return False

    @staticmethod
    def _merge_dataframes(
        existing: pd.DataFrame,
        incoming: pd.DataFrame,
        max_conflict_display: int,
    ) -> tuple[pd.DataFrame, int, int, int]:
        if incoming.empty:
            return existing, 0, 0, 0

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

        new_rows: list[pd.DataFrame] = []
        conflicts: list[dict[str, Any]] = []
        new_count = 0
        skipped_count = 0
        updated_count = 0

        for inc_idx, inc_row in incoming.iterrows():
            inc_key = inc_row["_merge_key"]
            match_mask = existing["_merge_key"] == inc_key
            match_indices = existing.index[match_mask].tolist()
            if not match_indices:
                new_rows.append(
                    incoming.iloc[[inc_idx]].drop(columns=["_merge_key"])  # type: ignore[index]
                )
                new_count += 1
                continue
            resolved = False
            for match_idx in match_indices:
                old_row = existing.loc[match_idx]
                if Database._rows_identical(old_row, inc_row, include_key=False):
                    skipped_count += 1
                    resolved = True
                    break
                updated = False
                for col in _MERGEABLE_COLUMNS:
                    new_val = inc_row.get(col)
                    if not _is_blank(new_val):
                        existing.at[match_idx, col] = new_val
                        updated = True
                if updated:
                    updated_count += 1
                    resolved = True
                    break
            if not resolved:
                logger.warning(
                    "Unresolved merge for row with key %s - treating as new", inc_key
                )
                new_rows.append(
                    incoming.iloc[[inc_idx]].drop(columns=["_merge_key"])  # type: ignore[index]
                )
        if conflicts:
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
            conflict_msgs = [_format_row_for_display(c) for c in display_conflicts]
            conflict_detail = chr(10).join(conflict_msgs)
            if total_conflicts > max_conflict_display > 0:
                remaining = total_conflicts - max_conflict_display
                conflict_detail += f"{chr(10)}  ... and {remaining} more conflicts."
            suffix = "y" if total_conflicts == 1 else "ies"
            prefix = "y has" if total_conflicts == 1 else "ies have"
            msg = (
                f"Merge conflict detected for {total_conflicts} entr{suffix}. "
                f"The following entr{prefix} the same "
                "start_time, end_time, and activity "
                f"but conflicting non-blank values:{chr(10)}{conflict_detail}"
            )
            raise MergeConflictError(msg, unique_conflicts)
        result = existing.drop(columns=["_merge_key"])
        if new_rows:
            new_concat = pd.concat(new_rows, ignore_index=True)
            result = pd.concat([result, new_concat], ignore_index=True)
        return result, new_count, skipped_count, updated_count  # type: ignore[no-any-return]
