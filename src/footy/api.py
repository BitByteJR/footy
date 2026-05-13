"""FastAPI application — bookmaker-style football data UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from footy.db import get_session
from footy.fdo import LEAGUE_COLOR, TOP_LEAGUES
from footy.models import Competition, Goal, Match, Scorer, Standing, Team
from footy.sync import sync_match_detail

app = FastAPI(title="footy", version="0.2.0")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["LEAGUE_COLOR"] = LEAGUE_COLOR


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/competitions")
def list_competitions(
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, str | int | None]]:
    rows = session.scalars(select(Competition).order_by(Competition.code)).all()
    return [{"id": c.id, "code": c.code, "name": c.name, "area": c.area_name} for c in rows]


# ─── helpers ────────────────────────────────────────────────────────────────


@dataclass
class MatchGroup:
    """Matches grouped for the index/league feed."""

    label: str  # e.g. "Сегодня, 13 мая" or "Завтра"
    date_key: str  # "2026-05-13"
    competition: Competition
    matches: list[Match]


RU_WEEKDAY = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
RU_MONTH = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def ru_date_label(d: datetime) -> str:
    today = datetime.now(UTC).date()
    target = d.date()
    if target == today:
        return f"Сегодня · {target.day} {RU_MONTH[target.month]}"
    if target == today + timedelta(days=1):
        return f"Завтра · {target.day} {RU_MONTH[target.month]}"
    if target == today - timedelta(days=1):
        return f"Вчера · {target.day} {RU_MONTH[target.month]}"
    return f"{RU_WEEKDAY[target.weekday()]} · {target.day} {RU_MONTH[target.month]}"


templates.env.filters["ru_date"] = ru_date_label


def ru_time(d: datetime | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%H:%M")


templates.env.filters["ru_time"] = ru_time


def _top_competitions(session: Session) -> list[Competition]:
    """Return the top leagues in our preferred display order."""
    by_code = {c.code: c for c in session.scalars(select(Competition)).all() if c.code}
    return [by_code[c] for c in TOP_LEAGUES if c in by_code]


def _leagues_summary(session: Session) -> list[dict]:
    """For the sidebar list — top leagues with current matchday + colour."""
    out = []
    for c in _top_competitions(session):
        out.append(
            {
                "code": c.code,
                "name": c.name,
                "matchday": c.current_matchday,
                "color": LEAGUE_COLOR.get(c.code or "", "#1a1f29"),
                "emblem_url": c.emblem_url,
            }
        )
    return out


# ─── routes ─────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    leagues = _top_competitions(session)
    league_ids = [c.id for c in leagues]

    now = datetime.now(UTC)
    horizon = now + timedelta(days=14)

    upcoming = list(
        session.scalars(
            select(Match)
            .where(
                Match.competition_id.in_(league_ids),
                Match.status.in_(("SCHEDULED", "TIMED", "POSTPONED")),
                Match.utc_date.is_not(None),
                Match.utc_date <= horizon,
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date)
            .limit(60)
        ).all()
    )

    recent = list(
        session.scalars(
            select(Match)
            .where(
                Match.competition_id.in_(league_ids),
                Match.status == "FINISHED",
                Match.utc_date.is_not(None),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date.desc())
            .limit(10)
        ).all()
    )

    # Top 4 featured — pick a mix of leagues if possible.
    featured: list[Match] = []
    used_codes: set[str] = set()
    for m in upcoming:
        code = next(c.code for c in leagues if c.id == m.competition_id)
        if code not in used_codes:
            featured.append(m)
            used_codes.add(code)
        if len(featured) >= 4:
            break
    if len(featured) < 4:
        for m in upcoming:
            if m in featured:
                continue
            featured.append(m)
            if len(featured) >= 4:
                break

    # Group upcoming by (date, competition) for the feed.
    groups: list[MatchGroup] = []
    by_key: dict[tuple[str, int], MatchGroup] = {}
    comp_by_id = {c.id: c for c in leagues}
    for m in upcoming:
        if m in featured:
            continue
        date_key = m.utc_date.strftime("%Y-%m-%d") if m.utc_date else "tba"
        key = (date_key, m.competition_id)
        if key not in by_key:
            grp = MatchGroup(
                label=ru_date_label(m.utc_date) if m.utc_date else "Дата уточняется",
                date_key=date_key,
                competition=comp_by_id[m.competition_id],
                matches=[],
            )
            by_key[key] = grp
            groups.append(grp)
        by_key[key].matches.append(m)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "leagues_sidebar": _leagues_summary(session),
            "featured": featured,
            "groups": groups,
            "recent": recent,
            "league_color": LEAGUE_COLOR,
        },
    )


@app.get("/league/{code}", response_class=HTMLResponse)
def league_page(
    code: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    tab: str = "matches",
) -> HTMLResponse:
    comp = session.scalar(select(Competition).where(Competition.code == code.upper()))
    if comp is None:
        raise HTTPException(status_code=404, detail=f"Competition {code} not synced")

    standings = list(
        session.scalars(
            select(Standing)
            .where(Standing.competition_id == comp.id)
            .options(selectinload(Standing.team))
            .order_by(Standing.position)
        ).all()
    )

    now = datetime.now(UTC)
    upcoming = list(
        session.scalars(
            select(Match)
            .where(
                Match.competition_id == comp.id,
                Match.utc_date.is_not(None),
                Match.utc_date >= now,
                Match.status != "FINISHED",
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date)
            .limit(20)
        ).all()
    )

    recent = list(
        session.scalars(
            select(Match)
            .where(
                Match.competition_id == comp.id,
                Match.status == "FINISHED",
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date.desc())
            .limit(15)
        ).all()
    )

    last_match = recent[0] if recent else None
    last_match_goals: list[Goal] = []
    if last_match is not None:
        # Lazy-fetch detail for the very latest match (cheap, single API call).
        if not last_match.detail_fetched:
            try:
                sync_match_detail(session, last_match.id)
                # refresh from DB
                last_match = session.get(Match, last_match.id) or last_match
            except Exception:
                pass
        last_match_goals = list(
            session.scalars(
                select(Goal).where(Goal.match_id == last_match.id).order_by(Goal.minute)
            ).all()
        )

    scorers = list(
        session.scalars(
            select(Scorer)
            .where(Scorer.competition_id == comp.id)
            .order_by(Scorer.goals.desc())
            .limit(10)
        ).all()
    )
    teams_by_id = {
        t.id: t for t in session.scalars(select(Team).where(Team.competition_id == comp.id)).all()
    }
    for sc in scorers:
        sc.team_obj = teams_by_id.get(sc.team_id) if sc.team_id else None  # type: ignore[attr-defined]

    return templates.TemplateResponse(
        request=request,
        name="league.html",
        context={
            "leagues_sidebar": _leagues_summary(session),
            "competition": comp,
            "color": LEAGUE_COLOR.get(comp.code or "", "#1a1f29"),
            "tab": tab,
            "standings": standings,
            "upcoming": upcoming,
            "recent": recent,
            "last_match": last_match,
            "last_match_goals": last_match_goals,
            "scorers": scorers,
        },
    )


@app.get("/match/{match_id}", response_class=HTMLResponse)
def match_page(
    match_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    match = session.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.home_team),
            selectinload(Match.away_team),
            selectinload(Match.goals),
            selectinload(Match.bookings),
        )
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    if not match.detail_fetched:
        try:
            sync_match_detail(session, match.id)
            match = (
                session.scalar(
                    select(Match)
                    .where(Match.id == match_id)
                    .options(
                        selectinload(Match.home_team),
                        selectinload(Match.away_team),
                        selectinload(Match.goals),
                        selectinload(Match.bookings),
                    )
                )
                or match
            )
        except Exception:
            pass

    comp = session.get(Competition, match.competition_id)

    # Form: last 5 finished matches for each team
    home_form = _team_form(session, match.home_team_id, match.competition_id)
    away_form = _team_form(session, match.away_team_id, match.competition_id)

    # Head-to-head
    h2h = list(
        session.scalars(
            select(Match)
            .where(
                Match.status == "FINISHED",
                (
                    (Match.home_team_id == match.home_team_id)
                    & (Match.away_team_id == match.away_team_id)
                )
                | (
                    (Match.home_team_id == match.away_team_id)
                    & (Match.away_team_id == match.home_team_id)
                ),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date.desc())
            .limit(8)
        ).all()
    )

    # Standings position for both teams
    home_standing = session.scalar(
        select(Standing).where(
            Standing.competition_id == match.competition_id,
            Standing.team_id == match.home_team_id,
        )
    )
    away_standing = session.scalar(
        select(Standing).where(
            Standing.competition_id == match.competition_id,
            Standing.team_id == match.away_team_id,
        )
    )

    return templates.TemplateResponse(
        request=request,
        name="match.html",
        context={
            "leagues_sidebar": _leagues_summary(session),
            "match": match,
            "competition": comp,
            "color": LEAGUE_COLOR.get(comp.code or "", "#1a1f29") if comp else "#1a1f29",
            "home_form": home_form,
            "away_form": away_form,
            "h2h": h2h,
            "home_standing": home_standing,
            "away_standing": away_standing,
        },
    )


@dataclass
class FormResult:
    outcome: str  # "W" / "D" / "L"
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
                (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
            )
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .order_by(Match.utc_date.desc())
            .limit(limit)
        ).all()
    )
    out: list[FormResult] = []
    for m in rows:
        if m.home_team_id == team_id:
            gf, ga, opp = m.home_score or 0, m.away_score or 0, m.away_team
        else:
            gf, ga, opp = m.away_score or 0, m.home_score or 0, m.home_team
        outcome = "W" if gf > ga else ("L" if gf < ga else "D")
        out.append(FormResult(outcome=outcome, gf=gf, ga=ga, opp=opp, match=m))
    return list(reversed(out))
