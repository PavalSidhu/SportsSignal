from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlayerGameStats(TimestampMixin, Base):
    __tablename__ = "player_game_stats"
    __table_args__ = (
        Index("ix_player_game_stats_player_game", "player_id", "game_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))

    minutes: Mapped[float | None] = mapped_column(nullable=True)
    points: Mapped[int | None] = mapped_column(nullable=True)
    rebounds: Mapped[int | None] = mapped_column(nullable=True)
    assists: Mapped[int | None] = mapped_column(nullable=True)
    steals: Mapped[int | None] = mapped_column(nullable=True)
    blocks: Mapped[int | None] = mapped_column(nullable=True)
    turnovers: Mapped[int | None] = mapped_column(nullable=True)
    fg_made: Mapped[int | None] = mapped_column(nullable=True)
    fg_attempted: Mapped[int | None] = mapped_column(nullable=True)
    fg3_made: Mapped[int | None] = mapped_column(nullable=True)
    fg3_attempted: Mapped[int | None] = mapped_column(nullable=True)
    ft_made: Mapped[int | None] = mapped_column(nullable=True)
    ft_attempted: Mapped[int | None] = mapped_column(nullable=True)
    personal_fouls: Mapped[int | None] = mapped_column(nullable=True)
