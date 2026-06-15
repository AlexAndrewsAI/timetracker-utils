"""Tests for the TimeCop module."""

# ruff: noqa: E501 - CSV data lines exceed line length limit
# mypy: ignore-errors - Pydantic validators handle str->datetime conversion at runtime

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from timetracker_utils.time_cop import TimeCop, TimeEntry

SAMPLE_CSV = """\
"Date","Project","Description","Combined Project & Description","Start Time","End Time","Time (hours)","Notes"
"1/15/2200","StellarCartography","nebula mapping","StellarCartography: nebula mapping","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","2.5",""
"1/15/2200","Hydroponics","crop harvest","Hydroponics: crop harvest","2200-01-15T13:00:00.000Z","2200-01-15T14:45:00.000Z","1.75",""
"1/15/2200","StellarCartography","","StellarCartography: ","2200-01-15T21:00:00.000Z","2200-01-15T22:30:00.000Z","1.5",""
"1/16/2200","CrewFitness","strength training","CrewFitness: strength training","2200-01-16T06:00:00.000Z","2200-01-16T07:00:00.000Z","1.0",""
"1/16/2200","Hydroponics","nutrient mix","Hydroponics: nutrient mix","2200-01-16T10:15:00.000Z","2200-01-16T11:45:00.000Z","1.5",""
"1/16/2200","StellarCartography","course plotting","StellarCartography: course plotting","2200-01-16T20:30:00.000Z","2200-01-16T22:15:00.000Z","1.75",""
"1/17/2200","WarpDrive","plasma calibration","WarpDrive: plasma calibration","2200-01-17T08:00:00.000Z","2200-01-17T12:30:00.000Z","4.5","critical test"
"1/17/2200","Hydroponics","pH adjustment","Hydroponics: pH adjustment","2200-01-17T14:00:00.000Z","2200-01-17T15:30:00.000Z","1.5",""
"1/17/2200","CrewFitness","cardiovascular","CrewFitness: cardiovascular","2200-01-17T17:00:00.000Z","2200-01-17T18:30:00.000Z","1.5",""
"1/20/2200","WarpDrive","coil winding","WarpDrive: coil winding","2200-01-20T09:30:00.000Z","2200-01-20T13:30:00.000Z","4.0",""
"1/20/2200","StellarCartography","asteroid tracking","StellarCartography: asteroid tracking","2200-01-20T15:00:00.000Z","2200-01-20T16:45:00.000Z","1.75",""
"1/20/2200","CrewFitness","yoga session","CrewFitness: yoga session","2200-01-20T19:00:00.000Z","2200-01-20T20:00:00.000Z","1.0",""
"""


def test_time_entry_valid() -> None:
    """Test creating a valid TimeEntry."""
    entry = TimeEntry(
        date="4/13/2026",
        project="Commute",
        description="drive",
        combined="Commute: drive",
        start_time="2026-04-13T10:45:00.000Z",
        end_time="2026-04-13T11:45:39.074Z",
        hours=1.0108,
        notes="",
    )
    assert entry.date == "4/13/2026"
    assert entry.project == "Commute"
    assert entry.description == "drive"
    assert entry.hours == 1.0108


def test_time_entry_duration() -> None:
    """Test duration calculation on TimeEntry."""
    entry = TimeEntry(
        date="4/13/2026",
        project="Commute",
        description="drive",
        combined="Commute: drive",
        start_time="2026-04-13T10:45:00.000Z",
        end_time="2026-04-13T11:45:39.074Z",
        hours=1.0108,
        notes="",
    )
    # 1 hour = 3600 seconds, + 39 seconds + 0.074 seconds = 3639.074
    expected_seconds = 3639.074
    assert abs(entry.duration_seconds() - expected_seconds) < 0.001
    expected_minutes = expected_seconds / 60.0
    assert abs(entry.duration_minutes() - expected_minutes) < 0.001


def test_time_entry_with_descriptions() -> None:
    """Test that TimeEntry can handle empty description."""
    entry = TimeEntry(
        date="4/15/2026",
        project="Commute",
        description="",
        combined="Commute: ",
        start_time="2026-04-15T11:00:00.000Z",
        end_time="2026-04-15T12:17:04.327Z",
        hours=1.2844,
        notes="",
    )
    assert entry.description == ""


def test_time_entry_with_notes() -> None:
    """Test that TimeEntry accepts notes."""
    entry = TimeEntry(
        date="4/20/2026",
        project="Break",
        description="lunch",
        combined="Break: lunch",
        start_time="2026-04-20T17:01:00.000Z",
        end_time="2026-04-20T17:15:00.000Z",
        hours=0.2333,
        notes="short lunch",
    )
    assert entry.notes == "short lunch"


def test_time_entry_alias_mapping() -> None:
    """Test that TimeEntry can be created with CSV column names as aliases."""
    entry = TimeEntry(
        **{
            "Date": "4/13/2026",
            "Project": "Commute",
            "Description": "drive",
            "Combined Project & Description": "Commute: drive",
            "Start Time": "2026-04-13T10:45:00.000Z",
            "End Time": "2026-04-13T11:45:39.074Z",
            "Time (hours)": 1.0108,
            "Notes": "",
        }
    )
    assert entry.date == "4/13/2026"
    assert entry.project == "Commute"
    assert entry.hours == 1.0108


