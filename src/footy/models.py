"""ORM models."""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from footy.db import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(100))
    area_name: Mapped[str] = mapped_column(String(100))

    teams: Mapped[list["Team"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    short_name: Mapped[str | None] = mapped_column(String(50))
    tla: Mapped[str | None] = mapped_column(String(8))
    crest_url: Mapped[str | None] = mapped_column(String(500))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))

    competition: Mapped[Competition] = relationship(back_populates="teams")
    home_matches: Mapped[list["Match"]] = relationship(
        back_populates="home_team", foreign_keys="Match.home_team_id"
    )
    away_matches: Mapped[list["Match"]] = relationship(
        back_populates="away_team", foreign_keys="Match.away_team_id"
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    matchday: Mapped[int | None]
    utc_date: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]

    home_team: Mapped[Team] = relationship(
        foreign_keys=[home_team_id], back_populates="home_matches"
    )
    away_team: Mapped[Team] = relationship(
        foreign_keys=[away_team_id], back_populates="away_matches"
    )


class Scorer(Base):
    __tablename__ = "scorers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    player_name: Mapped[str] = mapped_column(String(100), index=True)
    photo_url: Mapped[str | None] = mapped_column(String(500))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    goals: Mapped[int]
    season: Mapped[str | None] = mapped_column(String(20))
