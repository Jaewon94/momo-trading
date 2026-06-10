# Decision Record

## Decision

Add a metadata-only `strategy/policy/registry.py` and use it to render a
governance documentation section checked by tests.

## Rationale

- The user concern is policy ownership drift across files.
- A registry makes owner/priority/scope/settings/test expectations explicit.
- Docs consistency tests prevent future policy additions from bypassing the
  governance map.

## Deferred

- Registry-driven runtime execution.
- Auto-generating the whole governance document.
- CI wiring beyond existing docs/test harness.

## Risks

- Registry metadata can become stale if new policy owners are added without
  tests; the drift test reduces this risk.
