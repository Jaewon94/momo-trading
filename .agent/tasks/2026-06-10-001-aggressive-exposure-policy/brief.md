# Brief

## Metadata

- Task ID: `2026-06-10-001-aggressive-exposure-policy`
- Created: `2026-06-10T11:01:52+09:00`
- Repo: `momo-trading`
- Title: Aggressive exposure policy alignment

## Goal

공격적 리스크 성향에서 현금 활용률이 과도하게 낮아지는 정책 충돌을 진단하고, 노출 목표/수량 보정/정책 충돌 관측을 일관되게 설계·구현·검증한다.

## Scope

In scope:

- Diagnose why AGGRESSIVE mode still leaves excessive cash idle.
- Define a policy hierarchy for risk appetite, exposure targets, safety gates, and broker constraints.
- Add an aggressive exposure alignment policy that can raise already-approved BUY quantities toward a target exposure.
- Preserve hard safety gates: kill switch, drawdown blocks, risk manager, buying-power checks, and broker order submission.
- Add observability for quantity adjustments so future conflicts show where the quantity changed.
- Add focused tests for policy behavior and runtime setting validation.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Local runtime logs and admin APIs: latest cycle showed AGGRESSIVE limits were open, but candidate approval and quantity stages produced low exposure.
- Local code paths: `ai_risk_tuner`, `trading_guard`, `risk_manager`, `trading_agent`, `decision_maker`, broker buying-power checks, and runtime settings.
- Automated-trading control best practice: keep hard risk controls and post-trade monitoring; do not solve exposure by removing kill switches or broker safety gates.
- Stop/order and position-sizing references from the preceding strategy task: wider stops require size/risk budget control, so exposure alignment must not bypass risk manager.

Plan implications:

- Adopt: introduce an explicit AGGRESSIVE exposure alignment layer after AI approval and before risk-manager checks.
- Adopt: default target exposure 25%, minimum approved BUY order 20,000,000 KRW, and minimum confidence 0.65 in BULL/THEME regimes.
- Adopt: make risk manager and broker buying-power reductions visible in activity logs.
- Adopt: pass exposure alignment metadata through trade notes for later audit.
- Defer: full UI form layout for the new exposure settings; API/runtime settings support is enough for this task.
- Reject: forcing cash fully invested or bypassing loss/drawdown/broker controls.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Add task-specific commands here.
