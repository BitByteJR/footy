"""Pytest fixtures.

Tests use an in-memory SQLite engine — fast and no Docker dependency.
The real Postgres is exercised by Alembic migrations and `just db-shell`.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from footy.api import app
from footy.db import Base, get_session


@pytest.fixture
def session() -> Generator[Session, None, None]:
    # StaticPool + check_same_thread=False keeps the same in-memory DB across
    # threads — TestClient runs handlers in Starlette's threadpool, so a
    # per-thread connection would see an empty schema.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    def override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
