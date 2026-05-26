# Quality Scorecard

## Context Quality

- Status: pass
- Root cause was traced across scan prompt, deterministic candidate scoring, loss-streak probation settings, and live activity logs.
- Runtime evidence confirmed previous BUY decisions were rejected because overheated candidates violated the active 2~10% probation band.

## Implementation Quality

- Status: pass
- Scanner prompt now prefers mid/long swing candidates and treats STABLE_SHORT/AGGRESSIVE_SHORT as legacy execution/risk labels.
- Candidate scoring now marks policy eligibility and applies the configured preferred change band before LLM selection.
- Active probation now filters overheated LLM selections and can add deterministic policy-compatible candidates for analysis.
- Kiwoom BUY fill inference now avoids recording submitted limit price as fill price when broker holding average gives a better confirmed price source.
- Loss-streak PROBATION is now a reduced-size recovery lane: it no longer hard-blocks just because a holding exists, and repeated-loss pattern or one weak intraday field become warnings instead of hard blocks.
- Hard blocks remain for daily cap, under-min-change, over-max-change, and compound weak intraday confirmation.
- Tier1 stock-analysis prompt now matches the scanner's mid/long policy and clarifies that SHORT is only a tactical exception.
- Intraday holdings check now restores persisted AI exit thresholds into `event_detector` after restart before applying default stop/take fallback.

## Test Quality

- Status: pass
- Focused scanner/scoring tests cover the probation overheat filter and policy-eligible fallback path.
- Broader agent, analysis, and service test suites passed after the change.
- Trading adapter tests cover new BUY fill-price inference for both fresh entries and scale-ins.
- Trading guard tests cover softened PROBATION warnings and retained hard-block cases.
- Stock-analysis prompt test covers mid/long wording and absence of the old short-term specialist phrase.
- Scheduler runtime-path test covers post-restart restoration of persisted stop/take/trailing thresholds.

## Operational Safety

- Status: pass
- No manual broker order, destructive DB action, migration repair, or liquidation action was run.
- Approved runtime DB reconciliation was constrained to one confirmed BUY row, order `0069525`, aligning DB entry price with broker average price.
- Restart verification passed with health OK, scheduler and agent running, one KIWOOM BUY order accepted and confirmed, broker pending orders empty, and runtime integrity OK.
- Live persisted `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` is still `1`; the 11:00 KST cycle confirmed this still blocks a Tier2-approved BUY after today's first confirmed buy. Changing it to the new default `2` is a separate protected runtime setting update.
- After explicit user approval, the protected live runtime setting `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` was aligned from `1` to `2` through the admin confirmation flow.
- Post-restart runtime evidence shows the new Tier1 stock-analysis prompt in live LLM activity and a new `084650` BUY order submitted and confirmed after Tier2 approval and risk-check pass.
- Final restart after threshold-restore change passed health, pending-order, holdings, and runtime-integrity checks.
