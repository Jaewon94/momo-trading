# Decision Record

## Decision

- Use `PROBATION` as the live loss-streak recovery mode instead of `SHADOW`.
- Treat `SHADOW` as report-only in code. It should not prevent analysis or order review by itself.
- Prefer `MID`/`LONG` horizons for AI-driven entries because LLM analysis and broker confirmation latency are poorly matched to ultra-short momentum chasing.
- Keep `SHORT` available only for exceptional, non-overheated momentum cases rather than any aggressive strategy or 6% move.

## Rationale

- On 2026-05-19, the system completed live cycles but placed 0 orders because `LOSS_STREAK_RECOVERY_MODE=SHADOW` was implemented as a hard pre-analysis block.
- The current LLM and broker path can take seconds to tens of seconds, with occasional 90s timeouts. That latency is too high for broad intraday chase entries.
- A capped probation buy keeps recovery possible while limiting loss-streak exposure to small, high-quality entries.
- Longer horizons give the AI more room to be useful: news/context/trend validation matters more over 1+ day decisions than over minute-scale reversals.

## Deferred

- A separate true multi-week/month strategy taxonomy is deferred. Current code still uses `STABLE_SHORT`/`AGGRESSIVE_SHORT` execution profiles, with `MID`/`LONG` horizon metadata and wider risk thresholds.

## Risks

- Reducing short bias may miss some fast intraday winners.
- `PROBATION` still permits live broker buys after a loss streak, though capped. Runtime integrity and order reconciliation must remain green after restart.
- Daemon-mode restart in the current agent shell briefly launched and then lost the uvicorn child without a traceback; the runtime was kept alive by running `bash start.sh` inside `tmux` session `momo-runtime-20260519`.
- One off-hours `INVESTING` news source poll returned an error after restart. Core health, scheduler, agent, settings, holdings, pending orders, and reconciliation remained OK.