def test_time_entry_negative_hours() -> None:
    """Test that negative hours raises validation error."""
    with pytest.raises(ValidationError):
        TimeEntry(
            date="4/13/2026",
            project="Commute",
            description="drive",
            combined="Commute: drive",
            start_time="2026-04-13T10:45:00.000Z",
            end_time="2026-04-13T11:45:39.074Z",
            hours=-1.0,
            notes="",
        )


def test_time_entry_hours_too_large() -> None:
    """Test that hours > 24 raises validation error."""
    with pytest.raises(ValidationError, match="Hours exceed 24"):
        TimeEntry(
            date="4/13/2026",
            project="Commute",
            description="drive",
            combined="Commute: drive",
            start_time="2026-04-13T10:45:00.000Z",
            end_time="2026-04-13T11:45:39.074Z",
            hours=25.0,
            notes="",
        )


def test_time_entry_empty_project() -> None:
    """Test that empty project name raises validation error."""
    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        TimeEntry(
            date="4/13/2026",
            project="",
            description="drive",
            combined="Commute: drive",
            start_time="2026-04-13T10:45:00.000Z",
            end_time="2026-04-13T11:45:39.074Z",
            hours=1.0,
            notes="",
        )


def test_time_entry_invalid_datetime() -> None:
    """Test that invalid datetime string raises validation error."""
    with pytest.raises(ValidationError, match="Invalid datetime"):
        TimeEntry(
            date="4/13/2026",
            project="Commute",
            description="drive",
            combined="Commute: drive",
            start_time="not-a-datetime",
            end_time="2026-04-13T11:45:39.074Z",
            hours=1.0,
            notes="",
        )


# TimeCop Tests


def test_timecop_read_csv_string() -> None:
    """Test reading CSV string into TimeCop."""
    cop = TimeCop()
    entries = cop.read_csv_string(SAMPLE_CSV)
    assert len(entries) == 12  # 12 data rows
    assert all(isinstance(e, TimeEntry) for e in entries)
    assert entries[0].project == "StellarCartography"
    assert entries[0].hours == 2.5


def test_timecop_read_csv_string_empty_notes_default() -> None:
    """Test that empty notes fields load as empty strings."""
    cop = TimeCop()
    entries = cop.read_csv_string(SAMPLE_CSV)
    assert entries[0].notes == ""


def test_timecop_total_hours() -> None:
    """Test total hours calculation."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    total = cop.total_hours()
    # Sum of all hours from sample data: 24.25
    assert abs(total - 24.25) < 0.001


def test_timecop_total_hours_by_project() -> None:
    """Test total hours grouped by project."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    by_project = cop.total_hours_by_project()
    assert "StellarCartography" in by_project
    assert "WarpDrive" in by_project
    assert by_project["StellarCartography"] > 0
    assert by_project["WarpDrive"] > 0


def test_timecop_entries_by_project() -> None:
    """Test filtering entries by project."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    cartography_entries = cop.entries_by_project("StellarCartography")
    hydroponics_entries = cop.entries_by_project("Hydroponics")
    assert len(cartography_entries) == 4
    assert len(hydroponics_entries) == 3
    assert all(e.project == "StellarCartography" for e in cartography_entries)
    assert all(e.project == "Hydroponics" for e in hydroponics_entries)


def test_timecop_entries_by_project_nonexistent() -> None:
    """Test filtering by a project that doesn't exist."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    entries = cop.entries_by_project("Nonexistent")
    assert entries == []


def test_timecop_entries_by_date() -> None:
    """Test filtering entries by date."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    entries = cop.entries_by_date("1/15/2200")
    assert len(entries) == 3
    assert all(e.date == "1/15/2200" for e in entries)


def test_timecop_entries_by_date_nonexistent() -> None:
    """Test filtering by a date that doesn't exist."""
    cop = TimeCop()
    cop.read_csv_string(SAMPLE_CSV)
    entries = cop.entries_by_date("1/1/2000")
    assert entries == []


def test_timecop_empty_csv(caplog: pytest.LogCaptureFixture) -> None:
    """Test reading CSV with only headers returns empty list."""
    caplog.set_level(logging.INFO)
    cop = TimeCop()
    header_only_csv = (
        "Date,Project,Description,Combined Project & Description,"
        "Start Time,End Time,Time (hours),Notes\n"
    )
    entries = cop.read_csv_string(header_only_csv)
    assert entries == []
    assert "Loaded 0 time entries" in caplog.records[0].message


def test_timecop_read_csv_file(tmp_path: Path) -> None:
    """Test reading CSV from a file path."""
    csv_path = tmp_path / "test_entries.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    cop = TimeCop()
    entries = cop.read_csv(str(csv_path))
    assert len(entries) == 12  # 12 data rows


def test_timecop_read_csv_file_not_found() -> None:
    """Test reading CSV from a non-existent file raises FileNotFoundError."""
    cop = TimeCop()
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        cop.read_csv("/nonexistent/path.csv")


def test_timecop_read_csv_with_bom() -> None:
    """Test reading CSV with BOM (byte order mark) strips it."""
    cop = TimeCop()
    bom_csv = "\ufeff" + SAMPLE_CSV
    # When CSV has BOM, DictReader includes it in the first column name
    # Strip BOM from the data before parsing
    entries = cop.read_csv_string(bom_csv)
    assert len(entries) >= 1


def test_timecop_invalid_csv_raises_error() -> None:
    """Test that invalid CSV data raises an error."""
    cop = TimeCop()
    invalid_csv = "col1,col2\nval1\n"
    # Row with fewer fields than headers will result in dict with None values
    # Pydantic will reject None for required fields
    with pytest.raises(ValidationError):
        cop.read_csv_string(invalid_csv)
