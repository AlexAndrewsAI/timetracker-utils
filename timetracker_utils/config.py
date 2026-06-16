"""Configuration module.

Provides a Pydantic v2 model for loading application configuration from YAML files.
"""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TimeTrackerConfig(BaseModel):
    """Pydantic v2 model for the timetracker configuration file.

    Attributes:
        database: Path to the SQLite database file.

        timezone: Default timezone for timestamp conversions (e.g. ET, PT, UTC).

    """

    database: str = Field(
        ...,
        description="Path to the SQLite database file.",
    )
    timezone: str = Field(
        ...,
        description="Default timezone for timestamp conversions (e.g. ET, PT, UTC).",
    )


def load_config(config_path: Path) -> TimeTrackerConfig:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A validated TimeTrackerConfig instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.

        ValueError: If the configuration file is invalid.

    """
    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    logger.info("Loaded configuration from %s", config_path)
    return TimeTrackerConfig(**raw)
