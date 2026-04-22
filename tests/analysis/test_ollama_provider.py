import httpx
import pytest

from analysis.llm.ollama_provider import OllamaProvider
from trading.enums import LLMTier


@pytest.mark.asyncio
async def test_ollama_provider_generate_uses_http_api(monkeypatch):
    monkeypatch.setattr("analysis.llm.ollama_provider.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("analysis.llm.ollama_provider.settings.OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setattr("analysis.llm.ollama_provider.settings.OLLAMA_MODEL_TIER1", "qwen2.5:7b")

    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["payload"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"response": "로컬 응답"})

    provider = OllamaProvider(
        LLMTier.TIER1,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate("시장 요약", system_prompt="짧게 답변")

    assert result == "로컬 응답"
    assert observed["path"] == "/api/generate"
    assert '"model":"qwen2.5:7b"' in observed["payload"].replace(" ", "")
    assert '"stream":false' in observed["payload"].replace(" ", "")


@pytest.mark.asyncio
async def test_ollama_provider_is_available_when_tags_endpoint_responds(monkeypatch):
    monkeypatch.setattr("analysis.llm.ollama_provider.settings.OLLAMA_BASE_URL", "http://localhost:11434")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})
        return httpx.Response(404)

    provider = OllamaProvider(
        LLMTier.TIER1,
        transport=httpx.MockTransport(handler),
    )

    assert await provider.is_available() is True


def test_ollama_provider_status_snapshot_includes_base_url(monkeypatch):
    monkeypatch.setattr("analysis.llm.ollama_provider.settings.OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    provider = OllamaProvider(LLMTier.TIER2)

    status = provider.status_snapshot()

    assert status["base_url"] == "http://127.0.0.1:11434"
    assert status["model"].startswith("ollama:")
