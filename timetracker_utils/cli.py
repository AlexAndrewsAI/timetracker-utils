"""Command line interface module.

Provides a typer-based CLI for the package. Currently a dummy entrypoint
that references the TimeCop class.
"""

import logging
from pathlib import Path

import typer

from timetracker_utils import __version__
from timetracker_utils.time_cop import TimeCop

app = typer.Typer(help="Time tracker utilities CLI")

logger = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    """Handle the version flag callback."""
    if value:
        typer.echo(f"timetracker-utils version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Time tracker utilities CLI."""
    # Reference TimeCop to ensure the class is importable
    _ = TimeCop


@app.command()
def timecop(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Path to the CSV file to load.",
    ),
    head: int = typer.Option(
        100,
        "--head",
        "-h",
        help="Number of rows to display from the top of the DataFrame.",
    ),
) -> None:
    """Load a CSV time tracking file and display the DataFrame."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cop = TimeCop()
    cop.read_csv(input)
    typer.echo(f"Loaded DataFrame ({len(cop.entries)} rows total):")
    typer.echo(cop.entries.head(head).to_string())


if __name__ == "__main__":
    app()
