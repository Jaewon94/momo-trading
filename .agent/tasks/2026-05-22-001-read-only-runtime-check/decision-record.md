# Decision Record

## Decision

Run the application in read-only operational mode before any autonomous or full
order-submission mode is restored.

## Rationale

At the start of the task no server was listening on port 9000, so no automated
trading loop was active. However, persisted runtime settings in the operational
DB had `TRADING_ENABLED=true`, `AUTONOMY_MODE=AUTONOMOUS`,
`ORDER_SUBMISSION_MODE=FULL`, `SCHEDULER_ENABLED=true`, and `NEWS_POLL_ENABLED=true`.
Those persisted settings are applied during FastAPI startup and override the
safer `.env` values.

Because the check was performed during KRX regular trading hours, starting the
normal entrypoint without lowering those persisted values could have re-enabled
automated scan/order paths. The safer path was to back up the DB, set runtime
controls to read-only, then verify startup and read-only broker/API health.

## Deferred

Restoring autonomous trading, full order submission, scheduler jobs, or news
polling is deferred until separately approved.

## Risks

The app is running and broker read-only access works, including holdings and
polling fallback price reads. Account snapshot freshness remains `STALE`, so
the system reports that automatic-session new buys should remain blocked until
the account snapshot is refreshed.
