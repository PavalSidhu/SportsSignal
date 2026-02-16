from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GameBoxscore(TimestampMixin, Base):
    __tablename__ = "game_boxscores"
    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_boxscore_game_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    sport: Mapped[str] = mapped_column(String(10))
    stats: Mapped[dict] = mapped_column(JSONB)
