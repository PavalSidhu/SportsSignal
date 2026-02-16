from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Game(TimestampMixin, Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("sport", "external_id", name="uq_games_sport_external_id"),
        Index(
            "ix_games_upcoming",
            "game_date",
            "sport",
            postgresql_where="status = 'scheduled'",
        ),
        Index("ix_games_sport_date", "sport", "game_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), index=True)
    sport: Mapped[str] = mapped_column(String(10))
    season: Mapped[int]
    game_date: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    is_postseason: Mapped[bool] = mapped_column(default=False)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    home_score: Mapped[int | None] = mapped_column(nullable=True)
    away_score: Mapped[int | None] = mapped_column(nullable=True)

    # Flexible period scores stored as JSONB arrays (e.g. [28,26,30,28] for NBA quarters)
    home_period_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    away_period_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="game")


from app.models.team import Team  # noqa: E402
from app.models.prediction import Prediction  # noqa: E402, F811
