"""Canonical decision event dataset for strategy/LLM/news evaluation."""
from uuid import uuid4

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class DecisionEvent(Base, TimestampMixin):
    __tablename__ = "decision_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False, default="KRX")

    decision_stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    strategy_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    scanner_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier1_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tier2_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_gate_result: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    final_action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    reference_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN", index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="UNKNOWN")
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECORDED", index=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
