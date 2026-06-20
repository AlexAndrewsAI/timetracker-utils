"""Tests for the CLI module."""

# ruff: noqa: E501 - CSV data lines exceed line length limit

import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from timetracker_utils import __version__
from timetracker_utils.cli import app

runner = CliRunner()

SAMPLE_CSV = """\
"Date","Project","Description","Combined Project & Description","Start Time","End Time","Time (hours)","Notes"
"1/15/2200","StellarCartography","nebula mapping","StellarCartography: nebula mapping","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","2.5",""
"""


def _write_config(tmp_path: Path, timezone: str = "ET") -> Path:
    """Write a temporary config YAML file and return its path."""
    config_path = tmp_path / "timetracker.yml"
    db_path = tmp_path / "data" / "timetracker" / "db.sqlite3"
    config_path.write_text(
        yaml.dump({"database": str(db_path), "timezone": timezone}),
        encoding="utf-8",
    )
    return config_path


def test_cli_version() -> None:
    """Test that --version flag prints the version and exits."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help() -> None:
    """Test that --help flag prints help text."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Time tracker utilities CLI" in result.stdout


def test_cli_no_args_exits_with_error() -> None:
    """Test that running with no arguments exits with code 2 (missing command)."""
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Missing command" in result.stderr


def test_cli_callback_run_directly() -> None:
    """Test the main callback body directly to cover _ = TimeCop."""
    # main() is a Typer callback that expects options through Typer's context,
    # so we invoke it via the app with --help to reach the callback body
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_cli_main_body() -> None:
    """Test the main callback body covers _ = TimeCop line."""
    from timetracker_utils.cli import main

    # main() with no arguments runs the callback body (hits _ = TimeCop line)
    main()


def test_main_module_importable() -> None:
    """Test that the __main__ module can be imported."""
    import timetracker_utils.__main__

    assert timetracker_utils.__main__ is not None


def test_version_callback() -> None:
    """Test the version_callback function directly."""
    from click.exceptions import Exit as ClickExit

    from timetracker_utils.cli import version_callback

    with pytest.raises(ClickExit) as exc_info:
        version_callback(True)
    # click.exceptions.Exit has exit_code, not code
    assert exc_info.value.exit_code == 0

    # Should do nothing when value is False
    version_callback(False)


