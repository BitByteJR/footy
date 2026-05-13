"""FastAPI application."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from footy.db import get_session
from footy.models import Competition

app = FastAPI(title="footy", version="0.1.0")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Free-tier competition codes per football-data.org free plan.
FREE_CODES: frozenset[str] = frozenset(
    {"PL", "BL1", "FL1", "SA", "PD", "CL", "EC", "PPL", "DED", "BSA"}
)
CONFEDERATIONS = 6  # UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC

SortKey = Literal["area", "code", "name", "id"]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/competitions")
def list_competitions(
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, str | int | None]]:
    rows = session.scalars(select(Competition).order_by(Competition.code)).all()
    return [{"id": c.id, "code": c.code, "name": c.name, "area": c.area_name} for c in rows]


def _filter_and_sort(
    rows: list[Competition],
    *,
    area: str | None,
    sort: SortKey,
    q: str | None,
) -> list[Competition]:
    """In-memory filter + sort over the already-loaded competitions list."""
    out = rows
    if area:
        out = [c for c in out if c.area_name == area]
    if q:
        needle = q.strip().lower()
        if needle:
            out = [
                c
                for c in out
                if needle in c.name.lower()
                or (c.code and needle in c.code.lower())
                or needle in c.area_name.lower()
            ]

    key_fns = {
        "area": lambda c: (c.area_name.lower(), (c.code or "zzz").lower(), c.name.lower()),
        "code": lambda c: (c.code is None, (c.code or "").lower(), c.name.lower()),
        "name": lambda c: c.name.lower(),
        "id": lambda c: c.id,
    }
    return sorted(out, key=key_fns[sort])


def _page_context(
    all_rows: list[Competition],
    *,
    area: str | None,
    sort: SortKey,
    q: str | None,
) -> dict:
    total = len(all_rows)
    area_counts = Counter(c.area_name for c in all_rows)
    return {
        "rows": _filter_and_sort(all_rows, area=area, sort=sort, q=q),
        "total": total,
        "unique_areas": len(area_counts),
        "top_areas": area_counts.most_common(12),
        "selected_area": area,
        "sort": sort,
        "q": q,
        "free_codes": FREE_CODES,
        "free_count": sum(1 for c in all_rows if c.code in FREE_CODES),
        "confederations": CONFEDERATIONS,
        "compiled_at": datetime.now(UTC).strftime("%Y-%m-%d"),
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    area: str | None = None,
    sort: SortKey = "area",
    q: str | None = None,
) -> HTMLResponse:
    all_rows = list(session.scalars(select(Competition)).all())
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_page_context(all_rows, area=area, sort=sort, q=q),
    )


@app.get("/htmx/competitions", response_class=HTMLResponse)
def htmx_competitions(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    area: str | None = None,
    sort: SortKey = "area",
    q: str | None = None,
) -> HTMLResponse:
    all_rows = list(session.scalars(select(Competition)).all())
    return templates.TemplateResponse(
        request=request,
        name="partials/competitions_grid.html",
        context=_page_context(all_rows, area=area, sort=sort, q=q),
    )
