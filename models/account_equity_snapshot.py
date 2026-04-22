from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class AccountEquitySnapshot(Base, TimestampMixin):
    __tablename__ = "account_equity_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    session_phase: Mapped[str] = mapped_column(String(30), nullable=False, default="INTRADAY", index=True)
    total_asset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_unrealized_pnl_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    holding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
