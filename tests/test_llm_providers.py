"""Unit tests for LLM providers: GeminiProvider and OpenAICompatibleProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.llm.base import BaseLLMProvider
from core.llm.gemini_provider import GeminiProvider
from core.llm.openai_provider import OpenAICompatibleProvider


def test_base_llm_provider_abstract():
    class IncompleteProvider(BaseLLMProvider):
        pass

    with pytest.raises(TypeError):
        IncompleteProvider()


def test_gemini_provider_is_configured_and_defaults():
    p1 = GeminiProvider(api_key="")
    assert p1.is_configured() is False

    p2 = GeminiProvider(api_key="valid-key", models=["model-a", "model-b"])
    assert p2.is_configured() is True
    assert p2.get_default_models() == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_gemini_provider_not_configured_raises():
    provider = GeminiProvider(api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        await provider.generate_json("prompt", "system")


@pytest.mark.asyncio
async def test_gemini_provider_generate_json_success():
    provider = GeminiProvider(api_key="fake-key", models=["model-1"])

    mock_client = MagicMock()
    mock_resp = MagicMock(text='{"result": "ok"}')
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        text, model_used = await provider.generate_json("test prompt", "test sys")
        assert text == '{"result": "ok"}'
        assert model_used == "model-1"


@pytest.mark.asyncio
async def test_gemini_provider_generate_json_fallback_and_all_fail():
    provider = GeminiProvider(api_key="fake-key", models=["model-1", "model-2"])

    mock_client = MagicMock()
    mock_resp_success = MagicMock(text='{"recovered": true}')

    # Model 1 fails with 503, Model 2 succeeds
    mock_client.models.generate_content.side_effect = [
        Exception("503 Service Unavailable"),
        mock_resp_success,
    ]

    with patch("google.genai.Client", return_value=mock_client):
        text, model_used = await provider.generate_json("test prompt", "test sys")
        assert text == '{"recovered": true}'
        assert model_used == "model-2"

    # All models fail
    mock_client.models.generate_content.side_effect = Exception("All quota exceeded")
    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(Exception, match="All quota exceeded"):
            await provider.generate_json("test prompt", "test sys")


def test_openai_provider_is_configured_and_defaults():
    p1 = OpenAICompatibleProvider(api_key="")
    assert p1.is_configured() is False

    p2 = OpenAICompatibleProvider(api_key="sk-test", base_url="https://api.openai.com/v1/")
    assert p2.is_configured() is True
    assert p2.base_url == "https://api.openai.com/v1"
    assert "gpt-4o" in p2.get_default_models()


@pytest.mark.asyncio
async def test_openai_provider_not_configured_raises():
    provider = OpenAICompatibleProvider(api_key="")
    with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
        await provider.generate_json("prompt", "system")


@pytest.mark.asyncio
async def test_openai_provider_generate_json_success():
    provider = OpenAICompatibleProvider(api_key="sk-test", models=["gpt-4o-mini"])

    fake_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"status": "success"}'}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        content, model_used = await provider.generate_json("prompt", "system")
        assert content == '{"status": "success"}'
        assert model_used == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_provider_fallback_and_all_fail():
    provider = OpenAICompatibleProvider(api_key="sk-test", models=["model-1", "model-2"])

    resp_error = httpx.Response(
        500,
        text="Internal Server Error",
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    resp_success = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    # First model 500 error, second model succeeds
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_error, resp_success]
        content, model_used = await provider.generate_json("prompt", "system")
        assert content == '{"ok": true}'
        assert model_used == "model-2"

    # All models fail
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Network unreachable")
        with pytest.raises(Exception):
            await provider.generate_json("prompt", "system")


def test_llm_factory():
    from core.llm.factory import LLMProviderFactory

    p_gemini = LLMProviderFactory.create("gemini", api_key="test-key")
    assert isinstance(p_gemini, GeminiProvider)

    p_openai = LLMProviderFactory.create("openai", api_key="test-key")
    assert isinstance(p_openai, OpenAICompatibleProvider)

    p_deepseek = LLMProviderFactory.create("deepseek", api_key="test-key")
    assert isinstance(p_deepseek, OpenAICompatibleProvider)

    # Unknown provider falls back to Gemini
    p_unknown = LLMProviderFactory.create("unknown_provider", api_key="test-key")
    assert isinstance(p_unknown, GeminiProvider)
