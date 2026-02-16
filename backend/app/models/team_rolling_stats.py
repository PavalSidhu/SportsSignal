from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TeamRollingStats(TimestampMixin, Base):
    __tablename__ = "team_rolling_stats"
    __table_args__ = (
        UniqueConstraint("team_id", "game_id", name="uq_rolling_team_game"),
        Index("ix_rolling_team_date", "team_id", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    sport: Mapped[str] = mapped_column(String(10))
    as_of_date: Mapped[datetime]
    games_played: Mapped[int]
    stats: Mapped[dict] = mapped_column(JSONB)
