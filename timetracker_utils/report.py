"""Report generation and bar chart rendering for time tracking data.

Provides functions for generating daily/range reports in text format
and interactive matplotlib bar charts with multi-page navigation.
"""

import logging
import warnings
from datetime import date as date_type
from datetime import datetime
from typing import Any

import typer

from timetracker_utils.csv_formatters import _seconds_to_hhmm

logger = logging.getLogger(__name__)

_REPORT_TYPES = ["text", "bar"]


def _parse_date_arg(date_str: str) -> date_type | tuple[date_type, date_type]:
    """Parse a date string as either a single date or a date range.

    Accepts:
        - ``yyyy-mm-dd`` — single date
        - ``yyyy-mm-dd:yyyy-mm-dd`` — date range (inclusive)

    Returns:
        A single ``date`` or a ``(start_date, end_date)`` tuple.

    Raises:
        ValueError: If the format is invalid or start > end.

    """
    parts = date_str.split(":")
    if len(parts) == 1:
        try:
            return datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"Invalid date format: {parts[0]!r}. Use yyyy-mm-dd."
            ) from exc
    if len(parts) == 2:
        try:
            start = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"Invalid date range format: {date_str!r}. Use yyyy-mm-dd:yyyy-mm-dd."
            ) from exc
        if start > end:
            raise ValueError(f"Start date {start} is after end date {end}.")
        return start, end
    raise ValueError(
        f"Invalid date format: {date_str!r}. Use yyyy-mm-dd or yyyy-mm-dd:yyyy-mm-dd."
    )


def _print_daily_report(
    report_date: date_type,
    result: dict[str, Any],
) -> None:
    """Print a formatted daily report from an aggregate result dict."""
    total_secs = result["total_seconds"]
    typer.echo(f"\n{'=' * 50}")
    typer.echo(f"Daily Report: {report_date.strftime('%A, %B %d, %Y')}")
    typer.echo(f"{'=' * 50}")
    typer.echo(f"Total Time: {_seconds_to_hhmm(total_secs)}\n")

    activity_breakdown = result["activity_breakdown"]
    if activity_breakdown:
        _print_breakdown("Activity", activity_breakdown, total_secs)

    tag_breakdown = result["tag_breakdown"]
    if tag_breakdown:
        _print_breakdown("Tag", tag_breakdown, total_secs)

    category_breakdown = result["category_breakdown"]
    if category_breakdown:
        _print_breakdown("Category", category_breakdown, total_secs)


def _print_breakdown(
    label: str,
    breakdown: dict[str, float],
    total_secs: float,
) -> None:
    """Print a breakdown table with Activity/Time/% columns.

    Args:
        label: Column header for the item name (e.g. "Activity").

        breakdown: Mapping of item name to seconds.

        total_secs: Total seconds for percentage calculation.

    """
    typer.echo("-" * 40)
    typer.echo(f"{label:<20} {'Time':>8} {'%':>7}")
    typer.echo("-" * 40)
    for item, secs in sorted(breakdown.items()):
        pct = (secs / total_secs * 100.0) if total_secs > 0 else 0.0
        typer.echo(f"{item:<20} {_seconds_to_hhmm(secs):>8} {pct:>6.2f}%")
    typer.echo()


def _import_matplotlib() -> tuple[Any, Any]:
    """Import matplotlib, setting a GUI backend if available.

    Returns the (plt, Button) tuple.

    Raises:
        ImportError: If matplotlib is not installed or no interactive backend
            is available.

    """
    import importlib

    # Try to find a usable GUI backend before importing pyplot
    import os

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        # No display server — try to use a headless-interactive workaround
        # or bail out early with a clear message
        raise ImportError(
            "No display server found ($DISPLAY or $WAYLAND_DISPLAY). "
            "Interactive bar charts require a display. "
            "Use --type text for terminal output, or run with a display."
        )

    # Try common interactive backends in order
    for backend in ("TkAgg", "Qt5Agg", "GTK3Agg", "WXAgg"):
        try:
            importlib.import_module(f"matplotlib.backends.backend_{backend.lower()}")
            import matplotlib

            matplotlib.use(backend)
            break
        except ImportError:
            continue
    else:
        # Let matplotlib pick its default; may still fail at show()
        pass

    import matplotlib.pyplot as plt
    from matplotlib.widgets import Button

    return plt, Button


def _show_bar_single(
    report_date: date_type,
    result: dict[str, Any],
    timezone: str,
) -> None:
    """Show an interactive bar chart for a single day's report."""
    try:
        plt, Button = _import_matplotlib()
    except ImportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    activity = result.get("activity_breakdown", {})
    tags = result.get("tag_breakdown", {})
    categories = result.get("category_breakdown", {})
    total_secs = result["total_seconds"]
    date_str = report_date.strftime("%Y-%m-%d")
    total_label = _seconds_to_hhmm(total_secs)

    pages: list[dict[str, Any]] = []
    if activity:
        pages.append({"title": f"Activity — {date_str}", "data": activity})
    if tags:
        pages.append({"title": f"Tags — {date_str}", "data": tags})
    if categories:
        pages.append({"title": f"Categories — {date_str}", "data": categories})

    if not pages:
        typer.echo("No data to plot.")
        raise typer.Exit(code=1)

    _plot_pages(pages, total_secs, total_label, timezone, plt, Button)


