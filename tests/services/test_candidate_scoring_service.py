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
    assert "급등 상위" in result[0]["reasons"]
    assert result[2]["hold_candidate"] is True
    assert "보유 종목" in result[2]["reasons"]
    assert result[3]["buyable"] is False
    assert "1주 매수 불가" in result[3]["reasons"]

