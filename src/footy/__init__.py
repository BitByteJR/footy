"""CLI entry for footy."""

from footy.db import session_factory
from footy.parser import sync_competitions


def main() -> None:
    """Sync competitions from the configured source into the DB."""
    print("footy: syncing competitions...")
    with session_factory()() as session:
        count = sync_competitions(session)
    print(f"footy: synced {count} competitions")
