"""Unit tests for OllamaProvider."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.llm.ollama_provider import DEFAULT_OLLAMA_MODELS, OllamaProvider
from core.llm.openai_provider import OpenAICompatibleProvider

# ── Configuration tests ────────────────────────────────────────────────────────

def test_ollama_provider_is_always_configured():
    """OllamaProvider needs no API key — always returns True."""
    provider = OllamaProvider()
    assert provider.is_configured() is True


def test_ollama_provider_inherits_openai_compatible():
    provider = OllamaProvider()
    assert isinstance(provider, OpenAICompatibleProvider)


def test_ollama_provider_default_base_url():
    provider = OllamaProvider()
    assert "localhost:11434" in provider.base_url


def test_ollama_provider_custom_base_url():
    provider = OllamaProvider(base_url="http://myserver:11434/v1")
    assert provider.base_url == "http://myserver:11434/v1"


def test_ollama_provider_reads_base_url_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434/v1")
    provider = OllamaProvider()
    assert provider.base_url == "http://gpu-box:11434/v1"


def test_ollama_provider_default_models():
    provider = OllamaProvider()
    assert provider.get_default_models() == DEFAULT_OLLAMA_MODELS


def test_ollama_provider_custom_models():
    custom = ["phi3:mini", "mistral:7b"]
    provider = OllamaProvider(models=custom)
    assert provider.get_default_models() == custom


def test_ollama_provider_reads_models_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODELS", "phi3:mini, mistral:7b")
    provider = OllamaProvider()
    assert provider.get_default_models() == ["phi3:mini", "mistral:7b"]


def test_ollama_provider_api_key_is_sentinel():
    """Provider should use a sentinel 'ollama' key (not empty) so httpx auth works."""
    provider = OllamaProvider()
    assert provider.api_key == "ollama"


# ── generate_json tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_generate_json_success():
    provider = OllamaProvider(
        base_url="http://localhost:11434/v1",
        models=["qwen2.5-coder:1.5b"],
    )

    fake_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"level": 7}'}}]},
        request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        raw_text, model_used = await provider.generate_json("prompt", "system")

    assert model_used == "qwen2.5-coder:1.5b"
    assert '{"level": 7}' == raw_text


@pytest.mark.asyncio
async def test_ollama_generate_json_fallback():
    provider = OllamaProvider(
        base_url="http://localhost:11434/v1",
        models=["bad-model", "qwen2.5-coder:1.5b"],
    )

    error_resp = httpx.Response(
        404,
        text="model not found",
        request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"),
    )
    success_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"level": 5}'}}]},
        request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [error_resp, success_resp]
        raw_text, model_used = await provider.generate_json("prompt", "system")

    assert model_used == "qwen2.5-coder:1.5b"


@pytest.mark.asyncio
async def test_ollama_generate_json_connection_error():
    provider = OllamaProvider(
        base_url="http://localhost:11434/v1",
        models=["qwen2.5-coder:1.5b"],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Ollama not running")
        with pytest.raises(httpx.ConnectError):
            await provider.generate_json("prompt", "system")
