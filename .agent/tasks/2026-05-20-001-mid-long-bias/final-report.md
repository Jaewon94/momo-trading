# Final Report

## Summary

- Corrected the priority: mid/long-horizon operation is the primary strategy direction; loss-streak recovery is secondary.
- `SHORT` horizon is now a rare tactical exception only for high-confidence aggressive surge/volume momentum in bull/theme regimes.
- `MID` is the default, and `LONG` is used for high-confidence bull/theme setups without spike/drop tactical triggers.
- Aggressive candidate hints now require both surge and volume-rank evidence, moderate 6~10% movement, sufficient score, and low news pressure.
- Legacy `STABLE_SHORT`/`AGGRESSIVE_SHORT` names are now documented in prompts/metadata as execution/risk profiles, not desired holding horizons.
- Holding policy now uses `trade_horizon` from trade notes first, with hold windows SHORT 5, MID 15, LONG 30, STABLE fallback 15, AGGRESSIVE fallback 10.

## Verification

- Changed-module py_compile: passed.
- Focused horizon/scoring/profile/holding tests: `21 passed`.
- Agent cycle and scheduler runtime path regression tests: `113 passed`.
- Standard task harness verification: passed.
- Runtime restart: app is running in tmux session `momo-runtime-20260520b`, PID `31799`, health endpoint OK.
- Runtime integrity: system/settings/order reconciliation/status all OK; broker pending 0, DB pending 0, quantity mismatch 0, broker untracked holdings 0.

## Residual

- Local `.env` was updated because it was overriding hold days to STABLE 5 / AGGRESSIVE 3. `.env` is ignored by git; `.env.example` was updated for reproducibility.
- Strategy type names remain unchanged for DB/report compatibility.
