"""일일 운영 종합 리포트 서비스.

장마감 보고(DailyReport, 매매 성과 중심)와 별개로, 시스템 전 기능의 하루치
운영 데이터를 한 문서로 집계한다:

- 매매 funnel (신규 매수 / 청산 / 매도 주문 / 실현손익)
- 의사결정 게이트 (decision_event 단계·액션·리스크 게이트 분포)
- LLM 사용 / AI 스킵 효율 / 잡 실행 / 에러 / 리소스 (observability)
- 뉴스 파이프라인 적재 현황
- 에이전트 활동 카운트
- 전일 리포트 대비 주요 지표 변화량

산출물은 `runtime/reports/daily_ops_<YYYYMMDD>.json`(기계용)과
`daily_ops_<YYYYMMDD>.md`(사람용)로 저장한다. LLM 코멘터리(병목 해설,
개선 제안, 적용 검토할 신기능)는 옵션이며 실패해도 리포트 생성은 계속된다.

각 섹션은 독립적으로 수집한다 — 한 섹션의 실패가 전체 리포트를 막지 않고
해당 섹션에 error 필드로 기록된다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import func, select

from core.config import settings
from core.database import AsyncSessionLocal
from core.paths import RUNTIME_DIR
from models.decision_event import DecisionEvent
from repositories.agent_activity_repository import AgentActivityRepository
from repositories.trade_result_repository import TradeResultRepository
from services.news_reporting_service import news_reporting_service
from services.observability_reporting_service import observability_reporting_service
from util.time_util import now_kst

REPORT_DIR = RUNTIME_DIR / "reports"

# 전일 대비 변화를 추적할 (섹션, 키) 스칼라 지표
_DELTA_KEYS: list[tuple[str, str, str]] = [
    ("trading", "buy_count", "신규 매수"),
    ("trading", "sell_order_count", "매도 주문"),
    ("trading", "completed_count", "청산 완료"),
    ("trading", "realized_pnl", "실현손익(원)"),
    ("decisions", "total_events", "판단 이벤트"),
    ("decisions", "blocked_count", "게이트 차단"),
    ("llm", "total_calls", "LLM 호출"),
    ("ai_skipped", "total_skipped", "AI 스킵"),
    ("errors", "total_count", "에러"),
    ("news", "ingested_24h", "뉴스 적재(24h)"),
]


class DailyOpsReportService:
    """전 기능 일일 운영 리포트 생성기."""

    # ── 수집 ──────────────────────────────────────────────────────────

    async def build_report(self, report_date: date | None = None) -> dict[str, Any]:
        """하루치 운영 데이터를 섹션별로 수집해 dict로 반환한다."""
        target_date = report_date or now_kst().date()
        payload: dict[str, Any] = {
            "schema": "momo.daily_ops_report.v1",
            "report_date": target_date.isoformat(),
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "sections": {},
        }
        sections = payload["sections"]

        async with AsyncSessionLocal() as session:
            sections["trading"] = await self._collect_section(
                "trading", self._collect_trading(session, target_date)
            )
            sections["decisions"] = await self._collect_section(
                "decisions", self._collect_decisions(session, target_date)
            )
            sections["activities"] = await self._collect_section(
                "activities", self._collect_activities(session, target_date)
            )
            sections["news"] = await self._collect_section(
                "news", self._collect_news(session)
            )
            observability = await self._collect_section(
                "observability", self._collect_observability(session)
            )

        # observability 묶음은 마크다운 가독성을 위해 하위 섹션으로 분해한다.
        if "error" in observability:
            for key in ("llm", "ai_skipped", "jobs", "errors", "resource"):
                sections[key] = {"error": observability["error"]}
        else:
            sections["llm"] = observability.get("llm") or {}
            sections["ai_skipped"] = observability.get("ai_skipped") or {}
            sections["jobs"] = observability.get("jobs") or {}
            sections["errors"] = self._normalize_errors(observability.get("errors"))
            sections["resource"] = observability.get("resource_summary") or {}

        payload["deltas"] = self._build_deltas(payload)
        payload["flags"] = self._build_flags(payload)
        return payload

    async def _collect_section(self, name: str, coro) -> dict[str, Any]:
        try:
            result = await coro
            return result if isinstance(result, dict) else {"value": result}
        except Exception as exc:  # noqa: BLE001 - 섹션 실패는 리포트 전체를 막지 않는다
            logger.warning("daily ops report 섹션 수집 실패 ({}): {}", name, str(exc))
            return {"error": str(exc)}

    async def _collect_trading(self, session, target_date: date) -> dict[str, Any]:
        repo = TradeResultRepository(session)
        opened = await repo.get_opened_by_date(target_date)
        completed = await repo.get_completed_by_date(target_date)
        sell_count = await repo.get_sell_count_by_date(target_date)
        open_positions = await repo.get_all_open()

        win_count = sum(1 for t in completed if t.is_win)
        realized_pnl = round(sum(float(t.pnl or 0) for t in completed), 2)
        return {
            "buy_count": len(opened),
            "sell_order_count": sell_count,
            "completed_count": len(completed),
            "win_count": win_count,
            "loss_count": len(completed) - win_count,
            "realized_pnl": realized_pnl,
            "open_position_count": len(open_positions),
        }

    async def _collect_decisions(self, session, target_date: date) -> dict[str, Any]:
        start_at = datetime.combine(target_date, datetime.min.time())
        end_at = start_at + timedelta(days=1)

        stage_rows = await session.execute(
            select(
                DecisionEvent.decision_stage,
                DecisionEvent.final_action,
                func.count(),
            )
            .where(DecisionEvent.created_at >= start_at, DecisionEvent.created_at < end_at)
            .group_by(DecisionEvent.decision_stage, DecisionEvent.final_action)
        )
        by_stage_action: dict[str, dict[str, int]] = {}
        total = 0
        for stage, action, count in stage_rows:
            by_stage_action.setdefault(stage or "UNKNOWN", {})[action or "UNKNOWN"] = int(count)
            total += int(count)

        gate_rows = await session.execute(
            select(DecisionEvent.risk_gate_result, func.count())
            .where(
                DecisionEvent.created_at >= start_at,
                DecisionEvent.created_at < end_at,
                DecisionEvent.risk_gate_result.is_not(None),
            )
            .group_by(DecisionEvent.risk_gate_result)
        )
        by_gate = {str(gate): int(count) for gate, count in gate_rows}
        blocked = sum(
            count
            for gate, count in by_gate.items()
            if any(token in gate.upper() for token in ("BLOCK", "REJECT", "FAIL"))
        )
        return {
            "total_events": total,
            "by_stage_action": by_stage_action,
            "by_risk_gate": by_gate,
            "blocked_count": blocked,
        }

    async def _collect_activities(self, session, target_date: date) -> dict[str, Any]:
        repo = AgentActivityRepository(session)
        counts = await repo.count_by_date(target_date)
        return {"counts": counts, "total": sum(counts.values())}

    async def _collect_news(self, session) -> dict[str, Any]:
        overview = await news_reporting_service.build_overview(
            session, recent_limit=3, performance_days=7
        )
        ingestion = overview.get("ingestion") or {}
        return {
            "ingested_24h": ingestion.get("recent_24h_count"),
            "ingested_7d": ingestion.get("recent_7d_count"),
            "by_source_24h": ingestion.get("by_source_24h"),
            "translation_pending": ingestion.get("translation_pending_count"),
        }

    async def _collect_observability(self, session) -> dict[str, Any]:
        return await observability_reporting_service.build_overview(
            session, hours=24, points=24
        )

    @staticmethod
    def _normalize_errors(errors: Any) -> dict[str, Any]:
        if not isinstance(errors, dict):
            return {"total_count": 0, "incident_count": 0}
        normalized = dict(errors)
        if "total_count" not in normalized:
            normalized["total_count"] = (
                normalized.get("total")
                or normalized.get("count")
                or len(normalized.get("recent", []) or [])
            )
        normalized["incident_count"] = len(normalized.get("incidents", []) or [])
        return normalized

    # ── 전일 대비 / 플래그 ────────────────────────────────────────────

    def _build_deltas(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        previous = self._load_previous_payload(date.fromisoformat(payload["report_date"]))
        if not previous:
            return []
        deltas: list[dict[str, Any]] = []
        for section, key, label in _DELTA_KEYS:
            today_value = (payload["sections"].get(section) or {}).get(key)
            prev_value = (previous.get("sections", {}).get(section) or {}).get(key)
            if not isinstance(today_value, (int, float)) or not isinstance(prev_value, (int, float)):
                continue
            deltas.append(
                {
                    "label": label,
                    "section": section,
                    "key": key,
                    "today": today_value,
                    "previous": prev_value,
                    "delta": round(today_value - prev_value, 2),
                }
            )
        return deltas

    def _load_previous_payload(self, target_date: date) -> dict[str, Any] | None:
        candidates = sorted(REPORT_DIR.glob("daily_ops_*.json"), reverse=True)
        target_name = f"daily_ops_{target_date.strftime('%Y%m%d')}.json"
        for path in candidates:
            if path.name >= target_name:
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return None

    @staticmethod
    def _build_flags(payload: dict[str, Any]) -> list[dict[str, str]]:
        """사람이 먼저 봐야 할 이상 신호. severity: warn | alert"""
        sections = payload["sections"]
        flags: list[dict[str, str]] = []

        for name, section in sections.items():
            if isinstance(section, dict) and section.get("error"):
                flags.append(
                    {"severity": "alert", "message": f"{name} 섹션 수집 실패: {section['error']}"}
                )

        errors = sections.get("errors") or {}
        error_count = errors.get("total_count") or 0
        if isinstance(error_count, (int, float)) and error_count > 0:
            severity = "alert" if error_count >= 10 else "warn"
            flags.append({"severity": severity, "message": f"에러 이벤트 {int(error_count)}건 발생"})
        incident_count = errors.get("incident_count") or 0
        if isinstance(incident_count, (int, float)) and incident_count > 0:
            flags.append(
                {"severity": "warn", "message": f"미해결 에러 인시던트 {int(incident_count)}건"}
            )

        llm = sections.get("llm") or {}
        success_rate = llm.get("success_rate")  # observability 집계는 0~100 퍼센트
        if isinstance(success_rate, (int, float)) and llm.get("total_calls") and success_rate < 90.0:
            flags.append(
                {"severity": "warn", "message": f"LLM 성공률 저하: {success_rate:.0f}%"}
            )

        trading = sections.get("trading") or {}
        pnl = trading.get("realized_pnl")
        if isinstance(pnl, (int, float)) and pnl < 0:
            flags.append({"severity": "warn", "message": f"당일 실현손익 마이너스: {pnl:,.0f}원"})

        return flags

    # ── LLM 코멘터리 ──────────────────────────────────────────────────

    async def generate_llm_commentary(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """운영 데이터 기반 LLM 코멘터리. 실패 시 None (리포트는 계속)."""
        if not settings.DAILY_OPS_REPORT_LLM_ENABLED:
            return None
        try:
            from analysis.llm.llm_factory import llm_factory

            compact = {
                "report_date": payload["report_date"],
                "sections": payload["sections"],
                "deltas": payload["deltas"],
                "flags": payload["flags"],
            }
            prompt = (
                "다음은 국내 주식 자동매매 시스템(momo-trading)의 하루치 운영 데이터다.\n"
                "운영자가 매일 읽는 보고서의 코멘터리를 한국어 Markdown으로 작성하라.\n\n"
                "반드시 아래 4개 소제목 구조를 따르고, 데이터에 근거 없는 수치는 만들지 마라:\n"
                "### 오늘 운영 요약\n(3줄 이내 핵심)\n"
                "### 병목·이상 신호\n(데이터에서 보이는 문제 후보, 없으면 '특이사항 없음')\n"
                "### 개선 제안\n(우선순위 1~3개, 각 한 줄 근거)\n"
                "### 적용 검토할 신기능·최신 기법\n"
                "(이 시스템 데이터 특성에 맞는 새 기능/기법 제안 1~3개 — 예: 새로운 리스크 관리 기법, "
                "LLM 활용 패턴, 모니터링 방식. 일반론 말고 이 데이터와 연결해서)\n\n"
                f"운영 데이터(JSON):\n{json.dumps(compact, ensure_ascii=False, default=str)[:12000]}"
            )
            text, provider = await llm_factory.generate_manual(
                prompt,
                "너는 자동매매 시스템 운영 분석가다. 간결하고 데이터에 근거한 보고만 한다.",
            )
            if not text or not text.strip():
                return None
            return {"text": text.strip(), "provider": provider}
        except Exception as exc:  # noqa: BLE001 - LLM 실패는 리포트를 막지 않는다
            logger.warning("daily ops report LLM 코멘터리 실패 (리포트 계속): {}", str(exc))
            return None

    # ── 렌더링 / 저장 ─────────────────────────────────────────────────

    def render_markdown(
        self, payload: dict[str, Any], commentary: dict[str, Any] | None = None
    ) -> str:
        sections = payload["sections"]
        lines: list[str] = [
            f"# 일일 운영 종합 리포트 — {payload['report_date']}",
            "",
            f"- 생성: {payload['generated_at']}",
            "- 범위: 매매 funnel · 의사결정 게이트 · LLM · AI 스킵 · 잡 · 에러 · 리소스 · 뉴스",
            "",
        ]

        flags = payload.get("flags") or []
        if flags:
            lines.append("## ⚠️ 주목할 신호")
            lines.append("")
            for flag in flags:
                icon = "🔴" if flag["severity"] == "alert" else "🟡"
                lines.append(f"- {icon} {flag['message']}")
            lines.append("")
        else:
            lines.extend(["## ✅ 주목할 신호", "", "- 이상 신호 없음", ""])

        trading = sections.get("trading") or {}
        lines.extend(["## 매매", ""])
        if trading.get("error"):
            lines.append(f"- 수집 실패: {trading['error']}")
        else:
            completed = trading.get("completed_count") or 0
            win = trading.get("win_count") or 0
            win_rate = f"{win}/{completed}" if completed else "-"
            lines.extend(
                [
                    "| 지표 | 값 |",
                    "|---|---|",
                    f"| 신규 매수 | {trading.get('buy_count', '-')}건 |",
                    f"| 매도 주문 | {trading.get('sell_order_count', '-')}건 |",
                    f"| 청산 완료 | {completed}건 (승 {win_rate}) |",
                    f"| 실현손익 | {self._fmt_krw(trading.get('realized_pnl'))} |",
                    f"| 현재 보유 | {trading.get('open_position_count', '-')}건 |",
                ]
            )
        lines.append("")

        decisions = sections.get("decisions") or {}
        lines.extend(["## 의사결정 게이트", ""])
        if decisions.get("error"):
            lines.append(f"- 수집 실패: {decisions['error']}")
        else:
            lines.append(
                f"- 판단 이벤트 {decisions.get('total_events', 0)}건 · "
                f"게이트 차단 {decisions.get('blocked_count', 0)}건"
            )
            by_stage = decisions.get("by_stage_action") or {}
            if by_stage:
                lines.extend(["", "| 단계 | 액션 분포 |", "|---|---|"])
                for stage, actions in sorted(by_stage.items()):
                    summary = ", ".join(f"{a} {c}" for a, c in sorted(actions.items()))
                    lines.append(f"| {stage} | {summary} |")
        lines.append("")

        llm = sections.get("llm") or {}
        skipped = sections.get("ai_skipped") or {}
        lines.extend(["## LLM · AI 스킵", ""])
        if llm.get("error"):
            lines.append(f"- 수집 실패: {llm['error']}")
        else:
            total_calls = llm.get("total_calls") or 0
            rate = llm.get("success_rate")  # 0~100 퍼센트
            rate_text = (
                f"{rate:.0f}%" if total_calls and isinstance(rate, (int, float)) else "-"
            )
            avg_ms = llm.get("avg_elapsed_ms")
            avg_text = f"{avg_ms:,.0f}ms" if isinstance(avg_ms, (int, float)) else "-"
            lines.append(
                f"- LLM 호출 {total_calls}건 · 성공률 {rate_text} · 평균 {avg_text}"
            )
            providers = llm.get("provider_breakdown") or []
            if isinstance(providers, list) and providers:
                parts = ", ".join(
                    f"{p.get('provider', '?')} {p.get('calls', '?')}건"
                    for p in providers[:5]
                    if isinstance(p, dict)
                )
                if parts:
                    lines.append(f"- 프로바이더: {parts}")
            by_reason = skipped.get("by_reason") or []
            reason_text = ""
            if isinstance(by_reason, list) and by_reason:
                reason_text = " (사유: " + ", ".join(
                    f"{r.get('reason_code', '?')} {r.get('count', '?')}"
                    for r in by_reason[:5]
                    if isinstance(r, dict)
                ) + ")"
            lines.append(
                f"- 결정론 필터로 스킵된 LLM 호출 {skipped.get('total_skipped', 0)}건{reason_text}"
            )
        lines.append("")

        errors = sections.get("errors") or {}
        jobs = sections.get("jobs") or {}
        resource = sections.get("resource") or {}
        lines.extend(["## 에러 · 잡 · 리소스", ""])
        lines.append(
            f"- 에러 이벤트(24h): {errors.get('total_count', 0)}건 · "
            f"미해결 인시던트: {errors.get('incident_count', 0)}건"
        )
        lines.extend(self._render_jobs(jobs))
        lines.extend(self._render_resource(resource))
        lines.append("")

        news = sections.get("news") or {}
        lines.extend(["## 뉴스 파이프라인", ""])
        if news.get("error"):
            lines.append(f"- 수집 실패: {news['error']}")
        else:
            lines.append(
                f"- 24h 적재 {news.get('ingested_24h', '-')}건 · 7일 {news.get('ingested_7d', '-')}건 · "
                f"번역 대기 {news.get('translation_pending', '-')}건"
            )
            by_source = news.get("by_source_24h")
            if isinstance(by_source, list) and by_source:
                parts = ", ".join(
                    f"{item.get('source_code', '?')} {item.get('count', '?')}"
                    for item in by_source[:8]
                    if isinstance(item, dict)
                )
                if parts:
                    lines.append(f"- 소스별(24h): {parts}")
        lines.append("")

        deltas = payload.get("deltas") or []
        if deltas:
            lines.extend(["## 전일 대비", "", "| 지표 | 오늘 | 전일 | 변화 |", "|---|---|---|---|"])
            for d in deltas:
                arrow = "▲" if d["delta"] > 0 else ("▼" if d["delta"] < 0 else "—")
                lines.append(
                    f"| {d['label']} | {d['today']:,} | {d['previous']:,} | {arrow} {abs(d['delta']):,} |"
                )
            lines.append("")

        if commentary and commentary.get("text"):
            lines.extend(
                [
                    f"## 🤖 AI 코멘터리 (provider: {commentary.get('provider', '?')})",
                    "",
                    commentary["text"],
                    "",
                ]
            )

        activities = sections.get("activities") or {}
        if not activities.get("error") and activities.get("counts"):
            parts = ", ".join(f"{k} {v}" for k, v in sorted(activities["counts"].items()))
            lines.extend(["## 에이전트 활동", "", f"- {parts}", ""])

        return "\n".join(lines)

    @staticmethod
    def _render_jobs(jobs: Any) -> list[str]:
        """잡 실행 집계를 사람용 표로 변환. {잡이름: {runs, success_rate, ...}} 형태 가정."""
        if not isinstance(jobs, dict) or not jobs or jobs.get("error"):
            return []
        rows: list[str] = []
        for name, stat in sorted(jobs.items()):
            if not isinstance(stat, dict):
                continue
            runs = stat.get("runs", "-")
            rate = stat.get("success_rate")
            rate_text = f"{rate:.0f}%" if isinstance(rate, (int, float)) else "-"
            avg_ms = stat.get("avg_elapsed_ms")
            avg_text = f"{avg_ms:,.0f}ms" if isinstance(avg_ms, (int, float)) else "-"
            error_runs = stat.get("error_runs", 0) or 0
            error_text = f" · 실패 {error_runs}" if error_runs else ""
            rows.append(f"| {name} | {runs} | {rate_text} | {avg_text}{error_text} |")
        if not rows:
            return []
        return ["", "| 잡 | 실행 | 성공률 | 평균 소요 |", "|---|---|---|---|", *rows]

    @staticmethod
    def _render_resource(resource: Any) -> list[str]:
        if not isinstance(resource, dict) or not resource or resource.get("error"):
            return []
        parts: list[str] = []
        mem_avg = resource.get("avg_memory_percent")
        mem_peak = resource.get("peak_memory_percent")
        if isinstance(mem_peak, (int, float)):
            avg_text = f"{mem_avg:.0f}%" if isinstance(mem_avg, (int, float)) else "-"
            parts.append(f"메모리 평균 {avg_text} / 피크 {mem_peak:.0f}%")
        cpu_peak = resource.get("peak_cpu_load_ratio_1m")
        if isinstance(cpu_peak, (int, float)):
            parts.append(f"CPU 부하 피크 {cpu_peak:.2f}")
        app_rss = resource.get("peak_app_rss_mb")
        if isinstance(app_rss, (int, float)):
            parts.append(f"앱 RSS 피크 {app_rss:,.0f}MB")
        if not parts:
            return []
        return [f"- 리소스: {' · '.join(parts)}"]

    @staticmethod
    def _fmt_krw(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "-"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:,.0f}원"

    async def generate_and_persist(
        self,
        report_date: date | None = None,
        *,
        include_llm: bool | None = None,
    ) -> dict[str, Any]:
        """리포트 생성 후 JSON + Markdown 저장. 저장 경로를 payload에 담아 반환."""
        payload = await self.build_report(report_date)

        use_llm = settings.DAILY_OPS_REPORT_LLM_ENABLED if include_llm is None else include_llm
        commentary = await self.generate_llm_commentary(payload) if use_llm else None
        if commentary:
            payload["llm_commentary"] = commentary

        markdown = self.render_markdown(payload, commentary)

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = date.fromisoformat(payload["report_date"]).strftime("%Y%m%d")
        json_path = REPORT_DIR / f"daily_ops_{stamp}.json"
        md_path = REPORT_DIR / f"daily_ops_{stamp}.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        md_path.write_text(markdown, encoding="utf-8")

        payload["paths"] = {"json": str(json_path), "markdown": str(md_path)}
        logger.info("일일 운영 리포트 저장: {} (flags {}건)", md_path.name, len(payload.get("flags") or []))
        return payload


daily_ops_report_service = DailyOpsReportService()
