# Decision Record

## Decision

- Protect runtime trading/risk setting writes with `APPLY_RUNTIME_SETTINGS` confirmation tokens when the payload includes keys that can change live trading mode, order submission, scheduler behavior, or risk/exit sizing behavior.
- Protect LLM API key add/delete with credential-specific confirmation tokens.
- Protect scheduler start/stop and manual agent cycle trigger with always-on confirmation tokens.
- Keep `/orders` classified as DB-only CRUD for this task because `OrderService.create/cancel` only writes order records and does not submit/cancel broker orders.
- Restore the `portfolio-quick-stats` HTML anchor because the admin layout test still expects that shell contract.

## Rationale

- The earlier fix protected order/reconciliation actions, but additional admin writes could still mutate runtime behavior or credentials without the same server-side contract.
- Token checks are `always=True` on these high-risk routes so persisted `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false` cannot silently bypass them.
- UI calls now generate and attach matching tokens, keeping operator workflows aligned with the backend contract.

## Deferred

- No live DB repair, trade reconciliation apply, or broker-affecting manual action was executed.
- Live lifecycle integrity still depends on existing production data drift and must be handled as a separate repair/operations task.

## Risks

- Running server must be restarted before these route protections are active in the live process.
- Post-restart verification should avoid unsafe POST probes that could execute if an unexpected old server were still serving traffic.
