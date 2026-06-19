"""Tests for the Database module."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from timetracker_utils.database import (
    ActivityEntry,
    Database,
)

SAMPLE_DF = pd.DataFrame(
    {
        "date": ["1/15/2200", "1/16/2200"],
        "activity": ["StellarCartography", "Hydroponics"],
        "start_time": pd.to_datetime(
            ["2200-01-15 09:00:00+00:00", "2200-01-16 13:00:00+00:00"]
        ),
        "end_time": pd.to_datetime(
            ["2200-01-15 11:30:00+00:00", "2200-01-16 14:45:00+00:00"]
        ),
        "hours": [2.5, 1.75],
        "notes": ["", ""],
        "categories": [["nebula mapping"], ["crop harvest"]],
        "tags": [["tag1"], []],
    }
)


def test_activity_entry_fields() -> None:
    """Test ActivityEntry field validation and attribute presence."""
    entry = ActivityEntry(
        date="1/15/2200",
        activity="StellarCartography",
        categories=["nebula mapping"],
        tags=["tag1"],
        start_time=datetime(2200, 1, 15, 9, 0, tzinfo=None),
        end_time=datetime(2200, 1, 15, 11, 30, tzinfo=None),
        notes="",
    )
    assert entry.date == "1/15/2200"
    assert entry.activity == "StellarCartography"
    assert entry.categories == ["nebula mapping"]
    assert entry.tags == ["tag1"]
    assert not hasattr(entry, "project")
    assert not hasattr(entry, "description")


def test_activity_entry_start_time_required() -> None:
    """Test that start_time is a required field for ActivityEntry."""
    with pytest.raises(ValidationError, match="Field required"):
        ActivityEntry(  # type: ignore[call-arg]
            date="1/15/2200",
            activity="StellarCartography",
            categories=[],
            tags=[],
            notes="",
        )


def test_database_write_creates_table(tmp_path: Path) -> None:
    """Test that writing to database creates the activities table."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(activities)")
        columns = {row[1] for row in cur.fetchall()}
        assert columns == {
            "date",
            "activity",
            "start_time",
            "end_time",
            "notes",
            "categories",
            "tags",
        }
    finally:
        conn.close()


def test_database_write_stores_correct_count(tmp_path: Path) -> None:
    """Test that writing to database stores the correct number of entries."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        assert cur.fetchone()[0] == 2
    finally:
        conn.close()


def test_database_write_overwrites_existing(tmp_path: Path) -> None:
    """Test that writing to database overwrites existing entries."""
    db_path = tmp_path / "test.db"
    df1 = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": ["first write"],
            "categories": [["cat1"]],
            "tags": [["t1"]],
        }
    )
    db = Database()
    db.write(df1, db_path)
    df2 = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": ["second write"],
            "categories": [["cat2"]],
            "tags": [["t2"]],
        }
    )
    db.write(df2, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        assert cur.fetchone()[0] == 1
        cur = conn.execute("SELECT notes, categories, tags FROM activities")
        row = cur.fetchone()
        assert row[0] == "second write"
        assert json.loads(row[1]) == ["cat2"]
        assert json.loads(row[2]) == ["t2"]
    finally:
        conn.close()


def test_database_entries_property_after_write(tmp_path: Path) -> None:
    """Test that the entries property is populated after write."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    assert not db.entries.empty
    assert len(db.entries) == 2
    assert "activity" in db.entries.columns
    assert "categories" in db.entries.columns
    assert "tags" in db.entries.columns


def test_database_round_trip_preserves_lists(tmp_path: Path) -> None:
    """Test that writing and reading preserves list fields."""
    db_path = tmp_path / "test.db"
    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["WarpDrive"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 12:00:00+00:00"]),
            "hours": [3.0],
            "notes": ["plasma"],
            "categories": [["cat1", "cat2"]],
            "tags": [["urgent", "review"]],
        }
    )
    db = Database()
    db.write(df, db_path)
    result = db.read(db_path)
    assert len(result) == 1
    assert result.iloc[0]["categories"] == ["cat1", "cat2"]


