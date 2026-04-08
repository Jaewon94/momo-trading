"""운영 시작 전 read-only preflight 점검 서비스."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from analysis.llm.ollama_provider import OllamaProvider
from services.broker_smoke_service import run_broker_smoke_test
from services.error_capture_service import error_capture_service
from services.news_reporting_service import news_reporting_service
from trading.broker_factory import get_broker_adapter
from trading.enums import LLMTier, Market


class SystemPreflightService:
    async def build_snapshot(self, db: AsyncSession) -> dict:
        adapter = get_broker_adapter()
        probe_symbol = await self._pick_probe_symbol(adapter)
        broker = await self._run_broker_check(adapter=adapter, probe_symbol=probe_symbol)
        news = await self._run_news_check(db)
        ollama = await self._run_ollama_check()

        checks = {
            "broker": broker,
            "news": news,
            "ollama": ollama,
        }
        overall = self._resolve_overall(checks)

        return {
            "overall": overall,
            "probe_symbol": probe_symbol,
            "checks": checks,
            "actions": self._build_actions(checks),
        }

    async def _run_broker_check(self, *, adapter, probe_symbol: str) -> dict:
        try:
            result = await run_broker_smoke_test(
                adapter=adapter,
                symbol=probe_symbol,
                market=Market.KRX,
            )
        except Exception as exc:
            await error_capture_service.capture_exception(
                component="preflight",
                operation="broker_check",
                exc=exc,
                provider=getattr(getattr(adapter, "provider", None), "value", None),
                symbol=probe_symbol,
                detail={"probe_symbol": probe_symbol},
            )
            return {
                "status": "ERROR",
                "label": "브로커 확인 필요",
                "message": str(exc) or "브로커 사전 점검 실패",
                "ok": False,
                "detail": {"probe_symbol": probe_symbol},
            }
        return self._build_broker_check(result)

    async def _run_news_check(self, db: AsyncSession) -> dict:
        try:
            overview = await news_reporting_service.build_overview(
                db,
                recent_limit=1,
                performance_days=7,
            )
        except Exception as exc:
            await error_capture_service.capture_exception(
                component="preflight",
                operation="news_check",
                exc=exc,
            )
            return {
                "status": "ERROR",
                "label": "뉴스 확인 필요",
                "message": str(exc) or "뉴스 사전 점검 실패",
                "ok": False,
                "alerts": [],
                "last_status": "ERROR",
                "last_run_at": None,
            }
        return self._build_news_check(overview)

    async def _run_ollama_check(self) -> dict:
        try:
            return await self._build_ollama_check()
        except Exception as exc:
            await error_capture_service.capture_exception(
                component="preflight",
                operation="ollama_check",
                exc=exc,
                provider="OLLAMA",
            )
            return {
                "status": "ERROR",
                "label": "Ollama 확인 필요",
                "message": str(exc) or "Ollama 사전 점검 실패",
                "ok": False,
            }

    async def _pick_probe_symbol(self, adapter) -> str:
        try:
            holdings = await adapter.get_holdings()
        except Exception:
            holdings = []
        for holding in holdings or []:
            symbol = str(getattr(holding, "symbol", "") or "").strip()
            if symbol:
                return symbol
        return "005930"

    async def _build_ollama_check(self) -> dict:
        available = await OllamaProvider(LLMTier.TIER1).is_available()
        return {
            "status": "OK" if available else "WARN",
            "label": "Ollama 준비" if available else "Ollama 확인 필요",
            "message": "로컬 Ollama 연결 정상" if available else "로컬 Ollama 연결 실패 또는 미기동",
            "ok": bool(available),
        }

    @staticmethod
    def _build_broker_check(result: dict) -> dict:
        checks = result.get("checks") or {}
        failed = [name for name, item in checks.items() if not bool((item or {}).get("ok"))]
        if not failed:
            status = "OK"
            label = "브로커 준비"
            message = "잔고/보유/미체결/호가 조회가 모두 정상입니다."
        else:
            status = "WARN"
            label = "브로커 확인 필요"
            message = f"실패 체크: {', '.join(failed)}"
        return {
            "status": status,
            "label": label,
            "message": message,
            "ok": not failed,
            "detail": result,
        }

    @staticmethod
    def _build_news_check(overview: dict) -> dict:
        health = overview.get("health") or {}
        runtime = (overview.get("runtime") or {}).get("overall") or {}
        alerts = list(health.get("alerts") or [])
        status = str(health.get("status") or "OK").upper()
        return {
            "status": status,
            "label": "뉴스 준비" if status == "OK" else "뉴스 확인 필요",
            "message": str(runtime.get("last_message") or "뉴스 상태 확인 필요"),
            "ok": status == "OK",
            "alerts": alerts,
            "last_status": runtime.get("last_status"),
            "last_run_at": runtime.get("last_run_at"),
        }

    @staticmethod
    def _resolve_overall(checks: dict[str, dict]) -> str:
        statuses = [str((item or {}).get("status") or "OK").upper() for item in checks.values()]
        if any(status == "ERROR" for status in statuses):
            return "ERROR"
        if any(status == "WARN" for status in statuses):
            return "WARN"
        return "OK"

    @staticmethod
    def _build_actions(checks: dict[str, dict]) -> list[str]:
        actions: list[str] = []
        broker = checks.get("broker") or {}
        news = checks.get("news") or {}
        ollama = checks.get("ollama") or {}

        if not broker.get("ok"):
            actions.append("브로커 read-only 조회 실패 항목을 먼저 확인하세요.")
        if not news.get("ok"):
            actions.extend([str(alert) for alert in (news.get("alerts") or []) if str(alert).strip()])
        if not ollama.get("ok"):
            actions.append("Ollama 기동 또는 모델 로드 상태를 확인하세요.")
        if not actions:
            actions.append("운영 전 preflight 기준으로 즉시 조치가 필요한 항목이 없습니다.")
        return actions


system_preflight_service = SystemPreflightService()
