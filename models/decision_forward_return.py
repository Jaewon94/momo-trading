"""Forward return labels for canonical decision events."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class DecisionForwardReturn(Base, TimestampMixin):
    __tablename__ = "decision_forward_returns"
    __table_args__ = (
        UniqueConstraint("decision_event_id", "horizon", name="uq_decision_forward_return_horizon"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    decision_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("decision_events.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    reference_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    label_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    price_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision_event = relationship("DecisionEvent")