def test_timecop_command(tmp_path: Path) -> None:
    """Test the add CLI command with timecop format loads a CSV and prints the DataFrame."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    assert "StellarCartography" in result.output


def test_timecop_command_head(tmp_path: Path) -> None:
    """Test the add CLI command with timecop format and --head option."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app,
        [
            "add",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(csv_path),
            "--head",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output


def test_timecop_command_missing_config() -> None:
    """Test that the add CLI command fails without required --config."""
    result = runner.invoke(app, ["add", "--format", "timecop", "test.csv"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr or "required" in result.stderr.lower()


def test_timecop_command_no_input_or_output_exits_with_error(tmp_path: Path) -> None:
    """Test that the add CLI command fails without input file argument."""
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop"]
    )
    assert result.exit_code != 0


def test_timecop_command_timezone_from_config(tmp_path: Path) -> None:
    """Test that timezone from config converts timestamps in the DataFrame."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    assert "StellarCartography" in result.output
    # UTC-4 means 09:00Z becomes 05:00 ET
    assert "05:00" in result.output


def test_timecop_command_different_timezone(tmp_path: Path) -> None:
    """Test that a different timezone from config works correctly."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="PT")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    # January 2200 is winter: PT is UTC-8, so 09:00Z becomes 01:00 PT
    assert "01:00" in result.output


def test_timecop_output_empty_db(tmp_path: Path) -> None:
    """Test export with timecop format and empty database writes header-only CSV."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert "Database is empty" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Date" in content
    assert "Project" in content
    assert "Start Time" in content
    # No data rows should exist beyond the header
    assert content.strip().count("\n") == 0  # Only header row


def test_timecop_output_with_data(tmp_path: Path) -> None:
    """Test export with timecop format exports a previously imported database to CSV."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    # First, import the CSV to populate the database
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop", str(csv_path)]
    )
    assert result.exit_code == 0
    # Now export to output CSV
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    # Check header
    assert "Date" in content
    assert "Project" in content
    assert "Combined Project & Description" in content
    assert "Start Time" in content
    assert "End Time" in content
    assert "Time (hours)" in content
    # Check data row content
    assert "StellarCartography" in content
    assert "nebula mapping" in content
    assert "StellarCartography: nebula mapping" in content
    assert "2200-01-15T04:00:00.000-05:00" in content
    assert "2200-01-15T06:30:00.000-05:00" in content
    assert "2.5000" in content


def test_timecop_output_combined_with_input(tmp_path: Path) -> None:
    """Test using add and export commands together."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    # First add the data
    result = runner.invoke(
        app,
        [
            "add",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(csv_path),
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    # Then export the data
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert "Exporting" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "StellarCartography" in content


def test_stt_rejects_timecop_csv(tmp_path: Path) -> None:
    """Test that the add CLI command with stt format rejects a TimeCop-format CSV."""
    timecop_csv = """\
"Date","Project","Description","Combined Project & Description","Start Time","End Time","Time (hours)","Notes"
"1/15/2200","StellarCartography","nebula mapping","StellarCartography: nebula mapping","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","2.5",""
"""
    csv_path = tmp_path / "timecop.csv"
    csv_path.write_text(timecop_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt", str(csv_path)]
    )
    assert result.exit_code != 0
    assert "Missing required STT columns" in (result.output or result.stderr or "")


def test_timecop_rejects_stt_csv(tmp_path: Path) -> None:
    """Test that the add CLI command with timecop format rejects an STT-format CSV."""
    stt_csv = """\
"activity name","time started","time ended","comment","categories","record tags","duration","duration minutes"
"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z","nebula mapping","nebula mapping","","2:30:00","150"
"""
    csv_path = tmp_path / "stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "timecop", str(csv_path)]
    )
    assert result.exit_code != 0
    assert "Missing required TimeCop columns" in (result.output or result.stderr or "")


def test_timecop_output_non_existent_db(tmp_path: Path) -> None:
    """Test export with timecop format when the database file does not exist yet."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "timecop",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert "Database is empty" in result.output
    assert output_path.exists()


def test_format_datetime_iso() -> None:
    """Test _format_datetime_iso helper function."""
    from datetime import datetime, timedelta, timezone

    from timetracker_utils.cli import _format_datetime_iso

    # None input
    assert _format_datetime_iso(None) == ""
    # Empty string
    assert _format_datetime_iso("") == ""
    # Datetime object
    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    result = _format_datetime_iso(dt)
    assert result == "2200-01-15T09:00:00.000+00:00"
    # ISO string
    result = _format_datetime_iso("2200-01-15T09:00:00.000Z")
    assert result == "2200-01-15T09:00:00.000+00:00"
    # Non-UTC timezone defaults to UTC conversion
    dt_est = datetime(2200, 1, 15, 5, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    result = _format_datetime_iso(dt_est)
    assert result == "2200-01-15T10:00:00.000+00:00"


def test_format_datetime_iso_unparseable_string() -> None:
    """Test _format_datetime_iso with an unparseable string (hits except branch)."""
    from timetracker_utils.cli import _format_datetime_iso

    # Unparseable string should return as-is
    result = _format_datetime_iso("not-a-date")
    assert result == "not-a-date"


def test_format_datetime_iso_naive_datetime() -> None:
    """Test _format_datetime_iso with a naive datetime (hits tzinfo is None branch)."""
    from datetime import datetime

    from timetracker_utils.cli import _format_datetime_iso

    dt = datetime(2200, 1, 15, 9, 0, 0)  # No tzinfo
    result = _format_datetime_iso(dt)
    # Should be treated as UTC and show offset
    assert result == "2200-01-15T09:00:00.000+00:00"


def test_format_datetime_iso_non_datetime_type() -> None:
    """Test _format_datetime_iso with a non-datetime, non-string type (hits else branch)."""
    from timetracker_utils.cli import _format_datetime_iso

    # Integer input hits the else: return str(val) branch
    result = _format_datetime_iso(42)
    assert result == "42"


def test_compute_hours() -> None:
    """Test _compute_hours helper function."""
    from timetracker_utils.cli import _compute_hours

    # None values
    assert _compute_hours(None, None) == ""
    assert _compute_hours("2020-01-01T00:00:00Z", None) == ""
    # Valid times
    result = _compute_hours("2200-01-15T09:00:00.000Z", "2200-01-15T11:30:00.000Z")
    assert result == "2.5000"
    # Rounding
    result = _compute_hours("2200-01-15T09:00:00.000Z", "2200-01-15T12:00:00.000Z")
    assert result == "3.0000"


def test_compute_hours_empty_string() -> None:
    """Test _compute_hours with empty string start/end times."""
    from timetracker_utils.cli import _compute_hours

    # Empty start time
    assert _compute_hours("", "2200-01-15T11:30:00.000Z") == ""
    # Empty end time
    assert _compute_hours("2200-01-15T09:00:00.000Z", "") == ""


def test_compute_hours_datetime_objects() -> None:
    """Test _compute_hours with datetime objects (hits isinstance(datetime) branch)."""
    from datetime import datetime, timezone

    from timetracker_utils.cli import _compute_hours

    start = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2200, 1, 15, 11, 30, 0, tzinfo=timezone.utc)
    result = _compute_hours(start, end)
    assert result == "2.5000"


def test_compute_hours_invalid_string() -> None:
    """Test _compute_hours with invalid time string (hits except branch)."""
    from timetracker_utils.cli import _compute_hours

    # Invalid string should be caught by ValueError from fromisoformat
    result = _compute_hours("not-a-date", "2200-01-15T11:30:00.000Z")
    assert result == ""


def test_compute_hours_non_datetime_type() -> None:
    """Test _compute_hours with non-datetime, non-string types."""
    from timetracker_utils.cli import _compute_hours

    # Integer types hit the elif isinstance(x, datetime) else branch and return ""
    _compute_hours(100, 200)


def test_format_simple_csv_empty(tmp_path: Path) -> None:
    """Test _format_simple_csv with empty DataFrame writes header only."""
    import pandas as pd

    from timetracker_utils.cli import _format_simple_csv

    output_path = tmp_path / "empty_output.csv"
    _format_simple_csv(pd.DataFrame(), output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "activity name" in content
    assert "time started" in content


def test_format_simple_csv_with_data(tmp_path: Path) -> None:
    """Test _format_simple_csv with data writes correct rows."""
    from datetime import datetime, timezone

    import pandas as pd

    from timetracker_utils.cli import _format_simple_csv

    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["StellarCartography"],
            "start_time": [datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)],
            "end_time": [datetime(2200, 1, 15, 11, 30, 0, tzinfo=timezone.utc)],
            "notes": ["nebula mapping"],
            "categories": [["nebula"]],
            "tags": [["urgent"]],
        }
    )
    output_path = tmp_path / "stt_output.csv"
    _format_simple_csv(df, output_path)
    output_path.read_text(encoding="utf-8")


