import pytest
from sqlalchemy.exc import OperationalError

from services.news_reporting_service import NewsReportingService


@pytest.mark.asyncio
async def test_news_reporting_service_returns_empty_storage_snapshot_when_table_missing(monkeypatch):
    service = NewsReportingService()

    async def raise_missing_table(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("no such table: news_items"))

    async def fake_build_summary(_session, *, days: int):
        assert days == 30
        return {
            "baseline": {
                "active": True,
                "effective_date": "2026-04-06",
                "label": "2026-04-06 기준선 리셋 이후 데이터",
                "summary": "현재 브로커 계좌 상태와 복구된 열린 BUY lot를 기준선으로 사용 중",
                "details": ["현재 보유 종목/수량은 브로커 응답 기준"],
            },
            "window": {"days": 30, "trade_count": 0},
            "overall": {},
            "risk_controls": {"news_gate_blocks": 0, "news_rechecks": 0},
            "news_context": {"trade_count": 0, "avg_negative_pressure": 0.0},
            "shadow": {"candidate_count": 0, "blocked_by_news_count": 0},
            "rollout": {
                "status": "HOLDOUT",
                "reason": "표본 부족",
                "details": ["Shadow 후보 0건"],
                "checks": [{"key": "sample", "label": "표본", "passed": False, "actual": "실거래 0건 / Shadow 0건", "target": "각 12건 이상"}],
            },
        }

    async def fake_periodic(_session, *, period: str, size: int):
        assert period in {"weekly", "monthly"}
        assert size > 0
        return {"period": period, "buckets": [{"start": "2026-03-01", "end": "2026-03-08", "metrics": {}}]}

    monkeypatch.setattr(service, "_fetch_recent_items", raise_missing_table)
    monkeypatch.setattr(
        "services.news_reporting_service.performance_reporting_service.build_summary",
        fake_build_summary,
    )
    monkeypatch.setattr(
        "services.news_reporting_service.performance_reporting_service.build_periodic_summary",
        fake_periodic,
    )
    monkeypatch.setattr(
        "services.news_reporting_service.news_runtime_service.get_snapshot",
        lambda *, include_foreign: {
            "overall": {"last_status": "IDLE", "last_message": "대기 중"},
            "sources": {"DART": {"status": "IDLE"}},
        },
    )

    overview = await service.build_overview(object(), recent_limit=5, performance_days=30)

    assert overview["storage"]["ready"] is False
    assert overview["baseline"]["active"] is True
    assert overview["baseline"]["effective_date"] == "2026-04-06"
    assert overview["recent_items"] == []
    assert overview["ingestion"]["total_count"] == 0
    assert overview["ingestion"]["recent_24h_count"] == 0
    assert overview["health"]["status"] == "WARN"
    assert "최근 24시간 신규 적재 0건" in overview["health"]["alerts"]
    assert overview["runtime"]["overall"]["last_status"] == "IDLE"
    assert "news_items" in overview["storage"]["message"]
    assert overview["performance"]["rollout"]["status"] == "HOLDOUT"
    assert overview["performance"]["rollout"]["details"] == ["Shadow 후보 0건"]
    assert overview["performance"]["rollout"]["checks"][0]["key"] == "sample"
    assert overview["periodic"]["weekly"]["period"] == "weekly"
    assert overview["periodic"]["monthly"]["period"] == "monthly"
    assert "shadow_enabled" in overview["settings"]
    assert "rollout_min_sample_size" in overview["settings"]
    assert "rollout_max_drawdown_krw" in overview["settings"]
