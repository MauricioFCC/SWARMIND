# Contributing to Swarmind

Thank you for your interest in contributing! This document outlines the guidelines and workflow.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)

## Code of Conduct

Be respectful, constructive, and collaborative. Harassment or discriminatory behavior will not be tolerated.

## Getting Started

1. Fork the repository.
2. Clone your fork: `git clone https://github.com/your-username/SWARMIND.git`
3. Set up the development environment (see below).

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) for Python package management.

```bash
# Install uv (if not already installed)
pip install uv

# Create a virtual environment and install dependencies
uv sync

# Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install pre-commit hooks
python install_hooks.py
```

## Coding Standards

- **Language**: Python 3.10+ (type hints required for all public APIs)
- **Style**: Follow [PEP 8](https://peps.python.org/pep-0008/). Linting is enforced via `ruff`.
- **Linting**: `ruff check harness/`
- **Type checking**: `mypy harness/ --ignore-missing-imports`
- **Line length**: 120 characters (configured in `ruff.toml` / `pyproject.toml`)
- **Docstrings**: Google-style, written in English.

Run both before committing:

```bash
ruff check harness/
mypy harness/ --ignore-missing-imports
```

## Testing

- Tests are located in `harness/tests/`.
- We use `pytest` with `asyncio_mode = auto`.

```bash
# Run all tests
pytest harness/tests/ -v

# Run with coverage
pytest harness/tests/ -v --cov=harness

# Run unit tests only
pytest harness/tests/ -v -m unit

# Run slow/integration tests
pytest harness/tests/ -v -m slow
pytest harness/tests/ -v -m integration
```

Write tests for all new functionality. Aim for at least 50% project coverage.

## Documentation

- **Code documentation**: Use Google-style docstrings for public modules, classes, and functions.
- **Architecture Decision Records (ADRs)**: Create a new ADR in `docs/src/adr/` for significant architectural decisions.
- **mdbook**: User-facing and architectural documentation is built with [mdbook](https://rust-lang.github.io/mdBook/). To build locally:
  ```bash
  mdbook build
  ```
  The output goes to `docs/book/`.

## Commit Convention

Use conventional commits:

```
<type>(<scope>): <subject>

<body>
```

Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `ci`, `chore`, `security`

Examples:
- `feat(orchestrator): add adaptive pool resizing`
- `fix(guardian): handle timeout in agent response`
- `docs(adr): add ADR-0033 for cache eviction strategy`

## Pull Request Process

1. Create a feature branch from `develop` (or `main` for hotfixes).
2. Make your changes following the coding standards above.
3. Add or update tests as needed.
4. Ensure all checks pass locally.
5. Update the CHANGELOG.
6. Open a PR against `develop` (or `main` for hotfixes) using the PR template.
7. Request review from at least one maintainer.
8. Address review feedback. Merge is blocked until all discussions are resolved.

## Issue Reporting

- **Bug reports**: Use the `Bug Report` template. Include steps to reproduce, logs, and environment info.
- **Feature requests**: Use the `Feature Request` template. Describe the problem, solution, and alternatives.
- **Configuration changes**: Use the `Configuration Change` template for CI, linter, or tooling changes.
