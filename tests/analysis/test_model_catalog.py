import httpx
import pytest

from analysis.llm.model_catalog import ModelCatalogService


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response | None = None, error: Exception | None = None, **kwargs):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, path: str) -> httpx.Response:
        if self._error is not None:
            raise self._error
        assert path == "/api/tags"
        assert self._response is not None
        return self._response


@pytest.mark.asyncio
async def test_build_catalog_includes_ollama_provider(monkeypatch):
    service = ModelCatalogService()

    async def fake_claude_catalog():
        return {"id": "CLAUDE_CODE", "entries": []}

    async def fake_codex_catalog():
        return {"id": "CODEX", "entries": []}

    async def fake_ollama_catalog():
        return {"id": "OLLAMA", "entries": [{"value": "DEFAULT"}]}

    monkeypatch.setattr(service, "_build_claude_catalog", fake_claude_catalog)
    monkeypatch.setattr(service, "_build_codex_catalog", fake_codex_catalog)
    monkeypatch.setattr(service, "_build_ollama_catalog", fake_ollama_catalog)

    catalog = await service._build_catalog()

    assert [provider["id"] for provider in catalog["providers"]] == [
        "CLAUDE_CODE",
        "CODEX",
        "OLLAMA",
    ]


def test_fallback_catalog_includes_ollama_seed():
    service = ModelCatalogService()

    catalog = service.fallback_catalog("runtime unavailable")

    assert catalog["stale"] is True
    assert catalog["fetch_error"] == "runtime unavailable"
    assert [provider["id"] for provider in catalog["providers"]] == [
        "CLAUDE_CODE",
        "CODEX",
        "OLLAMA",
    ]
    ollama = next(provider for provider in catalog["providers"] if provider["id"] == "OLLAMA")
    assert [entry["value"] for entry in ollama["entries"]] == ["DEFAULT"]


@pytest.mark.asyncio
async def test_build_ollama_catalog_includes_runtime_models(monkeypatch):
    service = ModelCatalogService()

    monkeypatch.setattr(
        "analysis.llm.model_catalog.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(
            response=httpx.Response(
                200,
                request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"),
                json={
                    "models": [
                        {"name": "qwen2.5:14b"},
                        {"name": "llama3.1:8b"},
                    ]
                },
            )
        ),
    )

    catalog = await service._build_ollama_catalog()

    assert catalog["id"] == "OLLAMA"
    assert catalog["custom_value_supported"] is True
    assert [entry["value"] for entry in catalog["entries"]] == [
        "DEFAULT",
        "qwen2.5:14b",
        "llama3.1:8b",
    ]


@pytest.mark.asyncio
async def test_build_ollama_catalog_falls_back_when_runtime_unavailable(monkeypatch):
    service = ModelCatalogService()

    monkeypatch.setattr(
        "analysis.llm.model_catalog.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(error=httpx.ConnectError("connection refused")),
    )

    catalog = await service._build_ollama_catalog()

    assert catalog["id"] == "OLLAMA"
    assert [entry["value"] for entry in catalog["entries"]] == ["DEFAULT"]
    assert catalog["warnings"]
    assert "unavailable" in catalog["warnings"][0]