def _show_bar_range(
    start_date: date_type,
    end_date: date_type,
    total_seconds: float,
    total_activity: dict[str, float],
    total_tags: dict[str, float],
    total_categories: dict[str, float],
    daily_results: list[tuple[date_type, dict[str, Any]]],
    timezone: str,
) -> None:
    """Show interactive bar charts for a date range: overview then daily breakdowns."""
    try:
        plt, Button = _import_matplotlib()
    except ImportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    total_label = _seconds_to_hhmm(total_seconds)

    # Build overview pages
    pages: list[dict[str, Any]] = []
    if total_activity:
        pages.append(
            {
                "title": f"Activity — Range {start_str} to {end_str}",
                "data": total_activity,
            }
        )
    if total_tags:
        pages.append(
            {
                "title": f"Tags — Range {start_str} to {end_str}",
                "data": total_tags,
            }
        )
    if total_categories:
        pages.append(
            {
                "title": f"Categories — Range {start_str} to {end_str}",
                "data": total_categories,
            }
        )

    # Append daily pages
    for day_date, day_result in daily_results:
        day_str = day_date.strftime("%Y-%m-%d")
        day_secs = day_result["total_seconds"]
        day_label = _seconds_to_hhmm(day_secs)

        day_activity = day_result.get("activity_breakdown", {})
        day_tags = day_result.get("tag_breakdown", {})
        day_categories = day_result.get("category_breakdown", {})

        if day_activity:
            pages.append(
                {
                    "title": f"Activity — {day_str}",
                    "data": day_activity,
                    "total_secs": day_secs,
                    "total_label": day_label,
                }
            )
        if day_tags:
            pages.append(
                {
                    "title": f"Tags — {day_str}",
                    "data": day_tags,
                    "total_secs": day_secs,
                    "total_label": day_label,
                }
            )
        if day_categories:
            pages.append(
                {
                    "title": f"Categories — {day_str}",
                    "data": day_categories,
                    "total_secs": day_secs,
                    "total_label": day_label,
                }
            )

    if not pages:
        typer.echo("No data to plot.")
        raise typer.Exit(code=1)

    _plot_pages(pages, total_seconds, total_label, timezone, plt, Button)


def _plot_pages(
    pages: list[dict[str, Any]],
    total_secs: float,
    total_label: str,
    timezone: str,
    plt: Any,
    Button: Any,
) -> None:
    """Render a sequence of bar chart pages with Next/Prev navigation.

    Each page dict has:
        - title: str — window title / suptitle
        - data: dict[str, float] — label -> seconds
        - total_secs: float  (optional; defaults to outer total_secs)
        - total_label: str  (optional; defaults to outer total_label)
    """
    idx = 0

    def _render() -> None:
        nonlocal idx
        page = pages[idx]
        data = page["data"]
        secs = page.get("total_secs", total_secs)
        label = page.get("total_label", total_label)

        fig, ax = plt.subplots(figsize=(10, 6))

        items = sorted(data.items())
        names = [k for k, _ in items]
        hours = [v / 3600.0 for _, v in items]
        pcts = [(v / secs * 100.0) if secs > 0 else 0.0 for _, v in items]

        bars = ax.barh(names, hours, color="#4C72B0")
        ax.set_xlabel("Hours")
        ax.set_title(
            f"{page['title']}    Total: {label}",
            fontsize=13,
        )

        # annotate bars with hh:mm and %
        for bar, h, pct in zip(bars, hours, pcts, strict=False):
            ax.text(
                bar.get_width() + 0.05,
                bar.get_y() + bar.get_height() / 2,
                f"{_seconds_to_hhmm(h * 3600)}  ({pct:.1f}%)",
                va="center",
                fontsize=9,
            )

        # page indicator
        fig.text(
            0.5,
            0.02,
            f"Page {idx + 1} of {len(pages)}",
            ha="center",
            fontsize=9,
            color="gray",
        )

        # navigation buttons
        ax_prev = fig.add_axes([0.3, 0.01, 0.12, 0.04])
        ax_next = fig.add_axes([0.58, 0.01, 0.12, 0.04])
        btn_prev = Button(ax_prev, "← Prev")
        btn_next = Button(ax_next, "Next →")

        def _prev(_event: Any) -> None:
            nonlocal idx
            idx = (idx - 1) % len(pages)
            plt.close()
            _render()

        def _next(_event: Any) -> None:
            nonlocal idx
            idx = (idx + 1) % len(pages)
            plt.close()
            _render()

        btn_prev.on_clicked(_prev)
        btn_next.on_clicked(_next)

        # keyboard navigation
        def _on_key(event: Any) -> None:
            nonlocal idx
            if event.key in ("right", "n"):
                idx = (idx + 1) % len(pages)
                plt.close()
                _render()
            elif event.key in ("left", "p", "backspace"):
                idx = (idx - 1) % len(pages)
                plt.close()
                _render()
            elif event.key in ("q", "escape"):
                plt.close()

        fig.canvas.mpl_connect("key_press_event", _on_key)

        # instructions
        fig.text(
            0.01,
            0.01,
            "← → or n/p to navigate  |  q to quit",
            fontsize=8,
            color="gray",
        )

        # timezone note
        fig.text(
            0.99,
            0.01,
            f"tz: {timezone}",
            fontsize=8,
            color="gray",
            ha="right",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plt.tight_layout(rect=[0, 0.06, 1, 1])
        plt.show()

    _render()
