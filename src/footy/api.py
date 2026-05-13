"""FastAPI application."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from footy.db import get_session
from footy.models import Competition

app = FastAPI(title="footy", version="0.1.0")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/competitions")
def list_competitions(
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, str | int | None]]:
    rows = session.scalars(select(Competition).order_by(Competition.code)).all()
    return [{"id": c.id, "code": c.code, "name": c.name, "area": c.area_name} for c in rows]


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    rows = session.scalars(
        select(Competition).order_by(Competition.area_name, Competition.code)
    ).all()
    area_counts = Counter(c.area_name for c in rows)
    top_areas = area_counts.most_common(12)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "competitions": rows,
            "total": len(rows),
            "unique_areas": len(area_counts),
            "top_areas": top_areas,
            "compiled_at": datetime.now(UTC).strftime("%Y · %m · %d"),
        },
    )
