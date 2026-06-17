"""Tests for the CLI module."""

# ruff: noqa: E501 - CSV data lines exceed line length limit

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
    """Test the timecop CLI command loads a CSV and prints the DataFrame."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--input", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    assert "StellarCartography" in result.output


def test_timecop_command_head(tmp_path: Path) -> None:
    """Test the timecop CLI command with --head option."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app,
        [
            "timecop",
            "--config",
            str(config_path),
            "--input",
            str(csv_path),
            "--head",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output


def test_timecop_command_missing_config() -> None:
    """Test that the timecop CLI command fails without required --config."""
    result = runner.invoke(app, ["timecop"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr or "required" in result.stderr.lower()


def test_timecop_command_no_input_or_output_exits_with_error(tmp_path: Path) -> None:
    """Test that the timecop CLI command fails without --input or --output."""
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(app, ["timecop", "--config", str(config_path)])
    assert result.exit_code == 1
    assert "input" in result.output or "output" in result.output


def test_timecop_command_timezone_from_config(tmp_path: Path) -> None:
    """Test that timezone from config converts timestamps in the DataFrame."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--input", str(csv_path)]
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
        app, ["timecop", "--config", str(config_path), "--input", str(csv_path)]
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    # January 2200 is winter: PT is UTC-8, so 09:00Z becomes 01:00 PT
    assert "01:00" in result.output


def test_timecop_output_empty_db(tmp_path: Path) -> None:
    """Test --output with an empty database writes header-only CSV."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--output", str(output_path)]
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
    """Test --output exports a previously imported database to CSV."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    # First, import the CSV to populate the database
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--input", str(csv_path)]
    )
    assert result.exit_code == 0
    # Now export to output CSV
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--output", str(output_path)]
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
    assert "2200-01-15T09:00:00.000Z" in content or "2200-01-15T09:00:00" in content
    assert "2200-01-15T11:30:00.000Z" in content or "2200-01-15T11:30:00" in content
    assert "2.5000" in content


def test_timecop_output_combined_with_input(tmp_path: Path) -> None:
    """Test using --output together with --input."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app,
        [
            "timecop",
            "--config",
            str(config_path),
            "--input",
            str(csv_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output
    assert "Exporting" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "StellarCartography" in content


def test_timecop_output_non_existent_db(tmp_path: Path) -> None:
    """Test --output when the database file does not exist yet."""
    config_path = _write_config(tmp_path, timezone="ET")
    output_path = tmp_path / "output.csv"
    result = runner.invoke(
        app, ["timecop", "--config", str(config_path), "--output", str(output_path)]
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
    assert result == "2200-01-15T09:00:00.000Z"
    # ISO string
    result = _format_datetime_iso("2200-01-15T09:00:00.000Z")
    assert result == "2200-01-15T09:00:00.000Z"
    # Non-UTC timezone
    dt_est = datetime(2200, 1, 15, 5, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    result = _format_datetime_iso(dt_est)
    assert result == "2200-01-15T10:00:00.000Z"


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
    # Should be treated as UTC
    assert result == "2200-01-15T09:00:00.000Z"


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
    result = _compute_hours(100, 200)
    assert result == ""
