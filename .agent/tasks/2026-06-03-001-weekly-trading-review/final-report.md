# Final Report

## Summary

Read-only weekly trading review completed for 2026-06-01 through 2026-06-06 KST.

- Current service/API: healthy.
- Current session: closed/holiday context, no holdings, no pending orders, cash 472,669,543 KRW.
- Current lifecycle/reconciliation: OK after the 2026-06-04 broker ledger repair.
- Weekly closed-trade performance summary: +290,900 KRW gross, +152,446 KRW estimated net after costs, PF 1.255, win rate 57.14%.
- Daily report sum: +294,500 KRW, which differs from the performance summary by 3,600 KRW.

## Main Findings

- The week was not operationally clean, even though the current end state is clean.
- Historical confirmation failures remain: 10 `CONFIRM_FAILED` rows in the 7-day lifecycle window.
- Stale BUY pending patterns blocked later candidate orders on 2026-06-01, 2026-06-02, and 2026-06-05.
- `decision_events` contains fixture-like rows on 2026-06-03 and 2026-06-04, especially repeated `005930` rows with confidence 0 and test-style reasons. These did not map to broker/trade results, but can pollute benchmark metrics.
- A 2026-06-05 scheduled review flagged `fast_gate_score` as an inverted Pre-LLM indicator on a small sample.
- Performance rollout remains `ROLLBACK` because MDD -533,030 KRW exceeded the -500,000 KRW threshold and news-enriched comparison was negative.

## Safety

No broker action, runtime DB mutation, migration, order placement, runtime setting change, cleanup, commit, or push was performed.
