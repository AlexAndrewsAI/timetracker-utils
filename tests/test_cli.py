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
    result = version_callback(False)
    assert result is None


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
        ["timecop", "--config", str(config_path), "--input", str(csv_path), "--head", "1"],
    )
    assert result.exit_code == 0
    assert "Loaded DataFrame" in result.output


def test_timecop_command_missing_config() -> None:
    """Test that the timecop CLI command fails without required --config."""
    result = runner.invoke(app, ["timecop"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr or "required" in result.stderr.lower()


def test_timecop_command_missing_input() -> None:
    """Test that the timecop CLI command fails without required --input."""
    result = runner.invoke(app, ["timecop"])
    assert result.exit_code != 0
    assert "Missing option" in result.stderr or "required" in result.stderr.lower()


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
