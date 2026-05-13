"""Premier League data, scraped from Wikipedia.

Wikipedia is the most stable free source for current PL data — standings and
top scorers are kept up-to-date on the season page. Player photos and team
crests come from the Wikipedia REST summary API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import StringIO

import httpx
import pandas as pd

log = logging.getLogger(__name__)

WIKI_BASE = "https://en.wikipedia.org/wiki"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
PL_SEASON_SLUG = "2025%E2%80%9326_Premier_League"
USER_AGENT = "footy-pet/0.1 (educational; +https://github.com/BitByteJR/footy)"

# Wikipedia article slug for each PL club. The plain club name doesn't always
# resolve cleanly (e.g. "Arsenal" is a disambig page), so we map explicitly.
TEAM_WIKI_SLUG: dict[str, str] = {
    "Arsenal": "Arsenal_F.C.",
    "Aston Villa": "Aston_Villa_F.C.",
    "Bournemouth": "AFC_Bournemouth",
    "Brentford": "Brentford_F.C.",
    "Brighton": "Brighton_%26_Hove_Albion_F.C.",
    "Brighton & Hove Albion": "Brighton_%26_Hove_Albion_F.C.",
    "Burnley": "Burnley_F.C.",
    "Chelsea": "Chelsea_F.C.",
    "Crystal Palace": "Crystal_Palace_F.C.",
    "Everton": "Everton_F.C.",
    "Fulham": "Fulham_F.C.",
    "Leeds": "Leeds_United_F.C.",
    "Leeds United": "Leeds_United_F.C.",
    "Liverpool": "Liverpool_F.C.",
    "Manchester City": "Manchester_City_F.C.",
    "Manchester United": "Manchester_United_F.C.",
    "Newcastle United": "Newcastle_United_F.C.",
    "Newcastle": "Newcastle_United_F.C.",
    "Nottingham Forest": "Nottingham_Forest_F.C.",
    "Sunderland": "Sunderland_A.F.C.",
    "Tottenham Hotspur": "Tottenham_Hotspur_F.C.",
    "Tottenham": "Tottenham_Hotspur_F.C.",
    "West Ham United": "West_Ham_United_F.C.",
    "West Ham": "West_Ham_United_F.C.",
    "Wolverhampton Wanderers": "Wolverhampton_Wanderers_F.C.",
    "Wolves": "Wolverhampton_Wanderers_F.C.",
}


@dataclass
class StandingRow:
    rank: int
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    gd: int
    points: int


@dataclass
class ScorerRow:
    rank: int
    player: str
    club: str
    goals: int


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=20.0,
        follow_redirects=True,
    )


def fetch_pl_html() -> str:
    with _client() as c:
        r = c.get(f"{WIKI_BASE}/{PL_SEASON_SLUG}")
        r.raise_for_status()
        return r.text


def _clean_col(name) -> str:
    """Lowercase a column name and strip Wikipedia footnote brackets like `Goals[122]`."""
    return re.sub(r"\[.*?\]", "", str(name)).strip().lower()


def _clean_team(name) -> str:
    """Strip qualification suffixes like '(Q)', '(Y)', '(R)' and footnote refs."""
    s = re.sub(r"\[.*?\]", "", str(name))
    s = re.sub(r"\([A-Z]{1,3}\)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_standings(html: str) -> list[StandingRow]:
    tables = pd.read_html(StringIO(html))
    for raw in tables:
        cols = {_clean_col(c) for c in raw.columns}
        if "team" in cols and ("pld" in cols or "played" in cols) and "pts" in cols:
            df = raw.rename(columns=_clean_col)
            rows: list[StandingRow] = []
            for i, r in df.iterrows():
                try:
                    rows.append(
                        StandingRow(
                            rank=_to_int(r.get("pos", i + 1)),
                            team=_clean_team(r["team"]),
                            played=_to_int(r.get("pld") or r.get("played")),
                            won=_to_int(r.get("w")),
                            drawn=_to_int(r.get("d")),
                            lost=_to_int(r.get("l")),
                            gf=_to_int(r.get("gf")),
                            ga=_to_int(r.get("ga")),
                            gd=_to_int(r.get("gd")),
                            points=_to_int(r.get("pts")),
                        )
                    )
                except (ValueError, KeyError, TypeError):
                    continue
            if rows:
                return rows
    return []


def parse_top_scorers(html: str) -> list[ScorerRow]:
    tables = pd.read_html(StringIO(html))
    for raw in tables:
        cols = {_clean_col(c) for c in raw.columns}
        if "player" in cols and "goals" in cols and ("club" in cols or "team" in cols):
            df = raw.rename(columns=_clean_col)
            rows: list[ScorerRow] = []
            for i, r in df.iterrows():
                try:
                    rows.append(
                        ScorerRow(
                            rank=_to_int(r.get("rank", i + 1)),
                            player=re.sub(r"\s+", " ", str(r["player"])).strip(),
                            club=_clean_team(r.get("club") or r.get("team", "")),
                            goals=_to_int(r["goals"]),
                        )
                    )
                except (ValueError, KeyError, TypeError):
                    continue
            if rows:
                return rows
    return []


def parse_results_matrix(html: str) -> list[dict]:
    """Extract played matches from Wikipedia's home/away results matrix.

    Cells contain e.g. '1–2' for played, '—' or blank for not-yet-played.
    Column headers are 3-letter team codes (ARS, AVL...). Row labels are full
    team names (the matrix is square).
    """
    tables = pd.read_html(StringIO(html))
    for raw in tables:
        cols = [_clean_col(c) for c in raw.columns]
        if not cols or "home \\ away" not in cols[0]:
            continue
        # First column is the row label (home team), rest are away teams by TLA.
        df = raw.copy()
        df.columns = [str(c).strip() for c in df.columns]
        first_col = df.columns[0]
        away_tlas = df.columns[1:]
        # Need TLA → full name map. Use the first column values (which are full names)
        # in row order — but TLAs in columns are in alphabetical order, not
        # necessarily aligned. Build map from any pair we encounter where row team
        # is known by first 3 chars.
        # Simpler: derive TLA from row name (first 3 alpha chars uppercased) and
        # compare with column TLAs.
        rows_full = [str(v).strip() for v in df[first_col]]
        tla_to_name = {}
        for full in rows_full:
            tla_guess = re.sub(r"[^A-Za-z]", "", full)[:3].upper()
            tla_to_name[tla_guess] = full
        # Augment with known TLAs that don't derive cleanly
        manual_tla = {
            "ARS": "Arsenal",
            "AVL": "Aston Villa",
            "BOU": "Bournemouth",
            "BRE": "Brentford",
            "BHA": "Brighton & Hove Albion",
            "BUR": "Burnley",
            "CHE": "Chelsea",
            "CRY": "Crystal Palace",
            "EVE": "Everton",
            "FUL": "Fulham",
            "LEE": "Leeds United",
            "LEI": "Leicester City",
            "LIV": "Liverpool",
            "MCI": "Manchester City",
            "MUN": "Manchester United",
            "NEW": "Newcastle United",
            "NFO": "Nottingham Forest",
            "SOU": "Southampton",
            "SUN": "Sunderland",
            "TOT": "Tottenham Hotspur",
            "WHU": "West Ham United",
            "WOL": "Wolverhampton Wanderers",
            "IPS": "Ipswich Town",
        }
        matches: list[dict] = []
        for i, full_home in enumerate(rows_full):
            for tla in away_tlas:
                cell = df.iloc[i][tla]
                if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                    continue
                text = str(cell).strip()
                m = re.match(r"^\s*(\d+)\s*[–-]\s*(\d+)\s*$", text)
                if not m:
                    continue
                full_away = manual_tla.get(str(tla).upper(), str(tla).upper())
                matches.append(
                    {
                        "home": full_home,
                        "away": full_away,
                        "home_score": int(m.group(1)),
                        "away_score": int(m.group(2)),
                        "status": "FINISHED",
                    }
                )
        return matches
    return []


def _summary(slug: str) -> dict | None:
    """Wikipedia REST summary — returns the page's thumbnail and short blurb."""
    try:
        with _client() as c:
            r = c.get(f"{WIKI_REST}/{slug}")
            if r.status_code != 200:
                return None
            return r.json()
    except httpx.HTTPError:
        return None


