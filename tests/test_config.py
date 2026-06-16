"""Tests for the configuration module."""

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
    assert config.database == "~/data/timetracker/db.sqlite3"
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


def test_time_tracker_config_model() -> None:
    """Test the TimeTrackerConfig model directly."""
    config = TimeTrackerConfig(database="~/data/db.sqlite3", timezone="PT")
    assert config.database == "~/data/db.sqlite3"
    assert config.timezone == "PT"
