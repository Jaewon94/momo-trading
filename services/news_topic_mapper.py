"""Rule-based mapping from global news language to local sectors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewsTopicMapping:
    categories: list[str]
    reason_codes: list[str]
    matched_keywords: list[str]


@dataclass(frozen=True)
class _TopicRule:
    category: str
    keywords: tuple[str, ...]


class NewsTopicMapper:
    """Maps high-signal English/Korean macro themes to local stock categories."""

    _RULES: tuple[_TopicRule, ...] = (
        _TopicRule(
            "반도체",
            (
                "semiconductor",
                "chip",
                "chips",
                "ai chip",
                "advanced chip",
                "hbm",
                "dram",
                "nand",
                "memory",
                "micron",
                "nvidia",
                "tsmc",
                "asml",
                "export control",
                "export controls",
                "반도체",
                "수출통제",
            ),
        ),
        _TopicRule(
            "2차전지",
            ("battery", "batteries", "lithium", "cathode", "anode", "ev battery", "2차전지"),
        ),
        _TopicRule(
            "자동차",
            ("automaker", "vehicle", "electric vehicle", "ev demand", "auto tariff", "자동차"),
        ),
        _TopicRule(
            "인터넷",
            ("platform", "search ads", "cloud", "online ads", "internet platform", "인터넷"),
        ),
        _TopicRule(
            "방산",
            ("defense", "missile", "arms", "geopolitical", "방산"),
        ),
        _TopicRule(
            "조선",
            ("shipbuilding", "lng carrier", "vessel", "조선"),
        ),
    )

    def map_item(self, item: dict[str, Any]) -> NewsTopicMapping | None:
        text = self._text_for_mapping(item)
        if not text:
            return None

        categories: list[str] = []
        matched_keywords: list[str] = []
        for rule in self._RULES:
            for keyword in rule.keywords:
                if keyword.lower() not in text:
                    continue
                if rule.category not in categories:
                    categories.append(rule.category)
                matched_keywords.append(keyword)
                break

        if not categories:
            return None

        return NewsTopicMapping(
            categories=categories[:3],
            reason_codes=["english_theme_keywords"],
            matched_keywords=matched_keywords,
        )

    @staticmethod
    def _text_for_mapping(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        parts = [
            item.get("title"),
            item.get("summary"),
            item.get("body"),
            metadata.get("translated_title"),
            metadata.get("translated_summary"),
        ]
        return " ".join(str(part or "") for part in parts).lower()


news_topic_mapper = NewsTopicMapper()