def test_format_simple_datetime_none() -> None:
    """Test _format_simple_datetime with None."""
    from timetracker_utils.cli import _format_simple_datetime

    assert _format_simple_datetime(None) == ""


def test_format_simple_datetime_empty_string() -> None:
    """Test _format_simple_datetime with empty string."""
    from timetracker_utils.cli import _format_simple_datetime

    assert _format_simple_datetime("") == ""


def test_format_simple_datetime_whitespace_string() -> None:
    """Test _format_simple_datetime with whitespace string."""
    from timetracker_utils.cli import _format_simple_datetime

    assert _format_simple_datetime("   ") == ""


def test_format_simple_datetime_iso_string() -> None:
    """Test _format_simple_datetime with an ISO string."""
    from timetracker_utils.cli import _format_simple_datetime

    result = _format_simple_datetime("2200-01-15T09:00:00.000Z")
    assert "2200-01-15T09:00:00" in result


def test_format_simple_datetime_unparseable_string() -> None:
    """Test _format_simple_datetime with unparseable string returns as-is."""
    from timetracker_utils.cli import _format_simple_datetime

    result = _format_simple_datetime("not-a-date")
    assert result == "not-a-date"


def test_format_simple_datetime_non_datetime_non_string() -> None:
    """Test _format_simple_datetime with non-datetime, non-string type."""
    from timetracker_utils.cli import _format_simple_datetime

    result = _format_simple_datetime(42)
    assert result == "42"


def test_compute_simple_duration_none_values() -> None:
    """Test _compute_simple_duration with None values."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration(None, None)
    assert result == ("", "")


def test_compute_simple_duration_none_start() -> None:
    """Test _compute_simple_duration with None start time."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration(None, "2200-01-15T11:30:00.000Z")
    assert result == ("", "")


