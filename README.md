# timetracker-utils

This repository, CLI, and all associated materials are provided on an **"as is" basis only**. We make no warranties or representations, express or implied, as to the accuracy, completeness, or fitness for a particular purpose of any content. At no point does the developer have any duty to correct, update, or support the provided material. **Use at your own risk.**

Time tracker utilities for parsing, validating, and persisting CSV time tracking data. Built with **Pydantic**, **pandas**, **Typer**, and **SQLite**.

## Overview

This package processes CSV time tracking exports (in the TimeCop format), validates each entry using Pydantic models, and persists the data to a SQLite database with intelligent merge semantics. It supports timezone-aware datetime handling, conflict detection, and round-trip export back to CSV.

## Features

- **CSV parsing & validation**: Read and validate TimeCop-format CSV files with Pydantic
- **Smart merge semantics**: Import CSV data into a SQLite database with three merge rules:
  1. **Duplicate drop**: Identical rows are silently skipped
  2. **Blank-fill**: Missing fields (date, notes) are filled in from later imports
  3. **Conflict detection**: Non-blank conflicting values raise a `MergeConflictError`
- **Timezone conversion**: Display timestamps in any IANA or abbreviation timezone (ET, PT, UTC, etc.)
- **Round-trip CSV export**: Export the entire database back to TimeCop-format CSV
- **CLI interface**: Full-featured command-line interface via Typer

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
git clone https://github.com/AlexAndrewsAI/timetracker-utils.git
cd timetracker-utils
uv sync --dev
```

## Usage

### Example Files

The `tests/` directory includes example CSV files for both supported formats:

- `example_timecop.csv` - TimeCop format sample data
- `example_simpletimetracker.csv` - Simple Time Tracker format sample data

### Configuration

Create a YAML configuration file pointing to your SQLite database:

```yaml
database: /path/to/data/timetracker/db.sqlite3
timezone: ET
max_conflict_display: 100
```

### CLI

The package provides a `timetracker` CLI with commands for both supported formats:

#### TimeCop Format

```bash
# Show version
uv run timetracker --version

# Import a TimeCop CSV file and display entries
uv run timetracker timecop --config tests/timetracker.yml --input tests/example_timecop.csv

# Export the database back to TimeCop CSV
uv run timetracker timecop --config tests/timetracker.yml --output timecop_export.csv

# Both import and export in one command
uv run timetracker timecop --config tests/timetracker.yml --input tests/example_timecop.csv --output output.csv

# Control how many rows to display
uv run timetracker timecop --config tests/timetracker.yml --input tests/example_timecop.csv --head 5
```

#### Simple Time Tracker Format

```bash
# Import a Simple Time Tracker CSV file and display entries
uv run timetracker stt --config tests/timetracker.yml --input tests/example_simpletimetracker.csv

# Export the database back to Simple Time Tracker CSV
uv run timetracker stt --config tests/timetracker.yml --output stt_export.csv

# Both import and export in one command
uv run timetracker stt --config tests/timetracker.yml --input tests/example_simpletimetracker.csv --output output.csv

# Control how many rows to display
uv run timetracker stt --config tests/timetracker.yml --input tests/example_simpletimetracker.csv --head 5
```

### Python API

```python
from timetracker_utils import TimeCop, TimeEntry

# Parse a CSV string
cop = TimeCop()
csv_data = '''\
"Date","Project","Description","Combined Project & Description","Start Time","End Time","Time (hours)","Notes"
"4/13/2026","Research","literature review","Research: literature review","2026-04-13T09:00:00.000Z","2026-04-13T11:30:00.000Z","2.5",""
'''
df = cop.read_csv_string(csv_data)
print(f"Loaded {len(df)} entries")
print(f"Total hours: {cop.total_hours()}")
print(f"Hours by project: {cop.total_hours_by_project()}")
```

```python
from timetracker_utils.database import Database

db = Database()

# Write entries to a SQLite database (with merge semantics)
db.write(df, "/path/to/db.sqlite3")

# Read all entries back
entries = db.read("/path/to/db.sqlite3")
print(f"Database has {len(entries)} entries")
```

```python
from timetracker_utils.datetime_utils import convert_column_tz

# Convert timestamps to a specific timezone
converted = convert_column_tz(df["start_time"], "America/New_York")
```

## Project Structure

```
timetracker-utils/
├── AGENTS.md
├── pyproject.toml
├── README.md
├── timetracker_utils/
│   ├── __init__.py         # Package entry point, version
│   ├── __main__.py         # python -m entry point
│   ├── cli.py              # Typer CLI interface
│   ├── config.py           # Pydantic config model (YAML-backed)
│   ├── database.py         # SQLite persistence with merge logic
│   ├── datetime_utils.py   # Timezone conversion utilities
│   └── time_cop.py         # CSV parsing & Pydantic validation
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_datetime_utils.py
│   └── test_time_cop.py
└── uv.lock
```

## Development

### Install Dev Dependencies

```bash
uv sync --dev
```

### Run Tests

```bash
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_time_cop.py
```

### Code Quality

```bash
# Lint
uv run ruff check .

# Auto-format
uv run ruff format .

# Type check
uv run mypy .
```

## Technology Stack

| Component         | Tool          |
|-------------------|---------------|
| Environment       | uv            |
| Data Validation   | Pydantic      |
| CLI               | Typer         |
| Data Processing   | pandas        |
| Database          | SQLite        |
| Testing           | pytest        |
| Linting           | ruff          |
| Type Checking     | mypy          |

## License

MIT

## Author

AlexAndrewsAI <alex.andrews.ai@protonmail.com>
