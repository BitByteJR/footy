# Use PowerShell on Windows; default sh on Linux/macOS. Recipes stay portable.
set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

# Default: show all recipes
default:
    @just --list

# Install Python (via uv) and sync all dependencies including dev group
install:
    uv sync

# Lint the codebase
lint:
    uv run ruff check .

# Lint and auto-fix issues
lint-fix:
    uv run ruff check . --fix

# Format code
format:
    uv run ruff format .

# Check formatting without modifying files
format-check:
    uv run ruff format . --check

# Run tests
test:
    uv run pytest

# Install pre-commit hooks into .git/hooks
hooks-install:
    uv run pre-commit install

# Run pre-commit on all files (not just staged)
hooks-run:
    uv run pre-commit run --all-files

# Local CI: what GitHub Actions will run later
ci: lint format-check test
