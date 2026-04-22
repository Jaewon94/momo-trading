"""뉴스 수집/정규화 저장 모델."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_tier: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="ko", nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    symbols_csv: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
