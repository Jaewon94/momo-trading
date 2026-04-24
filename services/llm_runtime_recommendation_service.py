"""런타임 메트릭 기반 LLM 추천 서비스."""
from __future__ import annotations

import re
from typing import Any

from analysis.llm.selection_policy import resolve_manual_selection, resolve_news_selection
from core.config import settings
from trading.enums import LLMTier

_MODEL_SIZE_RE = re.compile(r":([0-9]+(?:\.[0-9]+)?)b$", re.IGNORECASE)


def _parse_model_size_b(model: str | None) -> float | None:
    text = str(model or "").strip()
    if not text:
        return None
    match = _MODEL_SIZE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _ollama_family(model: str | None) -> str | None:
    text = str(model or "").strip()
    if not text or ":" not in text:
        return None
    return text.split(":", 1)[0]


def _recommended_ollama_model(current_model: str | None, *, target_size: str) -> str:
    family = _ollama_family(current_model) or "qwen3"
    return f"{family}:{target_size}"


class LLMRuntimeRecommendationService:
    def build_recommendations(
        self,
        *,
        latest_snapshot: dict[str, Any] | None,
        resource_summary: dict[str, Any],
        llm_summary: dict[str, Any],
        news_poll_summary: dict[str, Any],
        window: dict[str, Any],
    ) -> dict[str, Any]:
        latest = latest_snapshot or {}
        news_selection = resolve_news_selection()
        manual_selection = resolve_manual_selection(default_tier=LLMTier.TIER2)

        pressure = self._machine_pressure(latest=latest, resource_summary=resource_summary)
        news_recommendation = self._recommend_news(
            selection=news_selection,
            pressure=pressure,
            llm_summary=llm_summary,
            news_poll_summary=news_poll_summary,
        )
        manual_recommendation = self._recommend_manual(
            selection=manual_selection,
            pressure=pressure,
            llm_summary=llm_summary,
        )
        concurrency = self._recommend_concurrency(
            news_recommendation=news_recommendation,
            pressure=pressure,
            latest=latest,
        )

        return {
            "window_hours": int(window.get("hours") or 24),
            "machine_pressure": pressure,
            "news_translation": news_recommendation,
            "manual_analysis": manual_recommendation,
            "ollama_concurrency": concurrency,
        }

    def _machine_pressure(
        self,
        *,
        latest: dict[str, Any],
        resource_summary: dict[str, Any],
    ) -> dict[str, Any]:
        memory_percent = float(latest.get("memory_percent") or 0.0)
        cpu_ratio = float(latest.get("cpu_load_ratio_1m") or 0.0)
        ollama_rss_mb = float(latest.get("ollama_rss_mb") or 0.0)
        peak_ollama_rss_mb = float(resource_summary.get("peak_ollama_rss_mb") or 0.0)

        severity = "LOW"
        reasons: list[str] = []
        if memory_percent >= 85.0:
            severity = "HIGH"
            reasons.append(f"메모리 사용률 {memory_percent:.1f}%")
        elif memory_percent >= 75.0:
            severity = "MEDIUM"
            reasons.append(f"메모리 사용률 {memory_percent:.1f}%")

        if cpu_ratio >= 1.2:
            severity = "HIGH"
            reasons.append(f"CPU load ratio {cpu_ratio:.2f}")
        elif cpu_ratio >= 0.9 and severity == "LOW":
            severity = "MEDIUM"
            reasons.append(f"CPU load ratio {cpu_ratio:.2f}")

        if max(ollama_rss_mb, peak_ollama_rss_mb) >= 10_240.0 and severity != "HIGH":
            severity = "MEDIUM"
            reasons.append("Ollama 메모리 사용량 높음")

        if not reasons:
            reasons.append("리소스 압박 낮음")

        return {
            "severity": severity,
            "reasons": reasons,
            "memory_percent": round(memory_percent, 1),
            "cpu_load_ratio_1m": round(cpu_ratio, 2),
            "ollama_rss_mb": round(ollama_rss_mb, 1),
        }

    def _recommend_news(
        self,
        *,
        selection,
        pressure: dict[str, Any],
        llm_summary: dict[str, Any],
        news_poll_summary: dict[str, Any],
    ) -> dict[str, Any]:
        provider = str(selection.provider or "CLAUDE_CODE").upper()
        model = str(selection.model or "DEFAULT")
        size_b = _parse_model_size_b(model)
        avg_latency = float(llm_summary.get("avg_elapsed_ms") or 0.0)
        p95_latency = float(llm_summary.get("p95_elapsed_ms") or 0.0)
        news_p95 = float(news_poll_summary.get("p95_elapsed_ms") or 0.0)
        pressure_severity = str(pressure.get("severity") or "LOW")
        reasons: list[str] = []

        if not bool(settings.NEWS_LLM_ENABLED):
            return {
                "current": {"provider": provider, "model": model},
                "recommended": {"provider": provider, "model": model},
                "action": "KEEP",
                "reasons": ["뉴스 LLM이 비활성화되어 모델 변경 불필요"],
            }

        if not bool(settings.NEWS_TRANSLATE_FOREIGN_ENABLED):
            return {
                "current": {"provider": provider, "model": model},
                "recommended": {"provider": provider, "model": model},
                "action": "KEEP",
                "reasons": ["해외 뉴스 번역이 비활성화되어 모델 변경 불필요"],
            }

        if provider != "OLLAMA":
            return {
                "current": {"provider": provider, "model": model},
                "recommended": {"provider": provider, "model": model},
                "action": "KEEP",
                "reasons": ["외부 provider 사용 중이라 현재 설정 유지 권장"],
            }

        target_model = model
        action = "KEEP"
        if pressure_severity == "HIGH" or p95_latency >= 30_000 or news_p95 >= 45_000:
            target_model = _recommended_ollama_model(model, target_size="4b")
            action = "DOWNGRADE"
            reasons.append("지연 또는 리소스 압박이 높아 경량 모델 권장")
        elif pressure_severity == "MEDIUM" or p95_latency >= 15_000 or news_p95 >= 25_000:
            target_model = _recommended_ollama_model(model, target_size="8b")
            action = "DOWNGRADE" if (size_b or 0.0) > 8.0 else "KEEP"
            reasons.append("장중 안정성을 위해 8b 이하 권장")
        elif size_b is not None and size_b <= 4.0 and avg_latency <= 8_000 and float(llm_summary.get("success_rate") or 0.0) >= 95.0:
            target_model = _recommended_ollama_model(model, target_size="8b")
            action = "UPGRADE"
            reasons.append("여유가 있어 품질 보강용 8b 권장")

        if not reasons:
            reasons.append("현재 뉴스 번역 설정 유지 권장")
        if target_model == model:
            action = "KEEP"

        return {
            "current": {"provider": provider, "model": model},
            "recommended": {"provider": provider, "model": target_model},
            "action": action,
            "reasons": reasons,
        }

    def _recommend_manual(
        self,
        *,
        selection,
        pressure: dict[str, Any],
        llm_summary: dict[str, Any],
    ) -> dict[str, Any]:
        provider = str(selection.provider or "CLAUDE_CODE").upper()
        model = str(selection.model or "DEFAULT")
        size_b = _parse_model_size_b(model)
        pressure_severity = str(pressure.get("severity") or "LOW")
        reasons: list[str] = []

        if provider != "OLLAMA":
            return {
                "current": {"provider": provider, "model": model},
                "recommended": {"provider": provider, "model": model},
                "action": "KEEP",
                "reasons": ["수동 분석은 현재 고품질 provider 유지 권장"],
            }

        target_model = model
        action = "KEEP"
        if pressure_severity == "HIGH":
            target_model = _recommended_ollama_model(model, target_size="8b")
            action = "DOWNGRADE" if (size_b or 0.0) > 8.0 else "KEEP"
            reasons.append("시스템 압박 시 수동 분석도 8b 이하 권장")
        elif pressure_severity == "LOW" and (size_b is None or size_b < 12.0) and float(llm_summary.get("success_rate") or 0.0) >= 95.0:
            target_model = _recommended_ollama_model(model, target_size="14b")
            action = "UPGRADE"
            reasons.append("오프라인/수동 분석 품질 보강용 14b 권장")

        if not reasons:
            reasons.append("현재 수동 분석 설정 유지 권장")

        return {
            "current": {"provider": provider, "model": model},
            "recommended": {"provider": provider, "model": target_model},
            "action": action,
            "reasons": reasons,
        }

    def _recommend_concurrency(
        self,
        *,
        news_recommendation: dict[str, Any],
        pressure: dict[str, Any],
        latest: dict[str, Any],
    ) -> dict[str, Any]:
        model = str((news_recommendation.get("recommended") or {}).get("model") or "")
        size_b = _parse_model_size_b(model)
        pressure_severity = str(pressure.get("severity") or "LOW")
        recommended = 1
        reasons: list[str] = []

        if pressure_severity == "HIGH":
            recommended = 1
            reasons.append("리소스 압박이 높아 동시 실행 1개 권장")
        elif size_b is not None and size_b <= 4.0 and float(latest.get("memory_percent") or 0.0) < 70.0:
            recommended = 2
            reasons.append("4b급 경량 모델이라 뉴스 번역 동시 실행 2개까지 권장")
        else:
            recommended = 1
            reasons.append("8b 이상 또는 일반 상태에서는 동시 실행 1개 권장")

        return {
            "recommended_parallel_jobs": recommended,
            "reasons": reasons,
        }


llm_runtime_recommendation_service = LLMRuntimeRecommendationService()