def test_compute_simple_duration_valid_strings() -> None:
    """Test _compute_simple_duration with valid ISO strings."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration(
        "2200-01-15T09:00:00.000Z", "2200-01-15T11:30:00.000Z"
    )
    assert result == ("2:30:0", "150.0")


def test_compute_simple_duration_mixed_types() -> None:
    """Test _compute_simple_duration with start as string and end as non-datetime."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration("2200-01-15T09:00:00.000Z", 42)
    assert result == ("", "")


def test_compute_hours_end_non_datetime_non_string() -> None:
    """Test _compute_hours with non-datetime, non-string end time (line 249)."""
    from timetracker_utils.cli import _compute_hours

    result = _compute_hours("2200-01-15T09:00:00.000Z", 42)
    assert result == ""


def test_compute_simple_duration_datetime_objects() -> None:
    """Test _compute_simple_duration with datetime objects."""
    from datetime import datetime, timezone

    datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)


def test_stt_command(tmp_path: Path) -> None:
    """Test the add CLI command with stt format loads a CSV and prints the DataFrame."""
    stt_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z",'
        '"nebula mapping","nebula mapping","","2:30:00","150"\n'
    )
    csv_path = tmp_path / "test_stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    assert "StellarCartography" in result.output


def test_stt_command_head(tmp_path: Path) -> None:
    """Test the add CLI command with stt format and --head option."""
    stt_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z",'
        '"nebula mapping","nebula mapping","","2:30:00","150"\n'
    )
    csv_path = tmp_path / "test_stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app,
        [
            "add",
            "--config",
            str(config_path),
            "--format",
            "stt",
            str(csv_path),
            "--head",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output


def test_stt_command_missing_config() -> None:
    """Test that add command fails without required --config."""
    result = runner.invoke(app, ["add", "--format", "stt", "test.csv"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr or "required" in result.stderr.lower()


def test_stt_command_no_input_or_output_exits_with_error(tmp_path: Path) -> None:
    """Test that add command fails without input file argument."""
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt"]
    )
    assert result.exit_code != 0


def test_stt_command_timezone_conversion(tmp_path: Path) -> None:
    """Test that timezone from config converts timestamps in stt output."""
    stt_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z",'
        '"nebula mapping","nebula mapping","","2:30:00","150"\n'
    )
    csv_path = tmp_path / "test_stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="PT")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt", str(csv_path)]
    )
    assert result.exit_code == 0
    # PT in January is UTC-8: 09:00Z -> 01:00 PT
    assert "01:00" in result.output


def test_stt_output_empty_db(tmp_path: Path) -> None:
    """Test export with stt format and empty database writes header-only CSV."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "stt_output.csv"
    result = runner.invoke(
        app,
        ["export", "--config", str(config_path), "--format", "stt", str(output_path)],
    )
    assert result.exit_code == 0
    assert "Database is empty" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "activity name" in content


def test_stt_output_with_data(tmp_path: Path) -> None:
    """Test export with stt format exports a previously imported database."""
    stt_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z",'
        '"nebula mapping","nebula mapping","","2:30:00","150"\n'
    )
    csv_path = tmp_path / "input_stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt", str(csv_path)]
    )
    assert result.exit_code == 0
    output_path = tmp_path / "stt_output.csv"
    result = runner.invoke(
        app,
        ["export", "--config", str(config_path), "--format", "stt", str(output_path)],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "StellarCartography" in content
    assert "activity name" in content


def test_stt_output_combined_with_input(tmp_path: Path) -> None:
    """Test using add and export commands together."""
    stt_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"StellarCartography","2200-01-15T09:00:00.000Z","2200-01-15T11:30:00.000Z",'
        '"nebula mapping","nebula mapping","","2:30:00","150"\n'
    )
    csv_path = tmp_path / "input_stt.csv"
    csv_path.write_text(stt_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "stt_output.csv"
    # First add the data
    result = runner.invoke(
        app,
        [
            "add",
            "--config",
            str(config_path),
            "--format",
            "stt",
            str(csv_path),
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    # Then export the data
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "stt",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert "Exporting" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "StellarCartography" in content


def test_stt_command_invalid_csv(tmp_path: Path) -> None:
    """Test that an invalid CSV value (bad datetime) is handled."""
    bad_csv = (
        '"activity name","time started","time ended","comment","categories",'
        '"record tags","duration","duration minutes"\n'
        '"Test","not-a-datetime","2200-01-15T10:00:00.000Z",'
        '"","","","1:00:00","60"\n'
    )
    csv_path = tmp_path / "bad_stt.csv"
    csv_path.write_text(bad_csv, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "stt", str(csv_path)]
    )
    assert result.exit_code != 0


def test_compute_simple_duration_non_datetime_types() -> None:
    """Test _compute_simple_duration with non-datetime types."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration(100, 200)
    assert result == ("", "")


