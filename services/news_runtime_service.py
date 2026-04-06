"""뉴스 수집 런타임 상태 스냅샷 서비스."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.news_ingest_service import news_ingest_service
from util.time_util import now_kst


class NewsRuntimeService:
    IMPLEMENTED_SOURCES = {"DART", "KRX", "YONHAP", "BLOOMBERG", "CNBC", "NASDAQ", "INVESTING"}

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._overall = {
            "last_status": "IDLE",
            "last_mode": None,
            "last_message": "아직 수집 이력이 없습니다.",
            "last_source_code": None,
            "last_run_at": None,
            "last_success_at": None,
        }
        self._sources: dict[str, dict[str, Any]] = {}

    def get_snapshot(self, *, include_foreign: bool) -> dict[str, Any]:
        catalog = news_ingest_service.get_source_catalog(include_foreign=include_foreign)
        ordered_sources: dict[str, dict[str, Any]] = {}
        for item in catalog:
            code = str(item.get("code") or "").upper()
            if not code:
                continue
            source_state = deepcopy(self._sources.get(code) or self._build_default_source_state(item))
            source_state["implemented"] = bool(item.get("implemented", code in self.IMPLEMENTED_SOURCES))
            ordered_sources[code] = self._serialize_source_state(source_state)
        return {
            "overall": self._serialize_overall(),
            "sources": ordered_sources,
        }

    def record_source_result(
        self,
        source_code: str,
        *,
        status: str,
        mode: str,
        message: str | None = None,
        counts: dict[str, Any] | None = None,
    ) -> None:
        code = str(source_code or "").upper().strip()
        if not code:
            return
        source_state = self._sources.get(code) or self._build_default_source_state({"code": code})
        now = now_kst()
        source_state.update({
            "status": str(status or "IDLE").upper(),
            "mode": mode,
            "message": message or self._default_message_for_status(status),
            "updated_at": now,
            "counts": self._normalize_counts(counts),
        })
        self._sources[code] = source_state

        self._overall.update({
            "last_status": source_state["status"],
            "last_mode": mode,
            "last_message": source_state["message"],
            "last_source_code": code,
            "last_run_at": now,
        })
        if source_state["status"] == "SUCCESS":
            self._overall["last_success_at"] = now

    def _serialize_overall(self) -> dict[str, Any]:
        payload = deepcopy(self._overall)
        if payload["last_run_at"] is not None:
            payload["last_run_at"] = payload["last_run_at"].isoformat()
        if payload["last_success_at"] is not None:
            payload["last_success_at"] = payload["last_success_at"].isoformat()
        return payload

    def _serialize_source_state(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(state)
        updated_at = payload.get("updated_at")
        if updated_at is not None:
            payload["updated_at"] = updated_at.isoformat()
        payload["counts"] = self._normalize_counts(payload.get("counts"))
        return payload

    def _build_default_source_state(self, source: dict[str, Any]) -> dict[str, Any]:
        code = str(source.get("code") or "").upper()
        implemented = code in self.IMPLEMENTED_SOURCES
        return {
            "status": "IDLE",
            "mode": None,
            "message": "대기 중" if implemented else "실수집 미연결",
            "updated_at": None,
            "counts": self._normalize_counts(None),
            "implemented": implemented,
        }

    @staticmethod
    def _normalize_counts(counts: dict[str, Any] | None) -> dict[str, int]:
        payload = counts or {}
        return {
            "received": int(payload.get("received") or 0),
            "created": int(payload.get("created") or 0),
            "duplicates": int(payload.get("duplicates") or 0),
            "skipped": int(payload.get("skipped") or 0),
        }

    @staticmethod
    def _default_message_for_status(status: str | None) -> str:
        normalized = str(status or "").upper()
        if normalized == "SUCCESS":
            return "수집 성공"
        if normalized == "EMPTY":
            return "조회된 데이터 없음"
        if normalized == "SKIPPED":
            return "수집 스킵"
        if normalized == "ERROR":
            return "수집 실패"
        return "대기 중"


news_runtime_service = NewsRuntimeService()
