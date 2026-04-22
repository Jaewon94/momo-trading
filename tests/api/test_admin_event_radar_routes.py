from datetime import datetime, timedelta
from types import SimpleNamespace


async def test_admin_event_radar_route_returns_ranked_events(client, monkeypatch):
    snapshot = {
        "summary": {
            "total": 3,
            "actionable": 2,
            "cooldown": 1,
            "buy_candidates": 1,
            "sell_candidates": 1,
        },
        "events": [
            {
                "symbol": "215790",
                "name": "이노인스트루먼트",
                "event_type": "TAKE_PROFIT_HIT",
                "event_label": "익절 도달",
                "score": 92,
                "state": "ACTIONABLE",
                "direction": "SELL",
                "occurred_at": "2026-04-03T15:10:00+09:00",
                "cooldown_until": "2026-04-03T15:11:00+09:00",
                "cooldown_remaining_sec": 0,
                "price": 1211,
                "change_rate": 17.38,
                "volume_ratio": 3.6,
                "reason": "목표가 도달",
            },
            {
                "symbol": "065440",
                "name": "현대그린푸드",
                "event_type": "PRICE_SURGE",
                "event_label": "급등",
                "score": 78,
                "state": "TRIGGERED",
                "direction": "BUY",
                "occurred_at": "2026-04-03T14:41:00+09:00",
                "cooldown_until": "2026-04-03T14:42:00+09:00",
                "cooldown_remaining_sec": 12,
                "price": 3031,
                "change_rate": 5.12,
                "volume_ratio": 2.8,
                "reason": "가격 급등",
            },
        ],
    }

    monkeypatch.setattr(
        "api.routes.admin.event_detector",
        SimpleNamespace(get_radar_snapshot=lambda: snapshot),
        raising=False,
    )

    response = await client.get("/api/v1/admin/events/radar")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["actionable"] == 2
    assert payload["events"][0]["symbol"] == "215790"
    assert payload["events"][0]["score"] == 92


async def test_admin_event_radar_route_supports_limit(client, monkeypatch):
    snapshot = {
        "summary": {
            "total": 2,
            "actionable": 2,
            "cooldown": 0,
            "buy_candidates": 1,
            "sell_candidates": 1,
        },
        "events": [
            {"symbol": "111111", "score": 90},
            {"symbol": "222222", "score": 80},
        ],
    }

    monkeypatch.setattr(
        "api.routes.admin.event_detector",
        SimpleNamespace(get_radar_snapshot=lambda: snapshot),
        raising=False,
    )

    response = await client.get("/api/v1/admin/events/radar?limit=1")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload["events"]) == 1
    assert payload["events"][0]["symbol"] == "111111"

