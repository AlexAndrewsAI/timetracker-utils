# python-package-template

A basic template package demonstrating Python packaging best practices using **uv**, **pydantic**, and **pytest**.

## Overview

This is a minimal but well-structured Python package that serves as a template for building larger projects. It demonstrates:

- Modern Python packaging with `pyproject.toml`
- Type hints and static type checking with **mypy**
- Data validation using **pydantic**
- Code linting with **ruff**
- Testing with **pytest**
- Dependency management with **uv**

This package is intentionally simple to provide a clean starting point for your own projects.

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

**Option 1: Use this template (recommended)**

Visit https://github.com/AlexAndrewsAI/python-package-template and click the green "Use this template" button to create your own repository. Then clone your new repository:

```bash
cd your-repo-name
uv sync
```

**Option 2: Clone directly**

```bash
git clone https://github.com/AlexAndrewsAI/python-package-template.git
cd python-package-template  
uv sync
```

To install the package in editable mode (recommended for development) and test the CLI:

```bash
uv pip install -e .
hello-world --version
```

## Usage

### Basic Example

```python
from python_package_template.hello import HelloWorld
from python_package_template.config import Config

# Create with default name
hello = HelloWorld()
greeting = hello.greet() # Hello, World!

# Create with custom name
hello = HelloWorld(Config(name="Alice"))
personal_greeting = hello.greet() # Hello, Alice!
```

### Configuration

The `Config` class uses **pydantic** for validation:

```python
from python_package_template.config import Config

# Create with default name
config = Config()

# Create with custom name
config = Config(name="Alice")
```

### Command Line Interface

The package includes a CLI tool built with **typer**:

```bash
# Show version
uv run hello-world --version

# Run the CLI with default name
uv run hello-world hello

# Greet a specific name
uv run hello-world hello --name Alice

# Show help
uv run hello-world hello --help
```

## Development

### Install Dev Dependencies

```bash
uv sync --dev
```

This installs all dependencies and dev tools (pytest, ruff, mypy).

### Run Tests

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/test_hello.py::test_default_name
```

### Code Quality

```bash
# Lint code
uv run ruff check
uv run ruff format

# Type check
uv run mypy .
```

## Project Structure

- generate using `git ls-tree -r --name-only HEAD | tree --fromfile`
```
python-package-template/
├── AGENTS.md
├── .gitignore
├── pyproject.toml
├── python_package_template
│   ├── cli.py
│   ├── config.py
│   ├── hello.py
│   └── __init__.py
├── README.md
├── tests
│   ├── __init__.py
│   └── test_hello.py
└── uv.lock
```



## Agent Instructions

This template includes two agent instruction files for different workflows:

### AGENTS.md
Complete instructions for an AI agent with full automation. The agent automatically runs `pytest`, `ruff check`, and `mypy` after code changes to validate quality before handoff.

**Best for:** Fully autonomous workflows where the agent handles all validation.

### AGENTS_MANUAL_CHECKS.md
Streamlined instructions that skip automated validation tools to reduce token usage. The agent writes code with quality standards in mind, but you manually run `pytest`, `ruff check`, and `mypy` for final validation.

**Best for:** Cost-conscious workflows or when you prefer manual control over validation timing.

Both files enforce the same code standards and project structure—only the automation scope differs.


## Features

- **Type hints**: Full type annotations for better IDE support and mypy compatibility
- **Pydantic validation**: Runtime type validation and serialization
- **Configuration**: Externalize settings using the `Config` class
- **Testing**: Comprehensive test suite with pytest
- **Code quality**: Automated linting with ruff and type checking with mypy

## Python Best Practices Used

- ✅ **Type hints**: All functions and classes use type annotations
- ✅ **Docstrings**: Clear descriptions of modules, classes, and functions
- ✅ **Project structure**: Proper package layout with separation of concerns
- ✅ **Testing**: Comprehensive test coverage with pytest
- ✅ **Configuration**: Externalized config using pydantic BaseModel
- ✅ **Linting**: Code quality checks with ruff
- ✅ **Dependency management**: Explicit dependencies in pyproject.toml
- ✅ **Python versions**: Supports Python 3.10+

## License

MIT

## Contributing

This is a template repository. Feel free to use it as a starting point for your own projects.

## Author

AlexAndrewsAI <alex.andrews.ai@protonmail.com>