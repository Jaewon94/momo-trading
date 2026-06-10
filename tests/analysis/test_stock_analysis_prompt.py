from analysis.llm.prompts.stock_analysis import STOCK_ANALYSIS_SYSTEM


def test_stock_analysis_system_prompt_respects_target_horizon() -> None:
    assert "호라이즌별 트레이딩 애널리스트" in STOCK_ANALYSIS_SYSTEM
    assert "target_horizon_hint가 SHORT/MID/LONG으로 제공되면 해당 호라이즌을 우선" in STOCK_ANALYSIS_SYSTEM
    assert "target_horizon_hint가 UNSPECIFIED이면 MID/LONG 보유 가능성" in STOCK_ANALYSIS_SYSTEM
    assert "SHORT 후보는 장중 유동성" in STOCK_ANALYSIS_SYSTEM
    assert "legacy 실행·위험 프로파일" in STOCK_ANALYSIS_SYSTEM
    assert "단기 매매 전문" not in STOCK_ANALYSIS_SYSTEM
