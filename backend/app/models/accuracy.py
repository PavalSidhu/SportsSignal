from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PredictionAccuracy(TimestampMixin, Base):
    __tablename__ = "prediction_accuracy"
    __table_args__ = (
        Index(
            "ix_prediction_accuracy_prediction",
            "prediction_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    sport: Mapped[str] = mapped_column(String(10))

    was_correct: Mapped[bool]
    home_score_error: Mapped[float]
    away_score_error: Mapped[float]
    total_score_error: Mapped[float]
    spread_error: Mapped[float]
