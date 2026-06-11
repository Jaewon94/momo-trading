"""daily_ops_report_service 단위 테스트.

DB/LLM/관측 서비스는 전부 모킹한다 — 섹션 격리, 플래그, 전일 대비,
마크다운 렌더링, 파일 저장 계약을 검증한다.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

import services.daily_ops_report_service as mod
from services.daily_ops_report_service import DailyOpsReportService


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


def _patch_sections(monkeypatch, service, *, trading=None, observability=None):
    """모든 _collect_* 를 canned dict로 대체한다."""

    async def fake_trading(session, target_date):
        if isinstance(trading, Exception):
            raise trading
        return trading or {
            "buy_count": 3,
            "sell_order_count": 2,
            "completed_count": 2,
            "win_count": 1,
            "loss_count": 1,
            "realized_pnl": -15000.0,
            "open_position_count": 4,
        }

    async def fake_decisions(session, target_date):
        return {
            "total_events": 40,
            "by_stage_action": {"FAST_GATE": {"SKIP": 30, "CONTINUE": 10}},
            "by_risk_gate": {"BLOCKED_BUDGET": 5},
            "blocked_count": 5,
        }

    async def fake_activities(session, target_date):
        return {"counts": {"CYCLE": 12, "DECISION": 7}, "total": 19}

    async def fake_news(session):
        return {
            "ingested_24h": 120,
            "ingested_7d": 800,
            "by_source_24h": [{"source_code": "YONHAP", "count": 50}],
            "translation_pending": 3,
        }

    async def fake_observability(session):
        return observability or {
            "llm": {
                "total_calls": 100,
                "success_rate": 85.0,
                "avg_elapsed_ms": 1200,
                "provider_breakdown": [{"provider": "CODEX", "calls": 80}],
            },
            "ai_skipped": {
                "total_skipped": 55,
                "by_reason": [{"stage": "FAST_GATE", "reason_code": "LOW_SCORE", "count": 40}],
            },
            "jobs": {"total": 9},
            "errors": {"total_count": 12},
            "resource_summary": {"cpu_peak": 70},
        }

    monkeypatch.setattr(service, "_collect_trading", fake_trading)
    monkeypatch.setattr(service, "_collect_decisions", fake_decisions)
    monkeypatch.setattr(service, "_collect_activities", fake_activities)
    monkeypatch.setattr(service, "_collect_news", fake_news)
    monkeypatch.setattr(service, "_collect_observability", fake_observability)
    monkeypatch.setattr(mod, "AsyncSessionLocal", _FakeSessionCtx)


@pytest.mark.asyncio
async def test_build_report_assembles_sections_and_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service)

    payload = await service.build_report(date(2026, 6, 12))

    assert payload["report_date"] == "2026-06-12"
    sections = payload["sections"]
    assert sections["trading"]["buy_count"] == 3
    assert sections["llm"]["total_calls"] == 100
    assert sections["errors"]["total_count"] == 12
    # 플래그: 에러 12건(alert) + 성공률 85%(warn) + 손익 마이너스(warn)
    messages = [f["message"] for f in payload["flags"]]
    assert any("에러 이벤트 12건" in m for m in messages)
    assert any("성공률" in m for m in messages)
    assert any("실현손익 마이너스" in m for m in messages)
    assert any(f["severity"] == "alert" for f in payload["flags"])


@pytest.mark.asyncio
async def test_build_report_isolates_section_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service, trading=RuntimeError("DB down"))

    payload = await service.build_report(date(2026, 6, 12))

    assert payload["sections"]["trading"]["error"] == "DB down"
    # 다른 섹션은 정상 수집
    assert payload["sections"]["decisions"]["total_events"] == 40
    assert any("trading 섹션 수집 실패" in f["message"] for f in payload["flags"])


@pytest.mark.asyncio
async def test_deltas_compare_with_previous_report(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    previous = {
        "report_date": "2026-06-11",
        "sections": {
            "trading": {"buy_count": 1, "realized_pnl": 5000.0},
            "decisions": {"total_events": 10, "blocked_count": 2},
            "llm": {"total_calls": 60},
            "ai_skipped": {"total_skipped": 20},
            "errors": {"total_count": 0},
            "news": {"ingested_24h": 90},
        },
    }
    (tmp_path / "daily_ops_20260611.json").write_text(
        json.dumps(previous), encoding="utf-8"
    )
    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service)

    payload = await service.build_report(date(2026, 6, 12))

    by_key = {d["key"]: d for d in payload["deltas"]}
    assert by_key["buy_count"]["delta"] == 2  # 3 - 1
    assert by_key["total_calls"]["delta"] == 40  # 100 - 60
    assert by_key["total_skipped"]["previous"] == 20


@pytest.mark.asyncio
async def test_generate_and_persist_writes_json_and_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service)

    payload = await service.generate_and_persist(date(2026, 6, 12), include_llm=False)

    json_path = tmp_path / "daily_ops_20260612.json"
    md_path = tmp_path / "daily_ops_20260612.md"
    assert json_path.exists() and md_path.exists()
    assert payload["paths"]["markdown"] == str(md_path)

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["schema"] == "momo.daily_ops_report.v1"
    assert "llm_commentary" not in saved

    markdown = md_path.read_text(encoding="utf-8")
    assert "# 일일 운영 종합 리포트 — 2026-06-12" in markdown
    assert "## 매매" in markdown
    assert "## 의사결정 게이트" in markdown
    assert "## LLM · AI 스킵" in markdown
    assert "## 뉴스 파이프라인" in markdown
    assert "성공률 85%" in markdown
    assert "CODEX 80건" in markdown


@pytest.mark.asyncio
async def test_llm_commentary_disabled_by_setting(monkeypatch):
    monkeypatch.setattr(
        "services.daily_ops_report_service.settings.DAILY_OPS_REPORT_LLM_ENABLED", False
    )
    service = DailyOpsReportService()
    result = await service.generate_llm_commentary({"report_date": "2026-06-12"})
    assert result is None


@pytest.mark.asyncio
async def test_llm_commentary_included_in_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(
        "services.daily_ops_report_service.settings.DAILY_OPS_REPORT_LLM_ENABLED", True
    )

    async def fake_generate_manual(prompt, system_prompt="", **kwargs):
        assert "운영 데이터(JSON)" in prompt
        return "### 오늘 운영 요약\n정상 운영.", "CLAUDE_API"

    import analysis.llm.llm_factory as llm_mod

    monkeypatch.setattr(llm_mod.llm_factory, "generate_manual", fake_generate_manual)

    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service)

    payload = await service.generate_and_persist(date(2026, 6, 12), include_llm=True)

    assert payload["llm_commentary"]["provider"] == "CLAUDE_API"
    markdown = (tmp_path / "daily_ops_20260612.md").read_text(encoding="utf-8")
    assert "AI 코멘터리" in markdown
    assert "오늘 운영 요약" in markdown


@pytest.mark.asyncio
async def test_llm_commentary_failure_does_not_block_report(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(
        "services.daily_ops_report_service.settings.DAILY_OPS_REPORT_LLM_ENABLED", True
    )

    async def broken_generate_manual(prompt, system_prompt="", **kwargs):
        raise TimeoutError("LLM down")

    import analysis.llm.llm_factory as llm_mod

    monkeypatch.setattr(llm_mod.llm_factory, "generate_manual", broken_generate_manual)

    service = DailyOpsReportService()
    _patch_sections(monkeypatch, service)

    payload = await service.generate_and_persist(date(2026, 6, 12), include_llm=True)

    assert "llm_commentary" not in payload
    assert (tmp_path / "daily_ops_20260612.md").exists()
