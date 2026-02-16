from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Injury(TimestampMixin, Base):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    sport: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500), default="")
    report_date: Mapped[datetime]