def fetch_team_crest(team_name: str) -> str | None:
    slug = TEAM_WIKI_SLUG.get(team_name.strip())
    if not slug:
        return None
    data = _summary(slug)
    if not data:
        return None
    # `originalimage` for highest-res crest if available, fall back to thumbnail
    img = data.get("originalimage") or data.get("thumbnail") or {}
    return img.get("source")


def fetch_player_photo(player_name: str) -> str | None:
    slug = player_name.strip().replace(" ", "_")
    data = _summary(slug)
    if not data:
        return None
    img = data.get("thumbnail") or data.get("originalimage") or {}
    return img.get("source")


def _derive_tla(name: str) -> str:
    """Best-effort 3-letter abbreviation from a club name."""
    manual = {
        "Arsenal": "ARS",
        "Aston Villa": "AVL",
        "Bournemouth": "BOU",
        "Brentford": "BRE",
        "Brighton & Hove Albion": "BHA",
        "Brighton": "BHA",
        "Burnley": "BUR",
        "Chelsea": "CHE",
        "Crystal Palace": "CRY",
        "Everton": "EVE",
        "Fulham": "FUL",
        "Leeds United": "LEE",
        "Leeds": "LEE",
        "Liverpool": "LIV",
        "Manchester City": "MCI",
        "Manchester United": "MUN",
        "Newcastle United": "NEW",
        "Newcastle": "NEW",
        "Nottingham Forest": "NFO",
        "Sunderland": "SUN",
        "Tottenham Hotspur": "TOT",
        "Tottenham": "TOT",
        "West Ham United": "WHU",
        "West Ham": "WHU",
        "Wolverhampton Wanderers": "WOL",
        "Wolves": "WOL",
    }
    if name in manual:
        return manual[name]
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][:2]).upper()
    return name[:3].upper()


