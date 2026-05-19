from types import SimpleNamespace

from services.candidate_scoring_service import CandidateScoringService


def test_candidate_scoring_service_ranks_buyable_candidates_and_marks_holdings() -> None:
    service = CandidateScoringService()

    result = service.score_candidates(
        volume_rank=[
            {"symbol": "005930", "name": "삼성전자", "price": 71000, "change_rate": 1.2, "volume": 5000000},
            {"symbol": "091990", "name": "셀인비전", "price": 950000, "change_rate": 5.1, "volume": 1200000},
        ],
        surge_data=[
            {"symbol": "042700", "name": "한미반도체", "price": 110000, "change_rate": 14.2, "volume": 2300000},
        ],
        drop_data=[
            {"symbol": "000660", "name": "SK하이닉스", "price": 190000, "change_rate": -4.3, "volume": 1800000},
        ],
        holdings=[SimpleNamespace(symbol="000660", name="SK하이닉스", current_price=190000, pnl_rate=3.4)],
        available_cash=300000,
        max_candidates=4,
    )

    assert [item["symbol"] for item in result] == ["042700", "005930", "000660", "091990"]
    assert result[0]["buyable"] is True
    assert result[0]["strategy_type_hint"] == "AGGRESSIVE_SHORT"
    assert "SURGE_RANK" in result[0]["reason_codes"]
    assert "급등 상위" in result[0]["reasons"]
    assert result[2]["hold_candidate"] is True
    assert result[2]["strategy_type_hint"] == "STABLE_SHORT"
    assert "HOLDING_REVIEW" in result[2]["reason_codes"]
    assert "보유 종목" in result[2]["reasons"]
    assert result[3]["buyable"] is False
    assert "NOT_BUYABLE" in result[3]["reason_codes"]
    assert "1주 매수 불가" in result[3]["reasons"]


def test_candidate_scoring_service_penalizes_recent_non_holding_candidates() -> None:
    service = CandidateScoringService()

    result = service.score_candidates(
        volume_rank=[
            {"symbol": "005930", "name": "삼성전자", "price": 71000, "change_rate": 1.2, "volume": 5000000},
            {"symbol": "042700", "name": "한미반도체", "price": 110000, "change_rate": 2.0, "volume": 4000000},
        ],
        surge_data=[],
        drop_data=[],
        holdings=[SimpleNamespace(symbol="042700", name="한미반도체", current_price=110000, pnl_rate=1.1)],
        available_cash=300000,
        max_candidates=2,
        cooldown_symbols={"005930", "042700"},
    )

    samsung = next(item for item in result if item["symbol"] == "005930")
    holding = next(item for item in result if item["symbol"] == "042700")
    assert "최근 분석/후보 감점" in samsung["reasons"]
    assert "RECENT_CANDIDATE_COOLDOWN" in samsung["reason_codes"]
    assert "최근 분석/후보 감점" not in holding["reasons"]
    assert "RECENT_CANDIDATE_COOLDOWN" not in holding["reason_codes"]
    assert result[0]["symbol"] == "042700"


def test_candidate_scoring_service_penalizes_negative_news_pressure_for_buy_candidates() -> None:
    service = CandidateScoringService()

    result = service.score_candidates(
        volume_rank=[
            {"symbol": "005930", "name": "삼성전자", "price": 71000, "change_rate": 1.2, "volume": 5000000},
            {"symbol": "042700", "name": "한미반도체", "price": 110000, "change_rate": 2.0, "volume": 4000000},
        ],
        surge_data=[],
        drop_data=[],
        holdings=[SimpleNamespace(symbol="042700", name="한미반도체", current_price=110000, pnl_rate=1.1)],
        available_cash=300000,
        max_candidates=2,
        news_pressure_by_symbol={"005930": 0.7, "042700": 0.9},
    )

    samsung = next(item for item in result if item["symbol"] == "005930")
    holding = next(item for item in result if item["symbol"] == "042700")
    assert "뉴스 부정압력 0.70" in samsung["reasons"]
    assert "NEGATIVE_NEWS_PRESSURE" in samsung["reason_codes"]
    assert samsung["strategy_type_hint"] == "STABLE_SHORT"
    assert not any(reason.startswith("뉴스 부정압력") for reason in holding["reasons"])
    assert "NEGATIVE_NEWS_PRESSURE" not in holding["reason_codes"]
    assert samsung["news_negative_pressure"] == 0.7
    assert holding["news_negative_pressure"] == 0.9


def test_candidate_scoring_service_keeps_overheated_surge_stable() -> None:
    service = CandidateScoringService()

    result = service.score_candidates(
        volume_rank=[],
        surge_data=[
            {"symbol": "011000", "name": "진원생명과학", "price": 1120, "change_rate": 29.9, "volume": 40000000},
        ],
        drop_data=[],
        holdings=[],
        available_cash=300000,
        max_candidates=1,
    )

    assert result[0]["strategy_type_hint"] == "STABLE_SHORT"
