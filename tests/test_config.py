"""Tests for the configuration module."""

import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from timetracker_utils.config import TimeTrackerConfig, load_config


def test_load_config(tmp_path: Path) -> None:
    """Test loading a valid config YAML file."""
    config_path = tmp_path / "timetracker.yml"
    config_path.write_text(
        yaml.dump({"database": "~/data/timetracker/db.sqlite3", "timezone": "ET"}),
        encoding="utf-8",
    )
    config = load_config(config_path)
    expected = str(Path(os.path.expanduser("~/data/timetracker/db.sqlite3")))
    assert config.database == expected
    assert config.timezone == "ET"


def test_load_config_missing_file() -> None:
    """Test that load_config raises FileNotFoundError for a missing file."""
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(Path("/nonexistent/path/config.yml"))


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    """Test that load_config raises an error for invalid YAML."""
    config_path = tmp_path / "bad.yml"
    config_path.write_text("invalid: yaml: content: [", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_config(config_path)


def test_load_config_missing_fields(tmp_path: Path) -> None:
    """Test that load_config raises an error when required fields are missing."""
    config_path = tmp_path / "incomplete.yml"
    config_path.write_text(
        yaml.dump({"database": "~/data/db.sqlite3"}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_max_conflict_display_default() -> None:
    """Test that max_conflict_display defaults to 100."""
    config = TimeTrackerConfig(database="~/test.db", timezone="UTC")
    assert config.max_conflict_display == 100


def test_max_conflict_display_custom() -> None:
    """Test that max_conflict_display can be set to a custom value."""
    config = TimeTrackerConfig(
        database="~/test.db", timezone="UTC", max_conflict_display=50
    )
    assert config.max_conflict_display == 50


def test_max_conflict_display_zero() -> None:
    """Test that max_conflict_display can be set to 0."""
    config = TimeTrackerConfig(
        database="~/test.db", timezone="UTC", max_conflict_display=0
    )
    assert config.max_conflict_display == 0


def test_time_tracker_config_model() -> None:
    """Test the TimeTrackerConfig model directly."""
    config = TimeTrackerConfig(database="~/data/db.sqlite3", timezone="PT")
    expected = str(Path(os.path.expanduser("~/data/db.sqlite3")))
    assert config.database == expected
    assert config.timezone == "PT"
    assert config.max_conflict_display == 100  # default


def test_database_path_tilde_expansion() -> None:
    """Test that tilde in database path is expanded to the home directory."""
    config = TimeTrackerConfig(database="~/test.db", timezone="UTC")
    assert config.database == str(Path.home() / "test.db")


def test_database_path_absolute_not_expanded() -> None:
    """Test that an absolute path without tilde is kept as-is."""
    config = TimeTrackerConfig(database="/absolute/path/db.sqlite3", timezone="UTC")
    assert config.database == "/absolute/path/db.sqlite3"


def test_database_path_relative_not_expanded() -> None:
    """Test that a relative path without tilde is kept as-is."""
    config = TimeTrackerConfig(database="relative/path/db.sqlite3", timezone="UTC")
    assert config.database == "relative/path/db.sqlite3"