def test_database_write_empty_df(tmp_path: Path) -> None:
    """Test writing an empty DataFrame (hits validated empty path, line 114)."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(pd.DataFrame(), db_path)
    assert db.entries.empty
    # Database directory should still be created
    assert db_path.parent.exists()


def test_database_write_drops_combined_and_hours_cols(tmp_path: Path) -> None:
    """Test that 'combined' and 'hours' columns are dropped before write."""
    db_path = tmp_path / "test.db"
    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["Test"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": [""],
            "categories": [[]],
            "tags": [[]],
            "combined": ["Test: work"],
        }
    )
    db = Database()
    db.write(df, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(activities)")
        columns = {row[1] for row in cur.fetchall()}
        assert "combined" not in columns
    finally:
        conn.close()


def test_database_read_nonexistent(tmp_path: Path) -> None:
    """Test reading from a non-existent database returns empty DataFrame."""
    db_path = tmp_path / "nonexistent.db"
    db = Database()
    result = db.read(db_path)
    assert result.empty
    assert db.entries.empty


def test_database_normalize_missing_columns() -> None:
    """Test Database._normalise_dataframe adds missing columns (lines 193-198)."""
    df = pd.DataFrame({"date": ["1/15/2200"]})
    result = Database._normalise_dataframe(df)
    expected_cols = {
        "date",
        "activity",
        "start_time",
        "end_time",
        "notes",
        "categories",
        "tags",
    }
    assert expected_cols.issubset(set(result.columns))
    # categories/tags should be lists
    assert result["categories"].iloc[0] == []
    assert result["tags"].iloc[0] == []
    # end_time should be None
    assert result["end_time"].iloc[0] is None


def test_database_normalize_empty() -> None:
    """Test _normalise_dataframe with empty DataFrame returns it unchanged."""
    result = Database._normalise_dataframe(pd.DataFrame())
    assert result.empty


def test_database_rows_identical_with_none() -> None:
    """Test _rows_identical handles None values (lines 222, 225)."""
    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["Test"],
            "start_time": ["2026-04-13T10:45:00"],
            "end_time": [None],
            "notes": [None],
            "categories": [""],
            "tags": [""],
        }
    )
    row_a = df.iloc[0]
    row_b = df.iloc[0].copy()
    # Same row should be identical
    assert Database._rows_identical(row_a, row_b)


def test_database_rows_identical_different_values() -> None:
    """Test _rows_identical returns False when values differ."""
    df = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/16/2200"],
            "activity": ["A", "B"],
            "start_time": ["2026-04-13T10:00:00", "2026-04-13T11:00:00"],
            "end_time": ["2026-04-13T11:00:00", "2026-04-13T12:00:00"],
            "notes": ["note1", "note2"],
            "categories": ["", ""],
            "tags": ["", ""],
        }
    )
    assert not Database._rows_identical(df.iloc[0], df.iloc[1])


def test_database_is_blank_fill_true() -> None:
    """Test _is_blank_fill returns True when old values are blank (skipped)."""
    old = pd.Series({"date": "1/15/2200", "notes": "", "categories": "", "tags": ""})
    new = pd.Series(
        {"date": "1/15/2200", "notes": "existing", "categories": "", "tags": ""}
    )
    assert Database._is_blank_fill(old, new)


def test_database_is_blank_fill_new_has_different_value() -> None:
    """Test _is_blank_fill returns False when new row has different non-blank value."""
    old = pd.Series(
        {"date": "1/15/2200", "notes": "existing", "categories": [], "tags": []}
    )
    new = pd.Series(
        {"date": "1/15/2200", "notes": "different", "categories": [], "tags": []}
    )
    assert not Database._is_blank_fill(old, new)


def test_database_is_conflict_true() -> None:
    """Test _is_conflict returns True when non-blank values differ."""
    old = pd.Series(
        {"date": "1/15/2200", "notes": "note1", "categories": [], "tags": []}
    )
    new = pd.Series(
        {"date": "1/15/2200", "notes": "note2", "categories": [], "tags": []}
    )
    assert Database._is_conflict(old, new)


def test_database_is_conflict_blank_old_not_conflict() -> None:
    """Test _is_conflict returns False when old value is blank."""
    old = pd.Series({"date": "1/15/2200", "notes": "", "categories": [], "tags": []})
    new = pd.Series(
        {"date": "1/15/2200", "notes": "note2", "categories": [], "tags": []}
    )
    assert not Database._is_conflict(old, new)


def test_database_is_conflict_blank_new_not_conflict() -> None:
    """Test _is_conflict returns False when new value is blank."""
    old = pd.Series(
        {"date": "1/15/2200", "notes": "note1", "categories": [], "tags": []}
    )
    new = pd.Series({"date": "1/15/2200", "notes": "", "categories": [], "tags": []})
    assert not Database._is_conflict(old, new)


def test_database_merge_dataframes_incoming_empty() -> None:
    """Test _merge_dataframes returns existing when incoming is empty (line 258)."""
    existing = pd.DataFrame(
        {"date": ["1/15/2200"], "activity": ["A"], "start_time": ["09:00"]}
    )
    result, new_count, skipped, updated = Database._merge_dataframes(
        existing, pd.DataFrame(), 100
    )
    assert len(result) == 1
    assert new_count == 0
    assert skipped == 0
    assert updated == 0


def test_database_write_with_merge_skipped(tmp_path: Path) -> None:
    """Test that identical rows are skipped during merge."""
    db_path = tmp_path / "test.db"
    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": ["same"],
            "categories": [["cat1"]],
            "tags": [["t1"]],
        }
    )
    db = Database()
    db.write(df, db_path)
    # Write same data again
    db.write(df, db_path)
    # Should still be 1 entry (skipped the duplicate)
    assert len(db.entries) == 1


def test_database_write_with_update(tmp_path: Path) -> None:
    """Test that existing rows get updated with new non-blank values."""
    db_path = tmp_path / "test.db"
    df1 = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": [""],
            "categories": [[]],
            "tags": [[]],
        }
    )
    df2 = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "hours": [2.5],
            "notes": ["filled note"],
            "categories": [["cat1"]],
            "tags": [["t1"]],
        }
    )
    db = Database()
    db.write(df1, db_path)
    db.write(df2, db_path)
    assert len(db.entries) == 1
    assert db.entries.iloc[0]["notes"] == "filled note"


def test_merge_conflict_error() -> None:
    """Test MergeConflictError creation (lines 38-40)."""
    from timetracker_utils.database import MergeConflictError

    err = MergeConflictError(
        "test conflict",
        [{"date": "1/15/2200", "notes": "conflict"}],
    )
    assert str(err) == "test conflict"
    assert len(err.conflicts) == 1
    assert err.conflicts[0]["date"] == "1/15/2200"
