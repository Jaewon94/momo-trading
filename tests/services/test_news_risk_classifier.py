import pytest


def test_news_risk_classifier_flags_trading_suspension_disclosures():
    from services.news_risk_classifier import NewsRiskClassifier

    result = NewsRiskClassifier().classify({
        "source_code": "DART",
        "title": "신한제11호스팩 · 주권매매거래정지 (상장폐지 사유발생)",
        "metadata": {
            "report_nm": "주권매매거래정지 (상장폐지 사유발생)",
        },
    })

    assert result is not None
    assert result.sentiment_label == "NEGATIVE"
    assert result.sentiment_score <= 0.16
    assert result.impact_score >= 0.9
    assert "trading_suspension" in result.reason_codes


def test_news_risk_classifier_preserves_explicit_sentiment():
    from services.news_risk_classifier import NewsRiskClassifier

    result = NewsRiskClassifier().classify({
        "source_code": "DART",
        "title": "삼성전자 공급 계약 체결",
        "sentiment_label": "POSITIVE",
        "sentiment_score": 0.72,
        "impact_score": 0.61,
    })

    assert result is None


@pytest.mark.parametrize(
    ("title", "reason_code"),
    [
        ("이니텍 · 불성실공시법인지정예고 (공시불이행)", "unfaithful_disclosure"),
        ("에스아이리소스 · 소송등의제기ㆍ신청(경영권분쟁소송)", "management_dispute"),
        ("하이드로리튬 · 주요사항보고서(전환사채권발행결정)", "dilution_financing"),
    ],
)
def test_news_risk_classifier_scores_common_disclosure_risks(title, reason_code):
    from services.news_risk_classifier import NewsRiskClassifier

    result = NewsRiskClassifier().classify({
        "source_code": "DART",
        "title": title,
    })

    assert result is not None
    assert result.sentiment_label == "NEGATIVE"
    assert result.sentiment_score < 0.5
    assert result.impact_score > 0.0
    assert reason_code in result.reason_codes
