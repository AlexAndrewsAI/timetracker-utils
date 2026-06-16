"""Tests for the Database module."""
# ruff: noqa: E501 - CSV data lines exceed line length limit
# mypy: ignore-errors
# Pydantic validators handle runtime type coercion

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


def test_activity_entry_fields() -> None:
    """Test that ActivityEntry has the expected fields (no computed columns)."""
    entry = ActivityEntry(
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


def test_activity_entry_start_time_required() -> None:
    """Test that start_time is required for ActivityEntry."""
    with pytest.raises(ValidationError, match="Field required"):
        ActivityEntry(
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
        cur = conn.execute("PRAGMA table_info(activities)")
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
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_database_write_merge_keeps_existing_when_no_overlap(tmp_path: Path) -> None:
    """Test that merge keeps existing rows and adds new rows with different keys."""
    db_path = tmp_path / "test.db"
    db = Database()
    db.write(SAMPLE_DF, db_path)

    # New data with completely different project/description/times
    new_df = pd.DataFrame(
        {
            "date": ["1/17/2200"],
            "project": ["Astrobiology"],
            "description": ["sample analysis"],
            "start_time": pd.to_datetime(["2200-01-17 10:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-17 12:00:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(new_df, db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        assert count == 3  # 2 original + 1 new
    finally:
        conn.close()


# ── Merge Rule 1: Identical rows silently dropped ──────────────────────


def test_merge_drops_identical_row(tmp_path: Path) -> None:
    """Test that an identical row is silently dropped (Rule 1)."""
    db_path = tmp_path / "test.db"
    db = Database()

    # Write initial data
    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(initial_df, db_path)

    # Write the exact same data again
    db.write(initial_df, db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        assert count == 1  # No duplicate added
    finally:
        conn.close()


# ── Merge Rule 2: Blank-fill merge ─────────────────────────────────────


def test_merge_blank_fill_notes(tmp_path: Path) -> None:
    """Test that blank-fill merge fills in notes when old entry has blank notes."""
    db_path = tmp_path / "test.db"
    db = Database()

    # Write initial data with blank notes
    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(initial_df, db_path)

    # Write same entry but with notes filled in
    updated_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": ["Mapped the Triangulum Nebula"],
        }
    )
    db.write(updated_df, db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT notes FROM activities")
        notes = cur.fetchone()[0]
        assert notes == "Mapped the Triangulum Nebula"
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        assert count == 1  # Still only 1 row
    finally:
        conn.close()


def test_merge_blank_fill_date(tmp_path: Path) -> None:
    """Test that blank-fill merge fills in date when old entry has blank date."""
    db_path = tmp_path / "test.db"
    db = Database()

    # Write initial data with blank date
    initial_df = pd.DataFrame(
        {
            "date": [""],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(initial_df, db_path)

    # Write same entry but with date filled in
    updated_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(updated_df, db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT date FROM activities")
        date = cur.fetchone()[0]
        assert date == "1/15/2200"
    finally:
        conn.close()


# ── Merge Rule 3: Conflicts ────────────────────────────────────────────


def test_merge_conflict_detected(tmp_path: Path) -> None:
    """Test that a merge conflict raises MergeConflictError."""
    db_path = tmp_path / "test.db"
    db = Database()

    # Write initial data with non-blank notes
    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": ["Original notes"],
        }
    )
    db.write(initial_df, db_path)

    # Write same entry but with different non-blank notes
    conflicting_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": ["Different notes"],
        }
    )

    with pytest.raises(MergeConflictError) as exc_info:
        db.write(conflicting_df, db_path)

    assert "Merge conflict detected" in str(exc_info.value)
    assert len(exc_info.value.conflicts) == 1
    assert exc_info.value.conflicts[0]["notes"] == "Original notes"


def test_merge_conflict_on_date(tmp_path: Path) -> None:
    """Test that a conflict on the date field is detected."""
    db_path = tmp_path / "test.db"
    db = Database()

    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )
    db.write(initial_df, db_path)

    conflicting_df = pd.DataFrame(
        {
            "date": ["1/16/2200"],  # Different date
            "project": ["StellarCartography"],
            "description": ["nebula mapping"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:30:00+00:00"]),
            "notes": [""],
        }
    )

    with pytest.raises(MergeConflictError, match="Merge conflict detected"):
        db.write(conflicting_df, db_path)


def test_merge_conflict_multiple_entries(tmp_path: Path) -> None:
    """Test that multiple conflicts are all collected."""
    db_path = tmp_path / "test.db"
    db = Database()

    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/16/2200"],
            "project": ["ProjA", "ProjB"],
            "description": ["descA", "descB"],
            "start_time": pd.to_datetime(
                ["2200-01-15 09:00:00+00:00", "2200-01-16 10:00:00+00:00"]
            ),
            "end_time": pd.to_datetime(
                ["2200-01-15 11:00:00+00:00", "2200-01-16 12:00:00+00:00"]
            ),
            "notes": ["Note A", "Note B"],
        }
    )
    db.write(initial_df, db_path)

    conflicting_df = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/16/2200"],
            "project": ["ProjA", "ProjB"],
            "description": ["descA", "descB"],
            "start_time": pd.to_datetime(
                ["2200-01-15 09:00:00+00:00", "2200-01-16 10:00:00+00:00"]
            ),
            "end_time": pd.to_datetime(
                ["2200-01-15 11:00:00+00:00", "2200-01-16 12:00:00+00:00"]
            ),
            "notes": ["Different A", "Different B"],
        }
    )

    with pytest.raises(MergeConflictError) as exc_info:
        db.write(conflicting_df, db_path)

    assert len(exc_info.value.conflicts) == 2


def test_merge_conflict_max_display_limit(tmp_path: Path) -> None:
    """Test that max_conflict_display limits the displayed conflicts."""
    db_path = tmp_path / "test.db"
    db = Database()

    # Create 5 existing entries
    rows: list[dict] = []
    for i in range(5):
        rows.append(
            {
                "date": f"1/{15 + i}/2200",
                "project": "Proj",
                "description": f"desc{i}",
                "start_time": pd.to_datetime(f"2200-01-{15 + i:02d} 09:00:00+00:00"),
                "end_time": pd.to_datetime(f"2200-01-{15 + i:02d} 11:00:00+00:00"),
                "notes": f"Original note {i}",
            }
        )
    initial = pd.DataFrame(rows)
    db.write(initial, db_path)

    # Create conflicting entries with max_conflict_display=2
    conflicting_rows: list[dict] = []
    for i in range(5):
        conflicting_rows.append(
            {
                "date": f"1/{15 + i}/2200",
                "project": "Proj",
                "description": f"desc{i}",
                "start_time": pd.to_datetime(f"2200-01-{15 + i:02d} 09:00:00+00:00"),
                "end_time": pd.to_datetime(f"2200-01-{15 + i:02d} 11:00:00+00:00"),
                "notes": f"Different note {i}",
            }
        )
    conflicting = pd.DataFrame(conflicting_rows)

    with pytest.raises(MergeConflictError) as exc_info:
        db.write(conflicting, db_path, max_conflict_display=2)

    msg = str(exc_info.value)
    # Should mention the total count and that more exist
    assert "5 entr" in msg
    assert "and 3 more conflicts" in msg


def test_merge_conflict_max_display_zero_suppresses_list(tmp_path: Path) -> None:
    """Test that max_conflict_display=0 suppresses the conflict list."""
    db_path = tmp_path / "test.db"
    db = Database()

    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["ProjA"],
            "description": ["descA"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:00:00+00:00"]),
            "notes": ["Original"],
        }
    )
    db.write(initial_df, db_path)

    conflicting_df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "project": ["ProjA"],
            "description": ["descA"],
            "start_time": pd.to_datetime(["2200-01-15 09:00:00+00:00"]),
            "end_time": pd.to_datetime(["2200-01-15 11:00:00+00:00"]),
            "notes": ["Different"],
        }
    )

    with pytest.raises(MergeConflictError) as exc_info:
        db.write(conflicting_df, db_path, max_conflict_display=0)

    msg = str(exc_info.value)
    assert "Merge conflict detected" in msg
    # The conflict list should be empty since max is 0
    assert "notes=" not in msg or "project=" not in msg or msg.count("project=") == 0


