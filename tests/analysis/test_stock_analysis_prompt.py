from analysis.llm.prompts.stock_analysis import STOCK_ANALYSIS_SYSTEM


def test_stock_analysis_system_prompt_prefers_mid_long_swing() -> None:
    assert "중기/장기 스윙 중심" in STOCK_ANALYSIS_SYSTEM
    assert "MID/LONG 보유 가능성" in STOCK_ANALYSIS_SYSTEM
    assert "legacy 실행·위험 프로파일" in STOCK_ANALYSIS_SYSTEM
    assert "단기 매매 전문" not in STOCK_ANALYSIS_SYSTEM
