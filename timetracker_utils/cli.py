"""Command line interface module.

Provides a typer-based CLI for the package.
"""

import logging
from datetime import date as date_type
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from timetracker_utils import __version__
from timetracker_utils.config import load_config
from timetracker_utils.csv_formatters import (
    _format_simple_csv,
    _format_timecop_csv,
    _seconds_to_hhmm,
)
from timetracker_utils.database import Database
from timetracker_utils.datetime_utils import aggregate_by_date, convert_column_tz
from timetracker_utils.report import (
    _REPORT_TYPES,
    _parse_date_arg,
    _print_breakdown,
    _print_daily_report,
    _show_bar_range,
    _show_bar_single,
)
from timetracker_utils.simple_time_tracker import SimpleTimeTracker
from timetracker_utils.time_cop import TimeCop

app = typer.Typer(help="Time tracker utilities CLI")

logger = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    """Print version and exit when --version flag is passed."""
    if value:
        typer.echo(f"timetracker-utils version: {__version__}")
        raise typer.Exit()
    return None


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
    _ = TimeCop
    _ = SimpleTimeTracker


@app.command()
def add(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to the YAML configuration file."
    ),
    format: str = typer.Option(
        ..., "--format", "-f", help="Format of the input file (timecop or stt)."
    ),
    input_file: Path = typer.Argument(..., help="Path to the CSV file to load."),
    head: int = typer.Option(100, "--head", "-h", help="Rows to display."),
) -> None:
    """Load CSV data into the database."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config)

    if format == "timecop":
        try:
            cop = TimeCop(default_timezone=cfg.timezone)
            cop.read_csv(input_file)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        db = Database()
        db.write(
            cop.entries, cfg.database, max_conflict_display=cfg.max_conflict_display
        )
        typer.echo(f"Loaded DataFrame ({len(cop.entries)} rows total):")
        display_df = cop.entries.copy()
    elif format == "stt":
        try:
            tracker = SimpleTimeTracker(default_timezone=cfg.timezone)
            tracker.read_csv(input_file)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        db = Database()
        db.write(
            tracker.entries, cfg.database, max_conflict_display=cfg.max_conflict_display
        )
        typer.echo(f"Loaded DataFrame ({len(tracker.entries)} rows total):")
        display_df = tracker.entries.copy()
    else:
        typer.echo(f"Unknown format: {format}. Use 'timecop' or 'stt'.", err=True)
        raise typer.Exit(code=1)

    if not display_df.empty:
        if "start_time" in display_df.columns:
            display_df["start_time"] = convert_column_tz(
                display_df["start_time"], cfg.timezone
            )
        if "end_time" in display_df.columns:
            display_df["end_time"] = convert_column_tz(
                display_df["end_time"], cfg.timezone
            )
    with pd.option_context(
        "display.max_columns",
        None,
        "display.max_colwidth",
        None,
        "display.width",
        None,
    ):
        typer.echo(str(display_df.head(head)))


@app.command()
def export(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to the YAML configuration file."
    ),
    format: str = typer.Option(
        ..., "--format", "-f", help="Format of the output file (timecop or stt)."
    ),
    output_file: Path = typer.Argument(..., help="Path to export database as CSV."),
) -> None:
    """Export database data to CSV."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config)

    db = Database()
    db_entries = db.read(cfg.database)

    if db_entries.empty:
        typer.echo("Database is empty, writing header-only CSV.")
    else:
        typer.echo(f"Exporting {len(db_entries)} entries to {output_file}")

    if format == "timecop":
        _format_timecop_csv(db_entries, output_file, cfg.timezone)
    elif format == "stt":
        _format_simple_csv(db_entries, output_file, cfg.timezone)
    else:
        typer.echo(f"Unknown format: {format}. Use 'timecop' or 'stt'.", err=True)
        raise typer.Exit(code=1)


@app.command()
def report(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to the YAML configuration file."
    ),
    date: str = typer.Option(
        ...,
        "--date",
        "-d",
        help="Date or date range to report on (yyyy-mm-dd or yyyy-mm-dd:yyyy-mm-dd).",
    ),
    report_type: str = typer.Option(
        "text",
        "--type",
        "-t",
        help=(
            "Report output type: 'text' (tables, default) "
            "or 'bar' (interactive bar charts)."
        ),
    ),
) -> None:
    """Show a daily report of activities, tags, and categories.

    Aggregates total time and displays breakdowns for the specified date
    or date range. Use --type bar for interactive matplotlib bar charts.
    """
    if report_type not in _REPORT_TYPES:
        typer.echo(
            f"Invalid report type: {report_type!r}. Choose from {_REPORT_TYPES}.",
            err=True,
        )
        raise typer.Exit(code=1)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config)

    try:
        parsed = _parse_date_arg(date)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    db = Database()
    db_entries = db.read(cfg.database)

    if db_entries.empty:
        typer.echo("Database is empty.")
        raise typer.Exit(code=1)

    if isinstance(parsed, date_type):
        # Single date
        report_date = parsed
        result = aggregate_by_date(db_entries, report_date, cfg.timezone)
        if result["is_empty"]:
            typer.echo(f"No entries found for {date}.")
            raise typer.Exit(code=1)
        if report_type == "bar":
            _show_bar_single(report_date, result, cfg.timezone)
        else:
            _print_daily_report(report_date, result)
    else:
        # Date range
        start_date, end_date = parsed
        total_seconds = 0.0
        total_activity: dict[str, float] = {}
        total_tags: dict[str, float] = {}
        total_categories: dict[str, float] = {}
        daily_results: list[tuple[date_type, dict[str, Any]]] = []
        any_data = False

        current = start_date
        while current <= end_date:
            day_result = aggregate_by_date(db_entries, current, cfg.timezone)
            if not day_result["is_empty"]:
                any_data = True
                total_seconds += day_result["total_seconds"]
                for act, secs in day_result["activity_breakdown"].items():
                    total_activity[act] = total_activity.get(act, 0.0) + secs
                for tag, secs in day_result["tag_breakdown"].items():
                    total_tags[tag] = total_tags.get(tag, 0.0) + secs
                for cat, secs in day_result["category_breakdown"].items():
                    total_categories[cat] = total_categories.get(cat, 0.0) + secs
                daily_results.append((current, day_result))
            current += timedelta(days=1)

        if not any_data:
            typer.echo(f"No entries found for {start_date} to {end_date}.")
            raise typer.Exit(code=1)

        if report_type == "bar":
            _show_bar_range(
                start_date,
                end_date,
                total_seconds,
                total_activity,
                total_tags,
                total_categories,
                daily_results,
                cfg.timezone,
            )
        else:
            # Print range summary
            typer.echo(f"\n{'=' * 50}")
            typer.echo(
                f"Range Report: {start_date.strftime('%Y-%m-%d')} "
                f"to {end_date.strftime('%Y-%m-%d')}"
            )
            typer.echo(f"{'=' * 50}")
            typer.echo(f"Total Time: {_seconds_to_hhmm(total_seconds)}\n")

            if total_activity:
                _print_breakdown("Activity", total_activity, total_seconds)

            if total_tags:
                _print_breakdown("Tag", total_tags, total_seconds)

            if total_categories:
                _print_breakdown("Category", total_categories, total_seconds)

            # Print daily breakdowns
            for day_date, day_result in daily_results:
                _print_daily_report(day_date, day_result)


if __name__ == "__main__":
    app()
