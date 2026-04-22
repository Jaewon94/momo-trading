"""Deterministic news risk classification for market/disclosure events."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewsRiskClassification:
    sentiment_label: str
    sentiment_score: float
    impact_score: float
    reason_codes: list[str]
    matched_keywords: list[str]


@dataclass(frozen=True)
class _RiskRule:
    reason_code: str
    keywords: tuple[str, ...]
    sentiment_score: float
    impact_score: float


class NewsRiskClassifier:
    """Classifies explicit risk events before LLM translation/analysis.

    This only handles high-signal market/disclosure language. It does not try to
    infer nuanced sentiment from ordinary articles.
    """

    _RULES: tuple[_RiskRule, ...] = (
        _RiskRule(
            "trading_suspension",
            ("주권매매거래정지", "거래정지", "trading suspension"),
            0.12,
            0.95,
        ),
        _RiskRule(
            "delisting_risk",
            ("상장폐지", "관리종목", "delisting", "administrative issue"),
            0.14,
            0.95,
        ),
        _RiskRule(
            "unfaithful_disclosure",
            ("불성실공시", "공시불이행", "공시번복", "unfaithful disclosure"),
            0.22,
            0.86,
        ),
        _RiskRule(
            "management_dispute",
            ("경영권분쟁", "소송등의제기", "주주총회효력정지", "management dispute"),
            0.26,
            0.82,
        ),
        _RiskRule(
            "accounting_or_fraud",
            ("횡령", "배임", "분식", "감사의견거절", "회계 조사", "fraud", "investigation"),
            0.18,
            0.9,
        ),
        _RiskRule(
            "distress",
            ("부도", "회생절차", "파산", "default", "bankruptcy"),
            0.12,
            0.94,
        ),
        _RiskRule(
            "dilution_financing",
            ("전환사채", "신주인수권", "유상증자", "교환사채", "convertible bond", "rights offering"),
            0.42,
            0.62,
        ),
        _RiskRule(
            "control_change",
            ("최대주주변경", "경영권 변경", "change of largest shareholder"),
            0.44,
            0.58,
        ),
    )

    def classify(self, item: dict[str, Any]) -> NewsRiskClassification | None:
        if self._has_explicit_sentiment(item):
            return None

        text = self._text_for_classification(item)
        if not text:
            return None

        matched_rules: list[_RiskRule] = []
        matched_keywords: list[str] = []
        for rule in self._RULES:
            for keyword in rule.keywords:
                if keyword.lower() not in text:
                    continue
                matched_rules.append(rule)
                matched_keywords.append(keyword)
                break

        if not matched_rules:
            return None

        return NewsRiskClassification(
            sentiment_label="NEGATIVE",
            sentiment_score=min(rule.sentiment_score for rule in matched_rules),
            impact_score=max(rule.impact_score for rule in matched_rules),
            reason_codes=[rule.reason_code for rule in matched_rules],
            matched_keywords=matched_keywords,
        )

    @staticmethod
    def _has_explicit_sentiment(item: dict[str, Any]) -> bool:
        return item.get("sentiment_label") is not None or item.get("sentiment_score") is not None

    @staticmethod
    def _text_for_classification(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        parts = [
            item.get("title"),
            item.get("summary"),
            item.get("body"),
            metadata.get("report_nm"),
            metadata.get("translated_title"),
            metadata.get("translated_summary"),
        ]
        return " ".join(str(part or "") for part in parts).lower()


news_risk_classifier = NewsRiskClassifier()
