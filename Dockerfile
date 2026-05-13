# syntax=docker/dockerfile:1.7

# --- builder: install deps with uv, build the .venv ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies in their own layer (cache-friendly: changes only when lock/pyproject change)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Then install the project itself
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


# --- runtime: slim Python, only the resolved .venv + project sources ---
FROM python:3.12-slim-bookworm

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /app /app

EXPOSE 8000

# `exec` so uvicorn becomes PID 1 and receives SIGTERM directly
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn footy.api:app --host 0.0.0.0 --port 8000"]
