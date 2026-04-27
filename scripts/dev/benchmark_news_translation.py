#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.llm.selection_policy import NewsSelection
from core.config import settings
from services.news_translation_service import NewsTranslationService
from trading.enums import LLMProvider


SAMPLE_ITEMS = [
    {
        "source_code": "CNBC",
        "language": "en",
        "title": "Nvidia shares rise as analysts point to stronger AI server demand",
        "summary": "Chip stocks gained after several analysts raised demand expectations for AI infrastructure.",
    },
    {
        "source_code": "INVESTING",
        "language": "en",
        "title": "Oil slips as traders weigh inventory builds and OPEC supply signals",
        "summary": "Crude prices moved lower while investors assessed demand and producer policy headlines.",
    },
    {
        "source_code": "BLOOMBERG",
        "language": "en",
        "title": "South Korean battery makers advance on report of stronger US orders",
        "summary": "Battery suppliers climbed after reports suggested improving order momentum from US automakers.",
    },
]


def _build_selection(provider: str, model: str) -> NewsSelection:
    provider_key = LLMProvider(provider.upper())
    return NewsSelection(
        enabled=True,
        provider=provider_key.value,
        model=model,
        fallback_provider="",
        fallback_model="DEFAULT",
        provider_chain=(provider_key,),
        provider_model_overrides={provider_key: model},
    )


async def _run_once(service: NewsTranslationService, item: dict, selection: NewsSelection) -> dict:
    started = time.perf_counter()
    result = await service.translate_item(dict(item), news_selection=selection)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    metadata = result.get("metadata") or {}
    return {
        "source_code": item["source_code"],
        "elapsed_ms": elapsed_ms,
        "status": metadata.get("translation_status") or "UNKNOWN",
        "provider": metadata.get("translation_provider") or selection.provider,
        "translated_title": metadata.get("translated_title") or "",
        "sentiment_label": result.get("sentiment_label") or "",
        "sentiment_score": result.get("sentiment_score"),
        "error": metadata.get("translation_error") or "",
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark foreign-news translation latency and parse stability.")
    parser.add_argument("--provider", default="OLLAMA", choices=["OLLAMA", "CODEX", "CLAUDE_CODE"])
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--sample-count", type=int, default=len(SAMPLE_ITEMS))
    parser.add_argument("--timeout-sec", type=int, default=90)
    args = parser.parse_args()

    settings.NEWS_LLM_ENABLED = True
    settings.NEWS_TRANSLATE_FOREIGN_ENABLED = True
    settings.OLLAMA_GENERATE_TIMEOUT_SEC = max(int(args.timeout_sec), 1)
    selection = _build_selection(args.provider, args.model)
    service = NewsTranslationService()

    rows = []
    sample_items = SAMPLE_ITEMS[:max(min(int(args.sample_count), len(SAMPLE_ITEMS)), 1)]
    for _ in range(max(args.repeat, 1)):
        for item in sample_items:
            rows.append(await _run_once(service, item, selection))

    elapsed_values = [row["elapsed_ms"] for row in rows]
    success_count = sum(1 for row in rows if row["status"] == "SUCCESS")
    payload = {
        "provider": args.provider,
        "model": args.model,
        "samples": len(rows),
        "success_count": success_count,
        "success_rate": round((success_count / len(rows)) * 100.0, 2) if rows else 0.0,
        "avg_elapsed_ms": int(statistics.mean(elapsed_values)) if elapsed_values else 0,
        "p95_elapsed_ms": int(statistics.quantiles(elapsed_values, n=20)[18]) if len(elapsed_values) >= 2 else (elapsed_values[0] if elapsed_values else 0),
        "rows": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if success_count == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
