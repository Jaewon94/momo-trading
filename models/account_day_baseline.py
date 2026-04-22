from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class AccountDayBaseline(Base, TimestampMixin):
    __tablename__ = "account_day_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    baseline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    baseline_total_asset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_stock_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_total_unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_holding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_pending_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_source: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")
