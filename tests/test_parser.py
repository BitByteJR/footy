from sqlalchemy import select
from sqlalchemy.orm import Session

from footy.models import Competition
from footy.parser import sync_competitions


def test_sync_competitions_inserts_new(session: Session) -> None:
    fake = [
        {"id": 2021, "code": "PL", "name": "Premier League", "area": {"name": "England"}},
        {"id": 2014, "code": "PD", "name": "La Liga", "area": {"name": "Spain"}},
    ]
    n = sync_competitions(session, fetch=lambda: fake)

    assert n == 2
    rows = session.scalars(select(Competition)).all()
    assert {c.code for c in rows} == {"PL", "PD"}


def test_sync_competitions_updates_existing(session: Session) -> None:
    session.add(Competition(id=2021, code="OLD", name="Old name", area_name="??"))
    session.commit()

    fake = [{"id": 2021, "code": "PL", "name": "Premier League", "area": {"name": "England"}}]
    sync_competitions(session, fetch=lambda: fake)

    comp = session.get(Competition, 2021)
    assert comp is not None
    assert comp.code == "PL"
    assert comp.name == "Premier League"
    assert comp.area_name == "England"
