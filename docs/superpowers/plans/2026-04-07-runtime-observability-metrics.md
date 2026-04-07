# Runtime Observability Metrics Plan

## Goal

Store low-cardinality operational metrics that help answer:

- Is the app slow because of system pressure or a specific job?
- Are Ollama-backed translations succeeding, retrying, or falling back?
- Is the news pipeline keeping up, or building backlog?

## Principles

- Keep event logs and metrics separate.
- Prefer low-cardinality fields for long-term querying.
- Store one row per resource snapshot and one row per completed execution unit.
- Record summaries, not full prompts/responses, in metrics tables.

## Initial Scope

- `resource_snapshots`
  - host / app / environment / python / OS / arch / pid / cpu count
  - load averages and normalized load ratios
  - total/used/available memory and memory percent
  - swap used
  - total/used/available disk and disk used percent
  - app RSS
  - Ollama RSS, running state, pid count
- `execution_metrics`
  - `LLM_CALL / LLM_GENERATE`
  - `JOB / NEWS_POLL`

## Why This Fits Momo Trading

- Ollama latency is materially relevant to foreign-news translation.
- News polling is a batch pipeline with clear throughput and error counters.
- Scheduler-driven resource snapshots help correlate machine pressure with missed or slow jobs.
- Machine metadata lets us compare results after local runtime, Python, or hardware changes.

## Best-Practice Notes

- Use low-cardinality labels/fields for aggregate queries.
- Separate resource telemetry from request/job telemetry.
- Prefer RED-style job metrics and USE-style resource metrics.

## Near-Term Follow-Ups

- Add retention/cleanup for old raw metrics.
- Add read API and admin charts for hourly rollups.
- Add backlog and scheduler-lag metrics.