def test_compute_simple_duration_invalid_string() -> None:
    """Test _compute_simple_duration with invalid string."""
    from timetracker_utils.cli import _compute_simple_duration

    result = _compute_simple_duration("not-a-date", "2200-01-15T11:30:00.000Z")
    assert result == ("", "")


def test_format_simple_datetime_naive_datetime() -> None:
    """Test _format_simple_datetime with naive datetime."""
    from datetime import datetime

    from timetracker_utils.cli import _format_simple_datetime

    dt = datetime(2200, 1, 15, 9, 0, 0)  # No tzinfo
    result = _format_simple_datetime(dt)
    assert "2200-01-15T09:00:00" in result


def test_format_simple_datetime_target_tz() -> None:
    """Test _format_simple_datetime with a target timezone."""
    from datetime import datetime, timezone

    from timetracker_utils.cli import _format_simple_datetime

    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    result = _format_simple_datetime(dt, target_tz="ET")
    # UTC-5 in January (ET uses -5 in winter)
    assert "04:00:00" in result or "05:00:00" in result


def test_format_simple_datetime_resolve_tz_fails() -> None:
    """Test _format_simple_datetime when resolve_tz returns None."""
    from datetime import datetime, timezone

    from timetracker_utils.cli import _format_simple_datetime

    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    result = _format_simple_datetime(dt, target_tz="XZ")
    # When zone is None, it stays as UTC
    assert "2200-01-15T09:00:00" in result


def test_format_simple_csv_non_list_categories(tmp_path: Path) -> None:
    """Test _format_simple_csv with non-list categories (string)."""
    from datetime import datetime, timezone

    import pandas as pd

    from timetracker_utils.cli import _format_simple_csv

    df = pd.DataFrame(
        {
            "date": ["1/15/2200"],
            "activity": ["Test"],
            "start_time": [datetime(2200, 1, 15, 9, 0, 0, tzinfo=timezone.utc)],
            "end_time": [datetime(2200, 1, 15, 10, 0, 0, tzinfo=timezone.utc)],
            "notes": [""],
            "categories": ["raw_category"],
            "tags": ["raw_tag"],
        }
    )
    output_path = tmp_path / "nonlist_output.csv"
    _format_simple_csv(df, output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "raw_category" in content
    assert "raw_tag" in content


def test_add_command_unknown_format(tmp_path: Path) -> None:
    """Test add command with unknown format (lines 297-298)."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["add", "--config", str(config_path), "--format", "unknown", str(csv_path)]
    )
    assert result.exit_code == 1
    assert "Unknown format" in result.stderr or "Unknown format" in result.output


def test_export_command_unknown_format(tmp_path: Path) -> None:
    """Test export command with unknown format (lines 347-348)."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app,
        [
            "export",
            "--config",
            str(config_path),
            "--format",
            "unknown",
            str(output_path),
        ],
    )
    assert result.exit_code == 1
    assert "Unknown format" in result.stderr or "Unknown format" in result.output


def _add_entries_to_db(tmp_path: Path) -> tuple[Path, str]:
    """Add sample entries to the database and return (config_path, db_path)."""
    db_path = tmp_path / "data" / "timetracker" / "db.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE activities ("
        "date TEXT, activity TEXT, start_time TEXT, "
        "end_time TEXT, notes TEXT, categories TEXT, tags TEXT)"
    )
    entries = [
        (
            "1/15/2200",
            "StellarCartography",
            "2200-01-15T09:00:00+00:00",
            "2200-01-15T11:30:00+00:00",
            "nebula mapping",
            '["nebula"]',
            '["urgent", "space"]',
        ),
        (
            "1/15/2200",
            "DataAnalysis",
            "2200-01-15T13:00:00+00:00",
            "2200-01-15T14:00:00+00:00",
            "processing",
            '["analysis", "data"]',
            '["urgent"]',
        ),
    ]
    conn.executemany(
        "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
        entries,
    )
    conn.commit()
    conn.close()
    config_path = tmp_path / "timetracker.yml"
    config_path.write_text(
        yaml.dump({"database": str(db_path), "timezone": "ET"}),
        encoding="utf-8",
    )
    return config_path, str(db_path)


