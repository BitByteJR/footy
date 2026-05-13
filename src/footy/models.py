"""ORM models."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from footy.db import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    area_name: Mapped[str] = mapped_column(String(100))

    teams: Mapped[list["Team"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(20))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))

    competition: Mapped[Competition] = relationship(back_populates="teams")
