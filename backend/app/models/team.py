from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Team(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", name="uq_teams_sport_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), index=True)
    sport: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100))
    abbreviation: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(100), default="")
    conference: Mapped[str] = mapped_column(String(50), default="")
    division: Mapped[str] = mapped_column(String(50), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    current_elo: Mapped[float] = mapped_column(default=1500.0)

    elo_history: Mapped[list["TeamEloHistory"]] = relationship(back_populates="team")


class TeamEloHistory(Base):
    __tablename__ = "team_elo_history"
    __table_args__ = (Index("ix_team_elo_team_date", "team_id", "game_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    game_date: Mapped[datetime]
    elo_before: Mapped[float]
    elo_after: Mapped[float]

    team: Mapped["Team"] = relationship(back_populates="elo_history")