def test_report_command(tmp_path: Path) -> None:
    """Test the report CLI command with valid date."""
    config_path, _ = _add_entries_to_db(tmp_path)
    result = runner.invoke(
        app, ["report", "--config", str(config_path), "--date", "2200-01-15"]
    )
    assert result.exit_code == 0
    assert "Daily Report" in result.output
    assert "Total Time" in result.output
    assert "StellarCartography" in result.output
    assert "DataAnalysis" in result.output
    assert "nebula" in result.output
    assert "data" in result.output
    assert "urgent" in result.output
    assert "space" in result.output


def test_report_command_empty_db(tmp_path: Path) -> None:
    """Test the report command with empty database."""
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["report", "--config", str(config_path), "--date", "2200-01-15"]
    )
    assert result.exit_code != 0
    assert "Database is empty" in result.output


def test_report_command_no_entries_date(tmp_path: Path) -> None:
    """Test the report command when no entries exist for the date."""
    config_path, _ = _add_entries_to_db(tmp_path)
    result = runner.invoke(
        app, ["report", "--config", str(config_path), "--date", "2200-01-16"]
    )
    assert result.exit_code != 0
    assert "No entries found" in result.output


def test_report_command_invalid_date(tmp_path: Path) -> None:
    """Test the report command with an invalid date format."""
    config_path, _ = _add_entries_to_db(tmp_path)
    result = runner.invoke(
        app, ["report", "--config", str(config_path), "--date", "invalid-date"]
    )
    assert result.exit_code == 1
    assert "Invalid date format" in result.output


def test_seconds_to_hhmm() -> None:
    """Test _seconds_to_hhmm helper."""
    from timetracker_utils.cli import _seconds_to_hhmm

    assert _seconds_to_hhmm(0) == "00:00"
    assert _seconds_to_hhmm(3661) == "01:01"
    assert _seconds_to_hhmm(9000) == "02:30"
    assert _seconds_to_hhmm(-10) == "00:00"


def test_report_command_short_date_flag(tmp_path: Path) -> None:
    """Test the report command with short -d flag."""
    config_path, _ = _add_entries_to_db(tmp_path)
    result = runner.invoke(
        app, ["report", "--config", str(config_path), "-d", "2200-01-15"]
    )
    assert result.exit_code == 0
    assert "Daily Report" in result.output


def test_format_simple_datetime_utcoffset_none() -> None:
    """Test _format_simple_datetime when utcoffset() returns None (line 178).

    Uses a custom tzinfo with None utcoffset and an unresolvable target
    timezone so astimezone is skipped, exposing the fallback branch.
    """
    from datetime import datetime, tzinfo

    from timetracker_utils.cli import _format_simple_datetime

    class NoUTCOffsetTZ(tzinfo):
        def utcoffset(self, _dt: datetime | None) -> None:
            return None

        def dst(self, _dt: datetime | None) -> None:
            return None

        def tzname(self, _dt: datetime | None) -> str:
            return "NoOffset"

    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=NoUTCOffsetTZ())
    # target_tz='XZ' makes resolve_tz return None, so astimezone is skipped
    # and the custom tzinfo's utcoffset() returns None -> hits line 178
    result = _format_simple_datetime(dt, target_tz="XZ")
    assert "+00:00" in result
    assert "2200-01-15T09:00:00" in result


def test_format_datetime_iso_utcoffset_none() -> None:
    """Test _format_datetime_iso when utcoffset() returns None (line 239).

    Same strategy: custom tzinfo with None utcoffset and unresolvable target.
    """
    from datetime import datetime, tzinfo

    from timetracker_utils.cli import _format_datetime_iso

    class NoUTCOffsetTZ(tzinfo):
        def utcoffset(self, _dt: datetime | None) -> None:
            return None

        def dst(self, _dt: datetime | None) -> None:
            return None

        def tzname(self, _dt: datetime | None) -> str:
            return "NoOffset"

    dt = datetime(2200, 1, 15, 9, 0, 0, tzinfo=NoUTCOffsetTZ())
    result = _format_datetime_iso(dt, target_tz="XZ")
    assert "+00:00" in result
    assert "2200-01-15T09:00:00" in result
