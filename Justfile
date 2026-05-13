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

# --- Docker / database (Phase 1) ---

# Start the local stack (Postgres) in background
db-up:
    docker compose up -d

# Stop the stack, keep data volume
db-down:
    docker compose down

# Drop the stack AND wipe Postgres data (destructive)
db-reset:
    docker compose down -v

# Tail Postgres logs (Ctrl+C to exit)
db-logs:
    docker compose logs -f postgres

# Open a psql shell inside the Postgres container
db-shell:
    docker compose exec postgres psql -U footy -d footy

# Show container status / health
db-status:
    docker compose ps
