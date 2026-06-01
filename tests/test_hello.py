"""Tests for the hello module."""

import logging

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from python_package_template import Config, HelloWorld
from python_package_template.cli import app


def test_default_name(caplog: pytest.LogCaptureFixture) -> None:
    """Test HelloWorld with default name.

    Args:
        caplog: Pytest fixture for capturing log output.

    """
    caplog.set_level(logging.INFO)
    hello_world = HelloWorld()
    greeting = hello_world.greet()
    assert greeting == "Hello, World!"
    assert len(caplog.records) == 1
    assert caplog.records[0].message == "hello World"
    assert caplog.records[0].levelname == "INFO"


def test_custom_name(caplog: pytest.LogCaptureFixture) -> None:
    """Test HelloWorld with custom name.

    Args:
        caplog: Pytest fixture for capturing log output.

    """
    caplog.set_level(logging.INFO)
    hello_world = HelloWorld(Config(name="Alice"))
    greeting = hello_world.greet()
    assert greeting == "Hello, Alice!"
    assert len(caplog.records) == 1
    assert caplog.records[0].message == "hello Alice"
    assert caplog.records[0].levelname == "INFO"


def test_empty_name_validation() -> None:
    """Test that Config validates against empty names."""
    with pytest.raises(ValidationError, match="at least 1 character"):
        Config(name="")


def test_config_frozen_immutability() -> None:
    """Test that Config is frozen and cannot be modified after creation."""
    config = Config(name="Alice")
    with pytest.raises(ValidationError, match="Instance is frozen"):
        config.name = "Bob"


def test_config_invalid_type() -> None:
    """Test that Config validates against invalid types."""
    with pytest.raises(ValidationError, match="Input should be a valid string"):
        Config(name=123)  # type: ignore[arg-type]


# CLI Tests
runner = CliRunner()


def test_cli_hello_default() -> None:
    """Test CLI hello command with default name."""
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_cli_hello_custom_name() -> None:
    """Test CLI hello command with custom name."""
    result = runner.invoke(app, ["hello", "--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output


def test_cli_hello_short_option() -> None:
    """Test CLI hello command with short option."""
    result = runner.invoke(app, ["hello", "-n", "Bob"])
    assert result.exit_code == 0
    assert "Hello, Bob!" in result.output


def test_cli_version() -> None:
    """Test CLI --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "python-package-template version:" in result.output


def test_cli_version_short() -> None:
    """Test CLI -V short flag."""
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert "python-package-template version:" in result.output


def test_cli_hello_empty_name() -> None:
    """Test CLI hello command with empty string name raises validation error."""
    result = runner.invoke(app, ["hello", "--name", ""])
    assert result.exit_code != 0


def test_main_entry_point() -> None:
    """Test that __main__.py can be imported and provides the app."""
    from python_package_template import __main__

    assert hasattr(__main__, "app")