# ── Mixed scenarios ────────────────────────────────────────────────────


def test_merge_mixed_new_and_identical(tmp_path: Path) -> None:
    """Test merge with a mix of new, identical, and blank-fill rows."""
    db_path = tmp_path / "test.db"
    db = Database()

    initial_df = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/16/2200", "1/17/2200"],
            "project": ["A", "B", "C"],
            "description": ["descA", "descB", "descC"],
            "start_time": pd.to_datetime([
                "2200-01-15 09:00:00+00:00",
                "2200-01-16 09:00:00+00:00",
                "2200-01-17 09:00:00+00:00",
            ]),
            "end_time": pd.to_datetime([
                "2200-01-15 11:00:00+00:00",
                "2200-01-16 11:00:00+00:00",
                "2200-01-17 11:00:00+00:00",
            ]),
            "notes": ["", "", "Note C"],
        }
    )
    db.write(initial_df, db_path)

    # Row 1 (project=A): existing notes are blank → blank-fill merge → notes become "Existing notes"
    # Row 2 (project=B): existing notes are blank → blank-fill merge → notes become "New notes for B"
    # Row 3 (project=D): new entry with different key → added
    incoming_df = pd.DataFrame(
        {
            "date": ["1/15/2200", "1/16/2200", "1/18/2200"],
            "project": ["A", "B", "D"],
            "description": ["descA", "descB", "descD"],
            "start_time": pd.to_datetime([
                "2200-01-15 09:00:00+00:00",
                "2200-01-16 09:00:00+00:00",
                "2200-01-18 10:00:00+00:00",
            ]),
            "end_time": pd.to_datetime([
                "2200-01-15 11:00:00+00:00",
                "2200-01-16 11:00:00+00:00",
                "2200-01-18 12:00:00+00:00",
            ]),
            "notes": ["Existing notes", "New notes for B", ""],
        }
    )
    db.write(incoming_df, db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        # Row 1 (blank-fill) → merged, not added as new
        # Row 2 (blank-fill) → merged, not added as new
        # Row 3 (new) → added
        # Original rows: A (notes filled), B (notes filled), C (unchanged)
        # Total = 3 original + 1 new = 4
        assert count == 4

        # Verify row 1 notes were filled (blank-fill merge)
        cur = conn.execute(
            "SELECT notes FROM activities WHERE project='A'"
        )
        notes_a = cur.fetchone()[0]
        assert notes_a == "Existing notes"

        # Verify row 2 notes were filled
        cur = conn.execute(
            "SELECT notes FROM activities WHERE project='B'"
        )
        notes_b = cur.fetchone()[0]
        assert notes_b == "New notes for B"

        # Verify row 3 notes still say "Note C" (unchanged)
        cur = conn.execute(
            "SELECT notes FROM activities WHERE project='C'"
        )
        notes_c = cur.fetchone()[0]
        assert notes_c == "Note C"

    finally:
        conn.close()


# ── Existing behavior preserved ────────────────────────────────────────


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
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activities'"
        )
        assert cur.fetchone() is not None
        cur = conn.execute("SELECT COUNT(*) FROM activities")
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
        cur = conn.execute("PRAGMA table_info(activities)")
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
        cur = conn.execute("SELECT COUNT(*) FROM activities")
        count = cur.fetchone()[0]
        assert count == 2
        cur = conn.execute("SELECT project, description FROM activities")
        rows = cur.fetchall()
        assert rows[0] == ("StellarCartography", "nebula mapping")
        assert rows[1] == ("Hydroponics", "crop harvest")
    finally:
        conn.close()
