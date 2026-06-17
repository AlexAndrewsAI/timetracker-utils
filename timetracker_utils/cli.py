"""Command line interface module.

Provides a typer-based CLI for the package. Currently a dummy entrypoint
that references the TimeCop class.
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
from timetracker_utils.datetime_utils import convert_column_tz
from timetracker_utils.time_cop import TimeCop

app = typer.Typer(help="Time tracker utilities CLI")

logger = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    """Handle the version flag callback."""
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
    # Reference TimeCop to ensure the class is importable
    _ = TimeCop


def _format_timecop_csv(entries: pd.DataFrame, output_path: Path) -> None:
    """Write entries DataFrame to a timecop-format CSV file.

    Reconstructs the combined project/description column and computes
    hours from start/end time deltas to match the expected timecop CSV
    input format.

    Args:
        entries: DataFrame of database entries (columns: date, project,
            description, start_time, end_time, notes).
        output_path: Path to write the CSV file.

    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Shared header row for timecop CSV format
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
            project = str(row.get("project", ""))
            description = str(row.get("description", ""))
            combined = f"{project}: {description}"
            start_time = row.get("start_time")
            end_time = row.get("end_time")
            notes = str(row.get("notes", ""))

            # Format datetimes to ISO 8601 UTC with millisecond precision
            start_str = _format_datetime_iso(start_time)
            end_str = _format_datetime_iso(end_time)

            # Compute hours from start/end time
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


def _format_datetime_iso(val: object) -> str:
    """Format a datetime value as an ISO 8601 UTC string with millisecond precision.

    Args:
        val: A datetime object, string, or None.

    Returns:
        An ISO 8601 string in the format ``YYYY-MM-DDTHH:MM:SS.000Z``,
        or an empty string if the value is missing.

    """
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return ""
    if isinstance(val, str):
        # Parse the string to get a datetime, then re-format consistently
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
    else:
        dt = dt.astimezone(timezone.utc)
    # Format with millisecond precision and Z suffix
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _compute_hours(start_time: object, end_time: object) -> str:
    """Compute hours from start and end time.

    Args:
        start_time: Start time (datetime, string, or None).
        end_time: End time (datetime, string, or None).

    Returns:
        A string representation of the hours, rounded to 4 decimal
        places, or an empty string if the times are not available.

    """
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
def timecop(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to the YAML configuration file.",
    ),
    input: Path = typer.Option(
        None,  # type: ignore[arg-type]
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
    output: Path = typer.Option(
        None,  # type: ignore[arg-type]
        "--output",
        "-o",
        help="Path to write the entire database in timecop CSV format.",
    ),
) -> None:
    """Load a CSV time tracking file, write to database, and/or export the database.

    If --input is provided, loads the CSV file, writes entries to the database,
    and displays the DataFrame. If --output is provided, exports the entire
    database to a timecop-format CSV file. Both can be used together.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config)

    if input is not None:
        cop = TimeCop()
        cop.read_csv(input)
        db = Database()
        db.write(
            cop.entries, cfg.database, max_conflict_display=cfg.max_conflict_display
        )
        typer.echo(f"Loaded DataFrame ({len(cop.entries)} rows total):")

        # Apply timezone conversion to timestamp columns before display
        display_df = cop.entries.copy()
        if not display_df.empty and "start_time" in display_df.columns:
            display_df["start_time"] = convert_column_tz(
                display_df["start_time"], cfg.timezone
            )
        if not display_df.empty and "end_time" in display_df.columns:
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

    if output is not None:
        db = Database()
        db_entries = db.read(cfg.database)
        if db_entries.empty:
            typer.echo("Database is empty, writing header-only CSV.")
        else:
            typer.echo(f"Exporting {len(db_entries)} entries to {output}")
        _format_timecop_csv(db_entries, output)

    if input is None and output is None:
        typer.echo(
            "No --input or --output specified. Use --input to load a CSV, "
            "--output to export the database, or both.",
            err=True,
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
