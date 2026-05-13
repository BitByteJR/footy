"""Football data ingestion.

The HTTP fetcher targets football-data.org's free competitions endpoint.
Without an API token requests are rate-limited; with a token (set
FOOTBALL_DATA_TOKEN in .env) limits are higher.

The `sync_competitions` core takes any fetch callable, which keeps unit
tests offline — see tests/test_parser.py.
"""

from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session

from footy.config import get_settings
from footy.models import Competition

CompetitionDict = dict[str, Any]
FetchFn = Callable[[], list[CompetitionDict]]


def fetch_competitions_http() -> list[CompetitionDict]:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.football_data_token:
        headers["X-Auth-Token"] = settings.football_data_token
    response = httpx.get(
        f"{settings.football_data_url}/competitions",
        headers=headers,
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json().get("competitions", [])


def sync_competitions(
    session: Session,
    fetch: FetchFn = fetch_competitions_http,
) -> int:
    """Upsert competitions from the fetch source. Returns count synced."""
    items = fetch()
    for item in items:
        comp = session.get(Competition, item["id"])
        area_name = (item.get("area") or {}).get("name", "")
        if comp is None:
            session.add(
                Competition(
                    id=item["id"],
                    code=item.get("code") or None,
                    name=item["name"],
                    area_name=area_name,
                )
            )
        else:
            comp.code = item.get("code") or None
            comp.name = item["name"]
            comp.area_name = area_name
    session.commit()
    return len(items)
