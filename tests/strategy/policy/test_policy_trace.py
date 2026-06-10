from types import SimpleNamespace

from strategy.exposure_policy import ExposureAlignmentDecision
from strategy.policy.trace import (
    from_exit_event,
    from_exposure_alignment,
    from_pre_analysis_gate,
    from_risk_result,
    from_tier1_fast_gate,
    trace_dict,
    with_policy_trace,
)


def test_pre_analysis_gate_trace_blocks_candidate() -> None:
    decision = from_pre_analysis_gate(
        SimpleNamespace(
            approved=False,
            code="BEARISH_PRE_GATE",
            reason="강한 하락 추세",
            detail={"confidence": 0.8},
        )
    )

    trace = trace_dict(decision)

    assert trace["blocked"] is True
    assert trace["decisions"][0]["owner"] == "pre_analysis_gate"
    assert trace["decisions"][0]["scope"] == "CANDIDATE"
    assert trace["decisions"][0]["reason_code"] == "BEARISH_PRE_GATE"
    assert trace["decisions"][0]["metadata"]["confidence"] == 0.8


def test_fast_gate_shadow_trace_observes_without_blocking() -> None:
    decision = from_tier1_fast_gate(
        SimpleNamespace(
            should_skip_tier1=True,
            code="FAST_GATE_HOLD",
            reason="late-day new buy cutoff",
            score=42.0,
            detail={"after_cutoff": True},
        ),
        mode="SHADOW",
    )

    trace = trace_dict(decision)

    assert trace["blocked"] is False
    assert trace["decisions"][0]["action"] == "OBSERVE"
    assert trace["decisions"][0]["metadata"]["would_skip_tier1"] is True


def test_risk_result_trace_captures_quantity_adjustments() -> None:
    decision = from_risk_result(
        {
            "approved": True,
            "reason": "리스크 검사 통과 (수량 조정: 100 → 25)",
            "previous_quantity": 100,
            "adjusted_quantity": 25,
            "adjustments": [
                {
                    "stage": "MAX_POSITION_PCT_CAP",
                    "previous_quantity": 100,
                    "adjusted_quantity": 25,
                    "reason": "비중 한도 적용",
                }
            ],
        },
        input_quantity=100,
    )

    trace = trace_dict(decision)

    assert trace["adjusted"] is True
    effect = trace["decisions"][0]["effects"][0]
    assert effect["field"] == "suggested_quantity"
    assert effect["before"] == 100
    assert effect["after"] == 25
    assert effect["effect_type"] == "REDUCE"


def test_exposure_alignment_trace_captures_quantity_raise() -> None:
    decision = from_exposure_alignment(
        ExposureAlignmentDecision(
            applied=True,
            reason="aggressive_exposure_floor",
            initial_quantity=50,
            final_quantity=200,
            initial_notional=5_000_000,
            final_notional=20_000_000,
            current_exposure_pct=5.0,
            target_exposure_pct=25.0,
            min_order_krw=20_000_000,
            cap_order_krw=50_000_000,
        )
    )

    trace = trace_dict(decision)

    assert trace["decisions"][0]["owner"] == "exposure_alignment"
    assert trace["decisions"][0]["action"] == "ADJUST"
    assert trace["decisions"][0]["effects"][0]["effect_type"] == "RAISE"


def test_exit_event_trace_defers_min_hold_sell() -> None:
    trace = trace_dict(
        from_exit_event(
            event_type="TAKE_PROFIT_HIT",
            blocked=True,
            exit_reason="MIN_HOLD_BLOCK",
            reason="MID 최소 보유 1440분 전 수익보호 매도 보류",
        )
    )

    assert trace["blocked"] is False
    decision = trace["decisions"][0]
    assert decision["owner"] == "holding_exit"
    assert decision["action"] == "DEFER"
    assert decision["reason_code"] == "MIN_HOLD_BLOCK"


def test_with_policy_trace_is_additive() -> None:
    original = {"stage": "TEST"}
    enriched = with_policy_trace(
        original,
        from_pre_analysis_gate(
            SimpleNamespace(approved=True, code="APPROVED", reason="ok", detail={})
        ),
    )

    assert original == {"stage": "TEST"}
    assert enriched["stage"] == "TEST"
    assert enriched["policy_trace"]["decision_count"] == 1
