from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from footy.models import Competition


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_competitions_empty(client: TestClient) -> None:
    r = client.get("/competitions")
    assert r.status_code == 200
    assert r.json() == []


def test_list_competitions_with_data(client: TestClient, session: Session) -> None:
    session.add_all(
        [
            Competition(id=2021, code="PL", name="Premier League", area_name="England"),
            Competition(id=2014, code="PD", name="La Liga", area_name="Spain"),
        ]
    )
    session.commit()

    r = client.get("/competitions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert {c["code"] for c in data} == {"PL", "PD"}
