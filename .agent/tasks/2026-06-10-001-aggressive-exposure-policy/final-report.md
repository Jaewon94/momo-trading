# Final Report

## Summary

AGGRESSIVE 모드에서 현금 비중이 과도하게 높은 문제는 단일 버그라기보다 정책 소유권이 분리되지 않은 구조 문제였다. `RISK_APPETITE=AGGRESSIVE`는 현금 0%를 허용하는 의도와 한도 조정으로만 쓰였고, 실제 목표 노출을 올리는 레이어가 없었다. 또한 일부 리스크 가드가 `TradeSignal` 수량을 직접 줄이면서도 결과에는 조정 없음처럼 남겨 수량 변경 경로가 불투명했다.

## Changes

- `strategy/exposure_policy.py`를 추가해 AGGRESSIVE+BULL/THEME+최소 신뢰도 조건에서 이미 승인된 BUY 수량만 목표 노출 쪽으로 올리도록 했다.
- 런타임 설정에 `AGGRESSIVE_EXPOSURE_ALIGNMENT_ENABLED`, `AGGRESSIVE_TARGET_EXPOSURE_PCT`, `AGGRESSIVE_MIN_BUY_ORDER_KRW`, `AGGRESSIVE_EXPOSURE_MIN_CONFIDENCE`를 추가했다.
- `TradingAgent`에 노출 보정, 리스크 조정, 브로커 매수가능수량 조정 로그를 추가하고 trade notes에 exposure alignment 메타데이터를 남기도록 했다.
- `RiskManager`가 수량을 줄일 때 `previous_quantity`, `adjusted_quantity`, `adjustments`, `warnings`를 반환하도록 수정했다.
- `docs/architecture/trading-policy-governance.md`를 추가해 정책 우선순위, 소유권, 변경 프로토콜, 충돌 진단 순서를 문서화했다.

## Verification

- `134 passed in 2.20s`
- `git diff --check`: pass
- Secret scan: pass
- Task harness strict check: pass
- Runtime integrity before/after restart: pass
- Server restarted in `tmux` session `momo-trading-server`
- Post-restart status: `AUTONOMOUS`, effective order mode `FULL`, scheduler/agent running
- First post-restart cycle completed at `2026-06-10T11:32:38+09:00`
- Live BUY confirmed: `459550` 알트 2,500주 @ 2,100원
- Live risk-adjustment log confirmed: Tier2 5,000주 -> `NEGATIVE_EXPECTANCY` 0.5배 -> final 2,500주

## Current Runtime Snapshot

- Pending orders: 0
- Current exposure: about 9.1%
- Cash remains high because exposure alignment is progressive and only raises already-approved BUYs. It does not force all cash into the market and does not bypass trading guard, risk manager, or broker checks.
- Account unrealized PnL remains negative at the latest check, driven by open-position mark-to-market moves rather than a runtime blockage.

## Remaining Risks

- The strategy is still below the 25% target exposure because only a limited number of BUYs were approved and safety layers can still reduce sizing.
- Existing strategy expectancy warnings can reduce BUY size by 0.5x; this is now visible but still affects cash deployment.
- The old order WARN for `109740` remains visible in system status, but runtime integrity reports no pending or reconciliation mismatch.
