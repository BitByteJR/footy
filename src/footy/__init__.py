"""CLI entry for footy."""

import sys

from footy.db import session_factory
from footy.sync import sync_match_detail, sync_top_leagues


def main() -> None:
    """
    Usage:
      uv run footy                     full sync of top leagues (CL, PL, PD, BL1, SA, FL1)
      uv run footy match <match_id>    fetch one match's detail (goals, cards)
    """
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "match":
        match_id = int(args[1])
        with session_factory()() as session:
            m = sync_match_detail(session, match_id)
        print(f"footy: synced match {m.id} ({len(m.goals)} goals, {len(m.bookings)} cards)")
        return

    print("footy: syncing top leagues (this takes ~3-5 min on free tier)")
    with session_factory()() as session:
        out = sync_top_leagues(session)
    print("footy: done", out)
