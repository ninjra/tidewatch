# Contributing to Tidewatch

## Setup

```bash
git clone git@github.com:ninjra/tidewatch.git
cd tidewatch
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ -v          # full suite
python -m pytest tests/ -q --tb=no  # quick pass/fail
python -m pytest tests/ --cov=tidewatch --cov-report=term-missing  # with coverage
```

## Code Style

- Python 3.11+, type hints on all public functions
- Lint with [ruff](https://docs.astral.sh/ruff/): `ruff check tidewatch/ tests/`
- Zero runtime dependencies — stdlib only in `tidewatch/`
- Pure math in core — no database, no LLM, no async in the pressure engine

## Pull Request Process

1. Fork and create a feature branch
2. Ensure all tests pass: `python -m pytest tests/ -q`
3. Ensure lint is clean: `ruff check tidewatch/ tests/`
4. Submit PR against `main`

## Reporting Issues

Open an issue at [github.com/ninjra/tidewatch/issues](https://github.com/ninjra/tidewatch/issues).
