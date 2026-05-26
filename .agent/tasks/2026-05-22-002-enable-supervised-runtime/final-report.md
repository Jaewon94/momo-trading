# Final Report

## Outcome

- Runtime was enabled and live trading did occur.
- First live cycle completed with 5 analyses and 2 trades.
- A transient lifecycle integrity `FAIL` was observed during order confirmation monitoring, so the runtime was moved back to safe mode.
- Final state is safe/read-only with runtime integrity `OK`.

## Runtime Changes

- Enabled at 2026-05-22 10:49 KST:
  - `TRADING_ENABLED=true`
  - `ORDER_SUBMISSION_MODE=FULL`
  - `AUTONOMY_MODE=AUTONOMOUS`
  - `SCHEDULER_ENABLED=true`
  - `NEWS_POLL_ENABLED=true`
- Safety fallback at 2026-05-22 10:54 KST:
  - `TRADING_ENABLED=false`
  - `ORDER_SUBMISSION_MODE=READ_ONLY`
  - `AUTONOMY_MODE=SEMI_AUTO`
  - `SCHEDULER_ENABLED=false`
- Explicit scheduler stop at 2026-05-22 10:55 KST:
  - `enabled=false`
  - `running=false`

## Observed Trading

- `487240` KODEX AI전력핵심설비:
  - Partial take-profit sell confirmed.
  - 39 shares at 55,690 KRW.
  - Realized lot PnL recorded as +94,224 KRW.
  - Remaining open quantity: 81 shares.
- `307180` 아이엘:
  - Buy confirmed.
  - 300 shares at 9,238 KRW.
- `203400` 에이비온:
  - Buy order was accepted then did not remain as an open position.
  - Confirm-failed count increased, and final reconciliation shows no pending or untracked broker holding.

## Final Verification

- App process: running, PID 60008.
- Final system state:
  - `trading_enabled=false`
  - `autonomy_mode=SEMI_AUTO`
  - `effective_order_submission_mode=DISABLED`
  - `scheduler_running=false`
  - `agent_running=true`
- Final runtime integrity:
  - status `OK`
  - broker pending 0
  - DB pending 0
  - broker-only 0
  - stale DB-only 0
  - quantity mismatch 0
  - pending confirm 0
  - broker untracked holdings 0
- Account snapshot refreshed at 2026-05-22 10:55 KST:
  - total asset 479,344,738 KRW
  - cash 466,792,873 KRW
  - stock value 12,551,865 KRW
  - unrealized PnL 30,896 KRW
  - holding count 4
  - pending order count 0

## Follow-Up Plan

1. Keep autonomous trading disabled until the operator reviews this run.
2. Investigate whether runtime integrity should tolerate very fresh buy confirmations or whether `BUY_ORDER_CONFIRM_WAIT_SEC_MODERATE` should be shortened.
3. Before re-enable, rerun preflight, runtime integrity, lifecycle integrity, and account snapshot refresh.
4. If re-enabled, monitor the first full cycle and immediately fall back to safe mode on any lifecycle or order reconciliation `FAIL`.

## Sources

- SEC Rule 15c3-5 market access risk controls: https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access
- FINRA Regulatory Notice 15-09 algorithmic trading supervision/control practices: https://www.finra.org/industry/notices/15-09
- Kiwoom OpenAPI+ developer guide: https://download.kiwoom.com/web/openapi/kiwoom_openapi_plus_devguide_ver_1.1.pdf
