# Decision Record

## Decision

Add catalog metadata for runtime settings without changing the runtime settings
service or admin API behavior.

## Rationale

- The user concern is policy drift across files. A catalog lets future changes
  identify owner/scope/risk before tuning settings.
- A behavior-preserving metadata layer is lower risk than moving runtime
  validation immediately.

## Deferred

- Admin settings response metadata.
- Generated docs from catalog.
- Making the catalog the source of validation ranges.

## Risks

- Pattern-based classification may be less strict than a fully hand-authored
  catalog. Tests should at least prevent uncataloged mutable settings.
