"""football-data.org v4 API client.

Free-tier limits: 10 requests/min, with `X-Auth-Token` header. We pace
requests at ≥7s apart to stay safely under, and back off on 429.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from footy.config import get_settings

log = logging.getLogger(__name__)

API_BASE = "https://api.football-data.org/v4"

# Free-tier competitions we care about — top 5 leagues + Champions League.
TOP_LEAGUES: tuple[str, ...] = ("CL", "PL", "PD", "BL1", "SA", "FL1")

# League → fan-facing display colours (used by the league hero strip).
LEAGUE_COLOR: dict[str, str] = {
    "PL": "#38003c",  # Premier League purple
    "PD": "#ee2737",  # La Liga red
    "BL1": "#d20515",  # Bundesliga red
    "SA": "#00733e",  # Serie A green
    "FL1": "#091c3e",  # Ligue 1 navy
    "CL": "#0a3380",  # Champions League blue
}

# Pace control. Free tier is 10/min, so 7s is comfortable (≈8.5/min).
_MIN_GAP_SEC = 7.0
_last_call_at: float = 0.0


def _token() -> str:
    token = (get_settings().football_data_token or "").strip()
    if not token:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN missing. Set it in .env "
            "(get a free token at football-data.org/client/register)."
        )
    return token


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"X-Auth-Token": _token(), "User-Agent": "footy-pet/0.1"},
        timeout=20.0,
    )


def _pace() -> None:
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    if elapsed < _MIN_GAP_SEC:
        time.sleep(_MIN_GAP_SEC - elapsed)
    _last_call_at = time.monotonic()


def _get(c: httpx.Client, path: str, params: dict | None = None) -> dict[str, Any]:
    for attempt in range(3):
        _pace()
        r = c.get(path, params=params)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "30"))
            log.warning("fdo 429 on %s — backing off %ss (attempt %s)", path, wait, attempt + 1)
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def fetch_competition(code: str) -> dict[str, Any]:
    with _client() as c:
        return _get(c, f"/competitions/{code}")


def fetch_standings(code: str) -> dict[str, Any]:
    with _client() as c:
        return _get(c, f"/competitions/{code}/standings")


def fetch_matches(
    code: str,
    status: str | None = None,
    matchday: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if matchday is not None:
        params["matchday"] = matchday
    with _client() as c:
        return _get(c, f"/competitions/{code}/matches", params=params or None)


def fetch_scorers(code: str, limit: int = 10) -> dict[str, Any]:
    with _client() as c:
        return _get(c, f"/competitions/{code}/scorers", params={"limit": limit})


def fetch_match(match_id: int) -> dict[str, Any]:
    """Per-match detail — includes `goals` and `bookings` (cards)."""
    with _client() as c:
        return _get(c, f"/matches/{match_id}")
