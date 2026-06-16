"""Tests for the Database module."""

# ruff: noqa: E501 - CSV data lines exceed line length limit
# mypy: ignore-errors
# Pydantic validators handle runtime type coercion

import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from timetracker_utils.database import Database, TimeEntryDb

SAMPLE_DF = pd.DataFrame(
    {
        "date": ["1/15/2200", "1/16/2200"],
        "project": ["StellarCartography", "Hydroponics"],
        "description": ["nebula mapping", "crop harvest"],
        "combined": ["StellarCartography: nebula mapping", "Hydroponics: crop harvest"],
        "start_time": pd.to_datetime(
            ["2200-01-15 09:00:00+00:00", "2200-01-16 13:00:00+00:00"]
        ),
        "end_time": pd.to_datetime(
            ["2200-01-15 11:30:00+00:00", "2200-01-16 14:45:00+00:00"]
        ),
        "hours": [2.5, 1.75],
        "notes": ["", ""],
    }
)


def test_time_entry_db_fields() -> None:
    """Test that TimeEntryDb has the expected fields (no computed columns)."""
    entry = TimeEntryDb(
        date="1/15/2200",
        project="StellarCartography",
        description="nebula mapping",
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        notes="",
    )
    assert entry.date == "1/15/2200"
    assert entry.project == "StellarCartography"
    assert entry.description == "nebula mapping"
    # Verify combined and hours are NOT present
    assert not hasattr(entry, "combined")
    assert not hasattr(entry, "hours")


def test_time_entry_db_start_time_required() -> None:
    """Test that start_time is required for TimeEntryDb."""
    with pytest.raises(ValidationError, match="Field required"):
        TimeEntryDb(
            date="1/15/2200",
            project="StellarCartography",
            description="nebula mapping",
        )


def test_database_write_creates_table(tmp_path: Path) -> None:
    """Test that Database.write creates a SQLite table with correct schema."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(time_entries)")
        columns = {row[1] for row in cur.fetchall()}
        # Should have the core fields but NOT combined or hours
        assert "date" in columns
        assert "project" in columns
        assert "description" in columns
        assert "start_time" in columns
        assert "end_time" in columns
        assert "notes" in columns
        assert "combined" not in columns
        assert "hours" not in columns
    finally:
        conn.close()


def test_database_write_stores_correct_count(tmp_path: Path) -> None:
    """Test that Database.write stores the correct number of rows."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM time_entries")
        count = cur.fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_database_write_wipes_existing_data(tmp_path: Path) -> None:
    """Test that Database.write wipes existing data and replaces it."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)

    smaller_df = SAMPLE_DF.head(1)
    db.write(smaller_df, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM time_entries")
        count = cur.fetchone()[0]
        assert count == 1  # Only 1 row after replacement
    finally:
        conn.close()


def test_database_write_creates_parent_directories(tmp_path: Path) -> None:
    """Test that Database.write creates parent directories if they don't exist."""
    db_path = tmp_path / "nested" / "dirs" / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    assert db_path.exists()


def test_database_write_empty_dataframe(tmp_path: Path) -> None:
    """Test that Database.write handles an empty DataFrame gracefully."""
    db_path = tmp_path / "test.db"
    db = Database()
    empty_df = pd.DataFrame()
    db.write(empty_df, db_path)
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='time_entries'"
        )
        assert cur.fetchone() is not None
        cur = conn.execute("SELECT COUNT(*) FROM time_entries")
        count = cur.fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_database_write_drops_hours_and_combined(tmp_path: Path) -> None:
    """Test that the database table does NOT contain hours or combined columns."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(time_entries)")
        col_names = {row[1] for row in cur.fetchall()}
        assert "hours" not in col_names
        assert "combined" not in col_names
    finally:
        conn.close()


def test_database_entries_property_after_write(tmp_path: Path) -> None:
    """Test that db.entries is populated after write."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    assert not db.entries.empty
    assert len(db.entries) == 2
    # Should not have combined or hours
    assert "combined" not in db.entries.columns
    assert "hours" not in db.entries.columns
    assert "date" in db.entries.columns
    assert "project" in db.entries.columns


def test_database_write_from_timecop(tmp_path: Path) -> None:
    """Test end-to-end: TimeCop -> Database.write creates correct DB."""
    from timetracker_utils.time_cop import TimeCop

    SAMPLE_CSV = """\
"Date","Project","Description","Combined Project & Description","Start Time","End Time","Time (hours)","Notes"
"1/15/2200","StellarCartography","nebula mapping","StellarCartography: nebula mapping","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","2.5",""
"1/16/2200","Hydroponics","crop harvest","Hydroponics: crop harvest","2200-01-16T13:00:00.000Z","2200-01-16T14:45:00.000Z","1.75",""
"""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(cop.entries, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM time_entries")
        count = cur.fetchone()[0]
        assert count == 2
        cur = conn.execute("SELECT project, description FROM time_entries")
        rows = cur.fetchall()
        assert rows[0] == ("StellarCartography", "nebula mapping")
        assert rows[1] == ("Hydroponics", "crop harvest")
    finally:
        conn.close()
