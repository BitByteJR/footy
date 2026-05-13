"""Sync football-data.org → local Postgres."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from footy import fdo
from footy.models import (
    Booking,
    Competition,
    Goal,
    Match,
    Scorer,
    Standing,
    Team,
)

log = logging.getLogger(__name__)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # API returns "2026-05-17T14:00:00Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _upsert_competition(
    session: Session,
    data: dict[str, Any],
    season: dict[str, Any] | None = None,
) -> Competition:
    """Upsert. `season` (from /standings) has `currentMatchday`."""
    comp = session.get(Competition, data["id"])
    if comp is None:
        comp = Competition(id=data["id"])
        session.add(comp)
    comp.code = data.get("code")
    comp.name = data["name"]
    comp.area_name = (data.get("area") or {}).get("name", "")
    comp.emblem_url = data.get("emblem")
    # currentMatchday lives on the `season` envelope from /standings, not on
    # competition itself.
    current_md = None
    if season:
        current_md = season.get("currentMatchday")
    if current_md is None:
        current_md = (data.get("currentSeason") or {}).get("currentMatchday")
    if current_md is not None:
        comp.current_matchday = current_md
    return comp


def _upsert_team(session: Session, data: dict[str, Any], competition_id: int) -> Team:
    team = session.get(Team, data["id"])
    if team is None:
        team = Team(id=data["id"])
        session.add(team)
    team.name = data.get("name") or team.name or "?"
    team.short_name = data.get("shortName")
    team.tla = data.get("tla")
    team.crest_url = data.get("crest")
    team.competition_id = competition_id
    return team


def _upsert_match(session: Session, data: dict[str, Any], competition_id: int) -> Match:
    match = session.get(Match, data["id"])
    if match is None:
        match = Match(id=data["id"], competition_id=competition_id, status="SCHEDULED")
        session.add(match)
    match.competition_id = competition_id
    match.matchday = data.get("matchday")
    match.utc_date = _parse_dt(data.get("utcDate"))
    match.status = data.get("status") or "SCHEDULED"
    score = data.get("score") or {}
    full = score.get("fullTime") or {}
    match.home_score = full.get("home")
    match.away_score = full.get("away")
    match.winner = score.get("winner")
    match.venue = data.get("venue")
    match.referee = (data.get("referees") or [{}])[0].get("name") if data.get("referees") else None
    home, away = data["homeTeam"], data["awayTeam"]
    match.home_team_id = home["id"]
    match.away_team_id = away["id"]
    return match


def sync_competition(session: Session, code: str) -> dict[str, int]:
    """Pull standings, all matches, and top scorers for one competition."""
    counts = {"teams": 0, "matches": 0, "scorers": 0, "standings": 0}

    # 1. Standings call also gives us full team roster.
    standings_data = fdo.fetch_standings(code)
    comp_data = standings_data["competition"]
    comp = _upsert_competition(session, comp_data, season=standings_data.get("season"))
    session.flush()  # comp.id available

    # Standings: first item of "standings" array is the TOTAL table.
    total = next(
        (s for s in standings_data.get("standings", []) if s.get("type") == "TOTAL"),
        (standings_data.get("standings") or [{}])[0],
    )
    table = total.get("table") or []

    # Reset prior standings for this competition; we replace rather than diff.
    session.execute(delete(Standing).where(Standing.competition_id == comp.id))
    session.flush()

    for row in table:
        team = _upsert_team(session, row["team"], comp.id)
        counts["teams"] += 1
        session.flush()
        session.add(
            Standing(
                competition_id=comp.id,
                team_id=team.id,
                position=row["position"],
                played=row["playedGames"],
                won=row["won"],
                drawn=row["draw"],
                lost=row["lost"],
                goals_for=row["goalsFor"],
                goals_against=row["goalsAgainst"],
                goal_difference=row["goalDifference"],
                points=row["points"],
                form=row.get("form"),
            )
        )
        counts["standings"] += 1

    # 2. Matches (all statuses).
    matches_data = fdo.fetch_matches(code)
    for m in matches_data.get("matches", []):
        # Ensure both teams exist (in case matches API names a team standings missed).
        for side in (m["homeTeam"], m["awayTeam"]):
            if side.get("id") and session.get(Team, side["id"]) is None:
                _upsert_team(session, side, comp.id)
        session.flush()
        _upsert_match(session, m, comp.id)
        counts["matches"] += 1
    session.flush()

    # 3. Top scorers.
    scorers_data = fdo.fetch_scorers(code, limit=10)
    session.execute(delete(Scorer).where(Scorer.competition_id == comp.id))
    session.flush()
    season = (scorers_data.get("season") or {}).get("startDate", "")[:4]
    for s in scorers_data.get("scorers", []):
        team_id = (s.get("team") or {}).get("id")
        if team_id and session.get(Team, team_id) is None:
            _upsert_team(session, s["team"], comp.id)
            session.flush()
        session.add(
            Scorer(
                competition_id=comp.id,
                player_name=s["player"]["name"],
                team_id=team_id,
                goals=s.get("goals") or 0,
                assists=s.get("assists"),
                penalties=s.get("penalties"),
                matches_played=s.get("playedMatches"),
                season=f"{season}-{int(season) + 1}" if season.isdigit() else None,
            )
        )
        counts["scorers"] += 1

    session.commit()
    return counts


def sync_top_leagues(session: Session) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for code in fdo.TOP_LEAGUES:
        log.info("syncing %s", code)
        print(f"  ⇣ {code} ", end="", flush=True)
        try:
            out[code] = sync_competition(session, code)
            print(f"→ {out[code]}", flush=True)
        except Exception as exc:
            print(f"× {exc}", flush=True)
            out[code] = {"error": str(exc)}  # type: ignore[dict-item]
    return out


def sync_match_detail(session: Session, match_id: int) -> Match:
    """Fetch /matches/{id} and upsert goals + bookings for it."""
    data = fdo.fetch_match(match_id)
    comp_id = data["competition"]["id"]
    # Make sure competition + teams exist
    if session.get(Competition, comp_id) is None:
        _upsert_competition(session, data["competition"])
    for side in (data["homeTeam"], data["awayTeam"]):
        if side.get("id") and session.get(Team, side["id"]) is None:
            _upsert_team(session, side, comp_id)
    session.flush()
    match = _upsert_match(session, data, comp_id)
    match.detail_fetched = True

    session.execute(delete(Goal).where(Goal.match_id == match.id))
    session.execute(delete(Booking).where(Booking.match_id == match.id))
    session.flush()

    for g in data.get("goals", []) or []:
        score = g.get("score") or {}
        session.add(
            Goal(
                match_id=match.id,
                minute=g.get("minute"),
                injury_time=g.get("injuryTime"),
                player_name=(g.get("scorer") or {}).get("name") or "?",
                team_id=(g.get("team") or {}).get("id"),
                goal_type=g.get("type"),
                home_score=score.get("home"),
                away_score=score.get("away"),
            )
        )
    for b in data.get("bookings", []) or []:
        session.add(
            Booking(
                match_id=match.id,
                minute=b.get("minute"),
                player_name=(b.get("player") or {}).get("name") or "?",
                team_id=(b.get("team") or {}).get("id"),
                card=b.get("card") or "YELLOW",
            )
        )
    session.commit()
    return match
