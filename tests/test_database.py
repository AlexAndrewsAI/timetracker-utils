"""Tests for the Database module."""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from timetracker_utils.database import (
    ActivityEntry,
    Database,
    MergeConflictError,
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
    entry = ActivityEntry(
        date="1/15/2200",
        activity="StellarCartography",
        categories=["nebula mapping"],
        tags=["tag1"],
        start_time="2200-01-15T09:00:00.000Z",
        end_time="2200-01-15T11:30:00.000Z",
        notes="",
    )
    assert entry.date == "1/15/2200"
    assert entry.activity == "StellarCartography"
    assert entry.categories == ["nebula mapping"]
    assert entry.tags == ["tag1"]
    assert not hasattr(entry, "project")
    assert not hasattr(entry, "description")


def test_activity_entry_start_time_required() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        ActivityEntry(
            date="1/15/2200",
            activity="StellarCartography",
            categories=[],
            tags=[],
            notes="",
        )


def test_database_write_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(activities)")
        columns = {row[1] for row in cur.fetchall()}
        assert columns == {
            "date", "activity", "start_time",
            "end_time", "notes", "categories", "tags",
        }
    finally:
        conn.close()


def test_database_write_stores_correct_count(tmp_path: Path) -> None:
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
        cur = conn.execute(
            "SELECT notes, categories, tags FROM activities"
        )
        row = cur.fetchone()
        assert row[0] == "second write"
        assert json.loads(row[1]) == ["cat2"]
        assert json.loads(row[2]) == ["t2"]
    finally:
        conn.close()


def test_database_entries_property_after_write(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)
    assert not db.entries.empty
    assert len(db.entries) == 2
    assert "activity" in db.entries.columns
    assert "categories" in db.entries.columns
    assert "tags" in db.entries.columns


def test_database_round_trip_preserves_lists(tmp_path: Path) -> None:
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
    assert result.iloc[0]["tags"] == ["urgent", "review"]
