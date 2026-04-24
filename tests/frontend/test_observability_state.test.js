import { describe, expect, test } from "vitest";

import { buildObservabilityDashboardState } from "../../admin/static/js/observability_state.js";

describe("observability_state", () => {
  test("builds cards, charts, and breakdown rows", () => {
    const state = buildObservabilityDashboardState({
      latest_snapshot: {
        host: "mac-local",
        app_name: "momo-trading",
        environment: "local",
        python_version: "3.13.12",
        platform_system: "Darwin",
        platform_machine: "arm64",
        memory_percent: 62.4,
        cpu_load_ratio_1m: 0.82,
        app_rss_mb: 220,
        ollama_rss_mb: 4096,
        ollama_running: true,
      },
      resource_summary: {
        latest_collected_at: "2026-04-08T00:12:00+09:00",
        avg_memory_percent: 60.1,
        peak_memory_percent: 64.2,
        avg_cpu_load_ratio_1m: 0.73,
        peak_cpu_load_ratio_1m: 1.15,
        peak_app_rss_mb: 240,
        peak_ollama_rss_mb: 4200,
      },
      resource_series: [
        { created_at: "2026-04-08T00:00:00+09:00", cpu_load_ratio_1m: 0.5, memory_percent: 58, app_rss_mb: 180, ollama_rss_mb: 3800 },
        { created_at: "2026-04-08T00:10:00+09:00", cpu_load_ratio_1m: 0.82, memory_percent: 62.4, app_rss_mb: 220, ollama_rss_mb: 4096 },
      ],
      llm: {
        total_calls: 3,
        success_rate: 66.7,
        p95_elapsed_ms: 2200,
        provider_breakdown: [
          { provider: "OLLAMA", calls: 3, success_rate: 66.7, avg_elapsed_ms: 1800, p95_elapsed_ms: 2200, fallback_rate: 33.3 },
        ],
      },
      ai_skipped: {
        total_skipped: 2,
        by_stage: [{ stage: "HOLDINGS_PRECHECK", count: 2 }],
        by_reason: [
          { stage: "HOLDINGS_PRECHECK", reason_code: "HOLD", count: 1 },
          { stage: "HOLDINGS_PRECHECK", reason_code: "SELL", count: 1 },
        ],
        recent: [
          {
            created_at: "2026-04-08T00:24:00+09:00",
            stage: "HOLDINGS_PRECHECK",
            reason_code: "HOLD",
            skipped_tier: "TIER1",
            symbol: "005930",
            source: "HOLDING_POLICY",
            reason: "명확한 HOLD 사전판단",
          },
        ],
      },
      window: {
        hours: 168,
        resolution: "hourly_rollup",
      },
      trends: {
        llm: [
          { created_at: "2026-04-07T21:00:00+09:00", calls: 2, avg_elapsed_ms: 1600, success_rate: 50 },
          { created_at: "2026-04-08T00:00:00+09:00", calls: 1, avg_elapsed_ms: 2200, success_rate: 100 },
        ],
        news_poll: [
          { created_at: "2026-04-07T21:00:00+09:00", runs: 2, avg_elapsed_ms: 4800, created_total: 4, error_total: 1 },
          { created_at: "2026-04-08T00:00:00+09:00", runs: 2, avg_elapsed_ms: 5600, created_total: 5, error_total: 1 },
        ],
      },
      jobs: {
        news_poll: {
          runs: 4,
          success_rate: 75,
          avg_elapsed_ms: 5200,
          p95_elapsed_ms: 6800,
          received_total: 20,
          created_total: 9,
          source_error_total: 2,
          status_breakdown: [{ status: "SUCCESS", count: 3 }],
        },
        maintenance: {
          runs: 5,
          success_rate: 100,
          last_run_at: "2026-04-08T00:20:00+09:00",
          last_status: "SUCCESS",
          last_elapsed_ms: 380,
          last_deleted_resource_rows: 12,
          last_deleted_execution_rows: 3,
          last_resource_rollups_created: 4,
          last_execution_rollups_created: 6,
        },
      },
      storage: {
        raw_retention_days: 30,
        rollup_retention_days: 365,
        rollup_lookback_hours: 72,
        resource_rollup_buckets: 18,
        execution_rollup_buckets: 22,
      },
      recommendations: {
        machine_pressure: {
          severity: "MEDIUM",
          reasons: ["메모리 사용률 62.4%"],
        },
        news_translation: {
          action: "DOWNGRADE",
          recommended: { provider: "OLLAMA", model: "qwen3:8b" },
          reasons: ["장중 안정성을 위해 8b 이하 권장"],
        },
        manual_analysis: {
          action: "KEEP",
          recommended: { provider: "CLAUDE_CODE", model: "DEFAULT" },
          reasons: ["수동 분석은 현재 고품질 provider 유지 권장"],
        },
        ollama_concurrency: {
          recommended_parallel_jobs: 1,
          reasons: ["8b 이상 또는 일반 상태에서는 동시 실행 1개 권장"],
        },
      },
      errors: {
        recent: [
          {
            created_at: "2026-04-08T00:22:00+09:00",
            component: "scheduler",
            operation: "news_poll",
            severity: "ERROR",
            exception_type: "RuntimeError",
            exception_message: "poll failed",
          },
        ],
        incidents: [
          {
            fingerprint: "incident-1",
            title: "scheduler · news_poll · RuntimeError",
            severity: "ERROR",
            status: "OPEN",
            occurrence_count: 3,
            last_seen_at: "2026-04-08T00:22:00+09:00",
            last_message: "poll failed",
            owner_note: "watch tonight",
          },
        ],
      },
    });

    expect(state.machine.host).toBe("mac-local");
    expect(state.window).toMatchObject({ hours: 168, resolution: "hourly_rollup" });
    expect(state.summaryCards[0].value).toBe("62.4%");
    expect(state.summaryCards[4].help).toContain("호출 3회");
    expect(state.summaryCards[5]).toMatchObject({ label: "AI 스킵", value: "2회" });
    expect(state.summaryCards[7]).toMatchObject({ label: "Raw 보존", value: "30일" });
    expect(state.summaryCards[8]).toMatchObject({ label: "Hourly Rollup", value: "22개" });
    expect(state.maintenanceRows[1]).toMatchObject({ label: "최근 상태", value: "SUCCESS" });
    expect(state.maintenanceRows[4]).toMatchObject({ label: "최근 raw 정리", value: "15건" });
    expect(state.recommendationCards[0]).toMatchObject({ label: "머신 압박", value: "MEDIUM" });
    expect(state.recommendationCards[1]).toMatchObject({ label: "뉴스 번역 추천", value: "OLLAMA / qwen3:8b" });
    expect(state.recentErrors[0]).toMatchObject({ title: "scheduler · news_poll" });
    expect(state.incidentRows[0]).toMatchObject({
      fingerprint: "incident-1",
      title: "scheduler · news_poll · RuntimeError",
      status: "OPEN",
      ownerNote: "watch tonight",
    });
    expect(state.resourceCharts[0].line.path.startsWith("M")).toBe(true);
    expect(state.trendCharts[0]).toMatchObject({ label: "LLM Avg Latency", meta: "호출 3회" });
    expect(state.trendCharts[3]).toMatchObject({ label: "News Created", meta: "생성 9건" });
    expect(state.providerRows[0]).toMatchObject({ provider: "OLLAMA", calls: "3회" });
    expect(state.aiSkippedRows[0]).toMatchObject({ stage: "HOLDINGS_PRECHECK", reasonCode: "HOLD", count: "1회" });
    expect(state.aiSkippedRecentRows[0]).toMatchObject({ title: "HOLDINGS_PRECHECK · HOLD · 005930" });
    expect(state.newsRows[4]).toMatchObject({ label: "생성 기사", value: "9건" });
    expect(state.statusRows[0]).toMatchObject({ status: "SUCCESS", count: "3회" });
  });
});