def sync_pl(session) -> dict[str, int]:
    """Scrape Wikipedia's 2025-26 Premier League page and upsert into the DB.

    Requires the Premier League competition row to already exist (run
    `uv run footy` once to sync competitions from football-data.org).
    """
    from sqlalchemy import delete, select

    from footy.models import Competition, Match, Scorer, Team

    html = fetch_pl_html()

    pl = session.scalar(select(Competition).where(Competition.code == "PL"))
    if pl is None:
        raise RuntimeError("Premier League not in competitions table. Run `uv run footy` first.")

    # 1. Teams from standings (and crests from Wikipedia REST)
    standings = parse_standings(html)
    teams_by_name: dict[str, Team] = {}
    for s in standings:
        team = session.scalar(select(Team).where(Team.name == s.team))
        if team is None:
            team = Team(name=s.team, competition_id=pl.id)
            session.add(team)
        if not team.crest_url:
            team.crest_url = fetch_team_crest(s.team)
        if not team.tla:
            team.tla = _derive_tla(s.team)
        teams_by_name[s.team] = team
    session.flush()

    # 2. Matches (wipe + reinsert this season — small dataset, simplest)
    session.execute(delete(Match).where(Match.competition_id == pl.id))
    session.flush()
    matches = parse_results_matrix(html)
    saved_matches = 0
    for m in matches:
        home = teams_by_name.get(m["home"])
        away = teams_by_name.get(m["away"])
        if home is None or away is None:
            continue
        session.add(
            Match(
                competition_id=pl.id,
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=m["home_score"],
                away_score=m["away_score"],
                status="FINISHED",
            )
        )
        saved_matches += 1

    # 3. Top scorers (with player photos)
    session.execute(delete(Scorer).where(Scorer.competition_id == pl.id))
    session.flush()
    scorers = parse_top_scorers(html)
    for sc in scorers:
        first_club = sc.club.split("/")[0].strip()
        team = teams_by_name.get(first_club)
        if team is None:
            team = session.scalar(select(Team).where(Team.name == first_club))
        session.add(
            Scorer(
                competition_id=pl.id,
                player_name=sc.player,
                photo_url=fetch_player_photo(sc.player),
                team_id=team.id if team else None,
                goals=sc.goals,
                season="2025-26",
            )
        )

    session.commit()
    return {
        "teams": len(standings),
        "matches": saved_matches,
        "scorers": len(scorers),
    }


def _to_int(value) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    s = re.sub(r"[^\d\-+]", "", str(value).replace("−", "-"))
    if not s or s in {"-", "+"}:
        return 0
    try:
        return int(s)
    except ValueError:
        return 0
