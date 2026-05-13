"""FastAPI application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from footy.db import get_session
from footy.models import Competition, Match, Scorer, Team

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


@dataclass
class StandingRow:
    rank: int
    team: Team
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    gd: int
    points: int


def _compute_standings(teams: list[Team], matches: list[Match]) -> list[StandingRow]:
    """Derive standings from the matches list. PL: 3pts win / 1 draw / 0 loss."""
    stats: dict[int, dict] = {
        t.id: {"team": t, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for t in teams
    }
    for m in matches:
        if m.home_score is None or m.away_score is None:
            continue
        h, a = stats.get(m.home_team_id), stats.get(m.away_team_id)
        if h is None or a is None:
            continue
        h["p"] += 1
        a["p"] += 1
        h["gf"] += m.home_score
        h["ga"] += m.away_score
        a["gf"] += m.away_score
        a["ga"] += m.home_score
        if m.home_score > m.away_score:
            h["w"] += 1
            a["l"] += 1
            h["pts"] += 3
        elif m.home_score < m.away_score:
            a["w"] += 1
            h["l"] += 1
            a["pts"] += 3
        else:
            h["d"] += 1
            a["d"] += 1
            h["pts"] += 1
            a["pts"] += 1

    rows = [
        StandingRow(
            rank=0,
            team=s["team"],
            played=s["p"],
            won=s["w"],
            drawn=s["d"],
            lost=s["l"],
            gf=s["gf"],
            ga=s["ga"],
            gd=s["gf"] - s["ga"],
            points=s["pts"],
        )
        for s in stats.values()
    ]
    rows.sort(key=lambda r: (-r.points, -r.gd, -r.gf, r.team.name))
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows


@app.get("/premier-league", response_class=HTMLResponse)
def premier_league(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    pl = session.scalar(select(Competition).where(Competition.code == "PL"))
    if pl is None:
        raise HTTPException(status_code=503, detail="Run `uv run footy pl` first to load data.")

    teams = list(session.scalars(select(Team).where(Team.competition_id == pl.id)).all())
    if not teams:
        raise HTTPException(status_code=503, detail="No PL data yet. Run `uv run footy pl`.")

    matches = list(
        session.scalars(
            select(Match)
            .where(Match.competition_id == pl.id)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
        ).all()
    )
    standings = _compute_standings(teams, matches)

    # "Top results" — finished matches between the top 6 teams (showcase fixtures).
    top6_ids = {s.team.id for s in standings[:6]}
    big_matches = [m for m in matches if m.home_team_id in top6_ids and m.away_team_id in top6_ids][
        -8:
    ]

    scorers = list(
        session.scalars(
            select(Scorer).where(Scorer.competition_id == pl.id).order_by(Scorer.goals.desc())
        ).all()
    )
    # Attach team objects to scorers for template convenience (no relationship defined).
    teams_by_id = {t.id: t for t in teams}
    for sc in scorers:
        sc.team_obj = teams_by_id.get(sc.team_id) if sc.team_id else None  # type: ignore[attr-defined]

    return templates.TemplateResponse(
        request=request,
        name="premier_league.html",
        context={
            "competition": pl,
            "standings": standings,
            "matches_played": sum(s.played for s in standings) // 2,
            "big_matches": big_matches,
            "top_scorer": scorers[0] if scorers else None,
            "other_scorers": scorers[1:8],
        },
    )
