from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    sport: Mapped[str] = mapped_column(String(10))
    prediction_date: Mapped[datetime]

    # Win/loss prediction
    predicted_winner_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    win_probability: Mapped[float]
    confidence: Mapped[float]

    # Score prediction
    predicted_home_score: Mapped[float]
    predicted_away_score: Mapped[float]
    predicted_spread: Mapped[float]
    predicted_total: Mapped[float]

    # Quarter-by-quarter predictions (JSONB)
    quarter_predictions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Explanation factors (JSONB array)
    key_factors: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Player predictions (future, JSONB)
    player_predictions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="predictions")
    predicted_winner: Mapped["Team"] = relationship(foreign_keys=[predicted_winner_id])


from app.models.game import Game  # noqa: E402, F811
from app.models.team import Team  # noqa: E402, F811
