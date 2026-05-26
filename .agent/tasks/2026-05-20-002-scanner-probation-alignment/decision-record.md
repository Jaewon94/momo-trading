# Decision Record

## Decision

Keep the final trading guard strict and fix the upstream scanner. The scanner will prefer
moderate mid/long-compatible buy candidates, penalize overheated moves, and filter LLM
BUY selections that violate active loss-streak PROBATION change-rate limits.

Keep the consecutive-loss guard, but change PROBATION from a near-hard lock to a reduced-size
recovery lane. Under PROBATION, daily cap and 2~10% change-rate limits still hard-block buys;
compound weak intraday confirmation still blocks buys; holding an existing position, a
repeated-loss pattern, or one weak intraday component now becomes warning metadata with reduced
position sizing instead of an outright block.

## Rationale

The observed runtime issue was not order submission failure. Tier2 produced BUY decisions,
but the final guard correctly rejected candidates with +11.83% and +21.14% moves while
the account was in PROBATION, whose allowed recovery band is +2% to +10%.

Prompt-only control is insufficient because the existing market-scan prompt still asked
for 1-5 day short-term candidates and AGGRESSIVE_SHORT expansion. Deterministic post-LLM
enforcement is needed so the scanner cannot keep feeding candidates the risk guard will
reject.

The user's concern about release difficulty was valid. Consecutive losses only reset when a
closed winning BUY exists, while the previous PROBATION rules also blocked when any holding
existed and blocked on a single weak intraday field. That can create a feedback loop where the
bot is nominally in recovery mode but cannot take enough controlled recovery attempts.

External control guidance supports keeping automated-trading risk controls, but the practical
engineering requirement is that the controls be calibrated, tested, and monitored rather than
configured as an accidental deadlock.

## Deferred

Broader alpha/factor selection, multi-day backtesting, and external data provider changes
are deferred. This task is a consistency fix between existing scanner, LLM selection, and
loss-streak recovery policy.

Changing the live persisted runtime setting `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` from 1 to 2
is deferred until explicit admin-confirmed approval, because it is a protected runtime risk
setting. Code defaults and `.env.example` now use 2.

## Follow-up Decision

After explicit user approval on 2026-05-20, align the protected live runtime setting
`LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` from 1 to 2 using the admin confirmation flow. This
removes the code-vs-runtime mismatch that blocked the 11:00 KST Tier2-approved BUY after the
first confirmed buy.

Also align the Tier1 stock-analysis system prompt with the scanner prompt. The previous Tier1
prompt still described the agent as a short-term trading analyst, which conflicted with the
mid/long scanner policy and with `horizon_policy` metadata. The new prompt makes MID/LONG the
default analysis horizon and treats SHORT as a rare tactical exception while preserving the
legacy `STABLE_SHORT` and `AGGRESSIVE_SHORT` execution/risk labels.

Restore persisted AI exit thresholds during intraday holdings checks. `event_detector` keeps
stop/take/trailing thresholds in memory, but confirmed open trades persist AI stop/take values
in the database. After a market-hours restart, existing holdings can otherwise be monitored with
default stop/take rules until the next premarket restore. Holdings check now restores missing
in-memory thresholds from the open TradeResult before evaluating sell/default-fallback logic.

## Risks

The scanner may return fewer BUY candidates while the market is dominated by overheated
stocks. That is intentional under PROBATION, but it can reduce trade frequency. Runtime
verification after restart should confirm the system stays healthy and the new policy is
visible in scan logs.

While the persisted runtime cap remains 1, today's first confirmed buy can still prevent
additional same-day PROBATION buys even though the code path now supports the softer default
of 2. This was observed in the 11:00 KST cycle: Tier2 approved a BUY for `084650`, but the
final risk check blocked it on `probation 일일 매수 한도 도달 (1/1)`.

This risk was closed operationally after user approval: live settings now report
`LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS=2`, and the post-restart 14:59 KST cycle placed a
new reduced-size BUY order for `084650` after Tier2 approval and risk-check pass.

The threshold-restore change affects sell monitoring semantics by preserving the AI values that
were already persisted with confirmed positions. It does not loosen exits or add a new sell
condition; it prevents restarts from silently downgrading positions to default thresholds.
