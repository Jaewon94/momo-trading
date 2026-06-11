"""일일 운영 종합 리포트 수동 실행기.

사용:
    .venv313/bin/python scripts/dev/run_daily_ops_report.py            # 오늘, LLM 포함
    .venv313/bin/python scripts/dev/run_daily_ops_report.py --no-llm   # LLM 코멘터리 생략
    .venv313/bin/python scripts/dev/run_daily_ops_report.py --date 2026-06-11
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


async def _main() -> int:
    parser = argparse.ArgumentParser(description="일일 운영 종합 리포트 생성")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--no-llm", action="store_true", help="LLM 코멘터리 생략")
    args = parser.parse_args()

    from services.daily_ops_report_service import daily_ops_report_service

    payload = await daily_ops_report_service.generate_and_persist(
        args.date, include_llm=not args.no_llm
    )
    paths = payload.get("paths", {})
    print(f"JSON: {paths.get('json')}")
    print(f"Markdown: {paths.get('markdown')}")
    print(f"주목 신호: {len(payload.get('flags') or [])}건")
    print(f"LLM 코멘터리: {'포함' if payload.get('llm_commentary') else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
