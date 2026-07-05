# Agent Instructions: timetracker-utils

## Quick Start
1. **Setup:** Run `uv sync --dev` before major work sessions
2. **Activate:** Ensure `.venv` is active; run `uv venv` if missing
3. **Code:** Use `python3` or `uv run python`; always add type hints and tests

## Tech Stack
| Component | Tool |
|-----------|------|
| Environment & Dependencies | uv |
| Data Validation | Pydantic |
| CLI Framework | Typer |
| Testing | pytest |
| Linting & Formatting | ruff |
| Type Checking | mypy |
| Security Audit | pip-audit |

## Project Structure
```
timetracker-utils/
  ├── timetracker_utils/
  │   ├── cli.py              (Typer CLI interface)
  │   ├── config.py           (Pydantic config model)
  │   ├── database.py         (SQLite persistence)
  │   ├── datetime_utils.py   (Timezone conversion)
  │   ├── report.py           (Report generation)
  │   ├── time_cop.py         (TimeCop CSV parsing)
  │   ├── simple_time_tracker.py (Simple Time Tracker parsing)
  │   └── base_tracker.py     (Base tracker class)
tests/                   (Pytest suite)
pyproject.toml           (Dependencies & tool config)
```

## Essential Directives

### Code Standards
- **Type Hints:** Required on ALL function signatures and class members. Enforce strictly with mypy. Avoid using `# type: ignore` comments to suppress mypy errors; fix the underlying type issues instead.
- **Docstrings:** Google-style format for all public APIs.
- **Logging:** Use `logging` module only; never `print()`.
- **Relative Paths:** Never use absolute paths in code.

### Dependency & Configuration Management
- **Adding/Removing Dependencies:** Use `uv add` / `uv remove` commands.
- **Editing pyproject.toml:** Avoid manual edits during development. Only update `pyproject.toml` as the **final change** after all work is tested and finalized.
- **Before Major Work:** Always run `uv sync --dev` first.

### Testing & Quality
- **Test Coverage:** Every code change requires corresponding tests in `tests/`.
- **Validation Before Commit:** Run the full suite: `uv run pytest`, `uv run ruff check .`, `uv run mypy .`, `uv run pip-audit`.

### Operational Constraints
- **No Interactive Prompts:** Mock or bypass any interactive commands.
- **No Git Operations:** Don't stage/commit unless explicitly requested.
- **Code Review Mode:** Analyze only; record findings in `./REVIEW.md` without making modifications. At the top of the review, identify the reviewer including the name of the IDE/CLI used and the primary model that performed the review.

### File Maintenance
- **Keep Instructions Current:** Update "Tech Stack," "Project Structure," and "Workflow Commands" if `pyproject.toml`, structure, or core logic changes.

## Workflow Commands
```bash
uv sync --dev                           # Install/sync all dependencies
uv run pytest                           # Run tests
uv run ruff check .                     # Lint
uv run ruff format .                    # Auto-format
uv run mypy .                           # Type check
uv run pip-audit                        # Security audit
uv run timetracker --version            # Test CLI
```