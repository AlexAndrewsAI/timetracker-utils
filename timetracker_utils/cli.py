"""Command line interface module.

Provides a typer-based CLI for the package.
"""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import typer

from timetracker_utils import __version__
from timetracker_utils.config import load_config
from timetracker_utils.database import Database
from timetracker_utils.datetime_utils import (
    aggregate_by_date,
    convert_column_tz,
    resolve_tz,
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


def _format_timecop_csv(
    entries: pd.DataFrame, output_path: Path, timezone: str = "UTC"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "Date",
        "Project",
        "Description",
        "Combined Project & Description",
        "Start Time",
        "End Time",
        "Time (hours)",
        "Notes",
    ]
    if entries.empty:
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
        return
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for _, row in entries.iterrows():
            date = str(row.get("date", ""))
            project = str(row.get("activity", ""))
            description = str(row.get("categories", [""]))
            if isinstance(row.get("categories"), list):
                description = row["categories"][0] if row["categories"] else ""
            description = str(description)
            combined = f"{project}: {description}"
            start_time = row.get("start_time")
            end_time = row.get("end_time")
            notes = str(row.get("notes", ""))
            start_str = _format_datetime_iso(start_time, timezone)
            end_str = _format_datetime_iso(end_time, timezone)
            hours_str = _compute_hours(start_time, end_time)
            writer.writerow(
                [
                    date,
                    project,
                    description,
                    combined,
                    start_str,
                    end_str,
                    hours_str,
                    notes,
                ]
            )


def _format_simple_csv(
    entries: pd.DataFrame, output_path: Path, timezone: str = "UTC"
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "activity name",
        "time started",
        "time ended",
        "comment",
        "categories",
        "record tags",
        "duration",
        "duration minutes",
    ]
    if entries.empty:
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
        return
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for _, row in entries.iterrows():
            activity = str(row.get("activity", ""))
            start_time = row.get("start_time")
            end_time = row.get("end_time")
            notes = str(row.get("notes", ""))
            categories = row.get("categories", [])
            if isinstance(categories, list):
                categories_str = ", ".join(categories)
            else:
                categories_str = str(categories)
            tags = row.get("tags", [])
            tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            start_str = _format_simple_datetime(start_time, timezone)
            end_str = _format_simple_datetime(end_time, timezone)
            duration_str, duration_min_str = _compute_simple_duration(
                start_time, end_time
            )
            writer.writerow(
                [
                    activity,
                    start_str,
                    end_str,
                    notes,
                    categories_str,
                    tags_str,
                    duration_str,
                    duration_min_str,
                ]
            )


def _format_simple_datetime(val: object, target_tz: str = "UTC") -> str:
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return ""
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return val
    elif isinstance(val, datetime):
        dt = val
    else:
        return str(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone = resolve_tz(target_tz)
    if zone is not None:
        dt = dt.astimezone(zone)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    millis = f"{dt.microsecond // 1000:03d}"
    offset_seconds = dt.utcoffset()
    if offset_seconds is None:
        offset = "+00:00"
    else:
        total_seconds = int(offset_seconds.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        offset = f"{sign}{hours:02d}:{minutes:02d}"
    return f"{base}.{millis}{offset}"


def _compute_simple_duration(start_time: object, end_time: object) -> tuple[str, str]:
    if start_time is None or end_time is None:
        return "", ""
    try:
        if isinstance(start_time, str):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        elif isinstance(start_time, datetime):
            start_dt = start_time
        else:
            return "", ""
        if isinstance(end_time, str):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        elif isinstance(end_time, datetime):
            end_dt = end_time
        else:
            return "", ""
        delta = end_dt - start_dt
        total_secs = int(delta.total_seconds())
        hours = total_secs // 3600
        remainder = total_secs % 3600
        minutes = remainder // 60
        seconds = remainder % 60
        duration_str = f"{hours}:{minutes}:{seconds}"
        duration_min_str = str(round(hours * 60 + minutes + seconds / 60.0, 4))
        return duration_str, duration_min_str
    except (ValueError, TypeError):
        return "", ""


def _format_datetime_iso(val: object, target_tz: str = "UTC") -> str:
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return ""
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return val
    elif isinstance(val, datetime):
        dt = val
    else:
        return str(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone = resolve_tz(target_tz)
    if zone is not None:
        dt = dt.astimezone(zone)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    millis = f"{dt.microsecond // 1000:03d}"
    offset_seconds = dt.utcoffset()
    if offset_seconds is None:
        offset = "+00:00"
    else:
        total_seconds = int(offset_seconds.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        offset = f"{sign}{hours:02d}:{minutes:02d}"
    return f"{base}.{millis}{offset}"


def _compute_hours(start_time: object, end_time: object) -> str:
    if start_time is None or end_time is None:
        return ""
    if isinstance(start_time, str) and start_time.strip() == "":
        return ""
    if isinstance(end_time, str) and end_time.strip() == "":
        return ""
    try:
        if isinstance(start_time, str):
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        elif isinstance(start_time, datetime):
            start_dt = start_time
        else:
            return ""
        if isinstance(end_time, str):
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        elif isinstance(end_time, datetime):
            end_dt = end_time
        else:
            return ""
        delta = end_dt - start_dt
        hours = delta.total_seconds() / 3600.0
        return f"{hours:.4f}"
    except (ValueError, TypeError):
        return ""


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


def _seconds_to_hhmm(total_seconds: float) -> str:
    """Convert seconds to hh:mm string format."""
    total_seconds = max(0.0, total_seconds)
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"


@app.command()
def report(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to the YAML configuration file."
    ),
    date: str = typer.Option(
        ..., "--date", "-d", help="Date to report on (yyyy-mm-dd format)."
    ),
) -> None:
    """Show a daily report of activities, tags, and categories.

    Aggregates total time (in hh:mm) and displays tables for activities,
    tags, and categories for the specified date.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config)

    try:
        report_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        typer.echo(f"Invalid date format: {date!r}. Use yyyy-mm-dd.", err=True)
        raise typer.Exit(code=1) from exc

    db = Database()
    db_entries = db.read(cfg.database)

    if db_entries.empty:
        typer.echo("Database is empty.")
        raise typer.Exit(code=1)

    result = aggregate_by_date(db_entries, report_date, cfg.timezone)

    if result["is_empty"]:
        typer.echo(f"No entries found for {date}.")
        raise typer.Exit(code=1)

    typer.echo(f"\n{'=' * 50}")
    typer.echo(f"Daily Report: {report_date.strftime('%A, %B %d, %Y')}")
    typer.echo(f"{'=' * 50}")
    typer.echo(f"Total Time: {_seconds_to_hhmm(result['total_seconds'])}\n")

    activity_breakdown = result["activity_breakdown"]
    if activity_breakdown:
        typer.echo("-" * 30)
        typer.echo(f"{'Activity':<20} {'Time':>8}")
        typer.echo("-" * 30)
        for activity, secs in sorted(activity_breakdown.items()):
            typer.echo(f"{activity:<20} {_seconds_to_hhmm(secs):>8}")
        typer.echo()

    tag_breakdown = result["tag_breakdown"]
    if tag_breakdown:
        typer.echo("-" * 30)
        typer.echo(f"{'Tag':<20} {'Time':>8}")
        typer.echo("-" * 30)
        for tag, secs in sorted(tag_breakdown.items()):
            typer.echo(f"{tag:<20} {_seconds_to_hhmm(secs):>8}")
        typer.echo()

    category_breakdown = result["category_breakdown"]
    if category_breakdown:
        typer.echo("-" * 30)
        typer.echo(f"{'Category':<20} {'Time':>8}")
        typer.echo("-" * 30)
        for category, secs in sorted(category_breakdown.items()):
            typer.echo(f"{category:<20} {_seconds_to_hhmm(secs):>8}")
        typer.echo()


if __name__ == "__main__":
    app()
