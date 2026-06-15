"""Command line interface module.

Provides a typer-based CLI for the package. Currently a dummy entrypoint
that references the TimeCop class.
"""

import typer

from timetracker_utils import __version__
from timetracker_utils.time_cop import TimeCop

app = typer.Typer(help="Time tracker utilities CLI")


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


if __name__ == "__main__":
    app()
