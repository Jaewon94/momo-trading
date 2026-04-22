from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NewsIngestItemRequest(BaseModel):
    source_code: str
    title: str
    published_at: datetime | str | None = None
    symbols: list[str] = Field(default_factory=list)
    url: str | None = None
    external_id: str | None = None
    summary: str | None = None
    body: str | None = None
    language: str | None = None
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    impact_score: float | None = None
    trust_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsBatchIngestRequest(BaseModel):
    items: list[NewsIngestItemRequest] = Field(default_factory=list)
