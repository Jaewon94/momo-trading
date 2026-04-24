from services.llm_runtime_recommendation_service import LLMRuntimeRecommendationService


def test_llm_runtime_recommendation_service_recommends_smaller_news_model_under_pressure(monkeypatch):
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_MODEL", "qwen3:14b")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_MODEL", "qwen3:14b")

    payload = LLMRuntimeRecommendationService().build_recommendations(
        latest_snapshot={
            "memory_percent": 86.0,
            "cpu_load_ratio_1m": 1.25,
            "ollama_rss_mb": 11200.0,
        },
        resource_summary={"peak_ollama_rss_mb": 11200.0},
        llm_summary={"avg_elapsed_ms": 21000.0, "p95_elapsed_ms": 38000.0, "success_rate": 92.0},
        news_poll_summary={"p95_elapsed_ms": 52000.0, "success_rate": 88.0},
        window={"hours": 24},
    )

    assert payload["machine_pressure"]["severity"] == "HIGH"
    assert payload["news_translation"]["action"] == "DOWNGRADE"
    assert payload["news_translation"]["recommended"]["model"] == "qwen3:4b"
    assert payload["ollama_concurrency"]["recommended_parallel_jobs"] == 1


def test_llm_runtime_recommendation_service_keeps_news_model_when_already_at_target(monkeypatch):
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_MODEL", "qwen3:4b")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_MODEL", "gpt-5.4")

    payload = LLMRuntimeRecommendationService().build_recommendations(
        latest_snapshot={
            "memory_percent": 64.0,
            "cpu_load_ratio_1m": 0.25,
            "ollama_rss_mb": 800.0,
        },
        resource_summary={"peak_ollama_rss_mb": 900.0},
        llm_summary={"avg_elapsed_ms": 31000.0, "p95_elapsed_ms": 64000.0, "success_rate": 92.0},
        news_poll_summary={"p95_elapsed_ms": 1600.0, "success_rate": 100.0},
        window={"hours": 24},
    )

    assert payload["news_translation"]["current"]["model"] == "qwen3:4b"
    assert payload["news_translation"]["recommended"]["model"] == "qwen3:4b"
    assert payload["news_translation"]["action"] == "KEEP"


def test_llm_runtime_recommendation_service_can_upgrade_manual_quality_when_stable(monkeypatch):
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_MODEL", "qwen3:4b")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.MANUAL_LLM_MODEL", "qwen3:8b")

    payload = LLMRuntimeRecommendationService().build_recommendations(
        latest_snapshot={
            "memory_percent": 61.0,
            "cpu_load_ratio_1m": 0.42,
            "ollama_rss_mb": 3200.0,
        },
        resource_summary={"peak_ollama_rss_mb": 4200.0},
        llm_summary={"avg_elapsed_ms": 4200.0, "p95_elapsed_ms": 7500.0, "success_rate": 99.0},
        news_poll_summary={"p95_elapsed_ms": 9800.0, "success_rate": 98.0},
        window={"hours": 24},
    )

    assert payload["machine_pressure"]["severity"] == "LOW"
    assert payload["manual_analysis"]["action"] == "UPGRADE"
    assert payload["manual_analysis"]["recommended"]["model"] == "qwen3:14b"
    assert payload["ollama_concurrency"]["recommended_parallel_jobs"] == 1
