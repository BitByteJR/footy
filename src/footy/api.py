"""FastAPI application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, select
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
    """Derive standings from FINISHED matches. PL: 3pts win / 1 draw / 0 loss."""
    stats: dict[int, dict] = {
        t.id: {"team": t, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for t in teams
    }
    for m in matches:
        if m.status != "FINISHED" or m.home_score is None or m.away_score is None:
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


def _attach_team_to_scorers(scorers: list[Scorer], teams_by_id: dict[int, Team]) -> None:
    """Add a `team_obj` attribute to each scorer for template convenience."""
    for sc in scorers:
        sc.team_obj = teams_by_id.get(sc.team_id) if sc.team_id else None  # type: ignore[attr-defined]


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
    teams_by_id = {t.id: t for t in teams}

    matches = list(
        session.scalars(
            select(Match)
            .where(Match.competition_id == pl.id)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
        ).all()
    )
    standings = _compute_standings(teams, matches)

    # "Top results" — finished matches between the top 6 teams.
    top6_ids = {s.team.id for s in standings[:6]}
    big_matches = [
        m
        for m in matches
        if m.status == "FINISHED" and m.home_team_id in top6_ids and m.away_team_id in top6_ids
    ][-8:]

    # Upcoming — scheduled matches involving top-12 teams (showcase fixtures first),
    # falling back to any remaining scheduled if there aren't 8 from the top.
    top12_ids = {s.team.id for s in standings[:12]}
    scheduled = [m for m in matches if m.status == "SCHEDULED"]
    upcoming_priority = [
        m for m in scheduled if m.home_team_id in top12_ids and m.away_team_id in top12_ids
    ]
    upcoming_rest = [m for m in scheduled if m not in upcoming_priority]
    upcoming_matches = (upcoming_priority + upcoming_rest)[:8]

    scorers = list(
        session.scalars(
            select(Scorer).where(Scorer.competition_id == pl.id).order_by(Scorer.goals.desc())
        ).all()
    )
    _attach_team_to_scorers(scorers, teams_by_id)

    return templates.TemplateResponse(
        request=request,
        name="premier_league.html",
        context={
            "competition": pl,
            "standings": standings,
            "matches_played": sum(s.played for s in standings) // 2,
            "matches_scheduled": len(scheduled),
            "big_matches": big_matches,
            "upcoming_matches": upcoming_matches,
            "top_scorer": scorers[0] if scorers else None,
            "other_scorers": scorers[1:8],
        },
    )


@dataclass
class FormResult:
    outcome: str  # "W" | "D" | "L"
    gf: int
    ga: int
    opp: Team
    match: Match


def _team_form(
    session: Session, team_id: int, competition_id: int, limit: int = 5
) -> list[FormResult]:
    rows = list(
        session.scalars(
            select(Match)
            .where(
                Match.competition_id == competition_id,
                Match.status == "FINISHED",
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.id.desc())
            .limit(limit)
        ).all()
    )
    out: list[FormResult] = []
    for m in rows:
        if m.home_team_id == team_id:
            gf, ga, opp = m.home_score, m.away_score, m.away_team
        else:
            gf, ga, opp = m.away_score, m.home_score, m.home_team
        outcome = "W" if gf > ga else ("L" if gf < ga else "D")
        out.append(FormResult(outcome=outcome, gf=gf or 0, ga=ga or 0, opp=opp, match=m))
    return list(reversed(out))  # oldest → newest


@app.get("/match/{match_id}", response_class=HTMLResponse)
def match_detail(
    request: Request,
    match_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    match = session.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    home_form = _team_form(session, match.home_team_id, match.competition_id)
    away_form = _team_form(session, match.away_team_id, match.competition_id)

    h2h = list(
        session.scalars(
            select(Match)
            .where(
                Match.status == "FINISHED",
                or_(
                    and_(
                        Match.home_team_id == match.home_team_id,
                        Match.away_team_id == match.away_team_id,
                    ),
                    and_(
                        Match.home_team_id == match.away_team_id,
                        Match.away_team_id == match.home_team_id,
                    ),
                ),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.id.desc())
        ).all()
    )

    # Team-specific scorers (only those in the competition-wide top scorers table).
    teams = list(
        session.scalars(select(Team).where(Team.competition_id == match.competition_id)).all()
    )
    teams_by_id = {t.id: t for t in teams}
    scorers_home = list(
        session.scalars(
            select(Scorer).where(Scorer.team_id == match.home_team_id).order_by(Scorer.goals.desc())
        ).all()
    )
    scorers_away = list(
        session.scalars(
            select(Scorer).where(Scorer.team_id == match.away_team_id).order_by(Scorer.goals.desc())
        ).all()
    )
    _attach_team_to_scorers(scorers_home + scorers_away, teams_by_id)

    # Head-to-head aggregate
    home_wins = sum(
        1
        for m in h2h
        if (m.home_team_id == match.home_team_id and (m.home_score or 0) > (m.away_score or 0))
        or (m.away_team_id == match.home_team_id and (m.away_score or 0) > (m.home_score or 0))
    )
    away_wins = sum(
        1
        for m in h2h
        if (m.home_team_id == match.away_team_id and (m.home_score or 0) > (m.away_score or 0))
        or (m.away_team_id == match.away_team_id and (m.away_score or 0) > (m.home_score or 0))
    )
    draws = len(h2h) - home_wins - away_wins

    return templates.TemplateResponse(
        request=request,
        name="match_detail.html",
        context={
            "match": match,
            "home_form": home_form,
            "away_form": away_form,
            "h2h": h2h,
            "h2h_home_wins": home_wins,
            "h2h_away_wins": away_wins,
            "h2h_draws": draws,
            "scorers_home": scorers_home,
            "scorers_away": scorers_away,
        },
    )
