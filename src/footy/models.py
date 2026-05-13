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
    emblem_url: Mapped[str | None] = mapped_column(String(500))
    current_matchday: Mapped[int | None]

    teams: Mapped[list["Team"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
    )


class Team(Base):
    """football-data.org team id is the primary key — natural dedupe across syncs."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), index=True)
    short_name: Mapped[str | None] = mapped_column(String(50))
    tla: Mapped[str | None] = mapped_column(String(8))
    crest_url: Mapped[str | None] = mapped_column(String(500))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))

    competition: Mapped[Competition] = relationship(back_populates="teams")


class Match(Base):
    """football-data.org match id is the primary key."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    matchday: Mapped[int | None]
    utc_date: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    winner: Mapped[str | None] = mapped_column(String(20))  # HOME_TEAM / AWAY_TEAM / DRAW
    venue: Mapped[str | None] = mapped_column(String(120))
    referee: Mapped[str | None] = mapped_column(String(120))
    detail_fetched: Mapped[bool] = mapped_column(default=False)

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="Goal.minute",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="Booking.minute",
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    minute: Mapped[int | None]
    injury_time: Mapped[int | None]
    player_name: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    goal_type: Mapped[str | None] = mapped_column(String(20))  # REGULAR / OWN / PENALTY
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]

    match: Mapped[Match] = relationship(back_populates="goals")


class Booking(Base):
    """Yellow/red cards within a match."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    minute: Mapped[int | None]
    player_name: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    card: Mapped[str] = mapped_column(String(20))  # YELLOW / YELLOW_RED / RED

    match: Mapped[Match] = relationship(back_populates="bookings")


class Standing(Base):
    """League standing row — refreshed from /competitions/{code}/standings."""

    __tablename__ = "standings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[int]
    played: Mapped[int]
    won: Mapped[int]
    drawn: Mapped[int]
    lost: Mapped[int]
    goals_for: Mapped[int]
    goals_against: Mapped[int]
    goal_difference: Mapped[int]
    points: Mapped[int]
    form: Mapped[str | None] = mapped_column(String(20))  # e.g. "WWLDW"

    team: Mapped[Team] = relationship()


class Scorer(Base):
    __tablename__ = "scorers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    player_name: Mapped[str] = mapped_column(String(100), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    goals: Mapped[int]
    assists: Mapped[int | None]
    penalties: Mapped[int | None]
    matches_played: Mapped[int | None]
    season: Mapped[str | None] = mapped_column(String(20))
