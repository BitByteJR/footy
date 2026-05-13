"""CLI entry for footy."""

import sys

from footy.db import session_factory
from footy.parser import sync_competitions
from footy.wiki import sync_pl


def main() -> None:
    """Entry point.

    Usage:
      uv run footy            sync the worldwide competitions list (football-data.org)
      uv run footy pl         scrape the 2025-26 Premier League page on Wikipedia
                              (standings, results, top scorers, team crests, player photos)
    """
    if len(sys.argv) > 1 and sys.argv[1] == "pl":
        print("footy: scraping Premier League from Wikipedia...")
        with session_factory()() as session:
            counts = sync_pl(session)
        print(
            "footy: synced "
            f"{counts['teams']} teams, "
            f"{counts['matches']} matches, "
            f"{counts['scorers']} scorers"
        )
        return

    print("footy: syncing competitions...")
    with session_factory()() as session:
        count = sync_competitions(session)
    print(f"footy: synced {count} competitions")
