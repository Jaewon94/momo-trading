"""일일 운영 종합 리포트 잡.

평일 장마감 후(16:40) 시스템 전 기능의 하루치 운영 데이터를 집계해
`runtime/reports/daily_ops_<YYYYMMDD>.json` + `.md`로 저장한다.
장마감 매매 보고(daily_report)와 별개의 운영 관점 보고서다.

설정:
- DAILY_OPS_REPORT_ENABLED: 잡 자체 on/off
- DAILY_OPS_REPORT_LLM_ENABLED: LLM 코멘터리(병목 해설·개선/신기능 제안) on/off
"""
from __future__ import annotations

from loguru import logger

from core.config import settings


async def daily_ops_report_job() -> None:
    if not settings.DAILY_OPS_REPORT_ENABLED:
        logger.debug("daily ops report 비활성화 — 스킵")
        return
    try:
        from services.daily_ops_report_service import daily_ops_report_service

        payload = await daily_ops_report_service.generate_and_persist()
        flags = payload.get("flags") or []
        logger.info(
            "일일 운영 리포트 완료: {} (주목 신호 {}건, LLM 코멘터리 {})",
            payload.get("paths", {}).get("markdown", "?"),
            len(flags),
            "포함" if payload.get("llm_commentary") else "없음",
        )
    except Exception as exc:  # noqa: BLE001 - 리포트 실패가 스케줄러를 막지 않는다
        logger.error("일일 운영 리포트 실패: {}", str(exc))
