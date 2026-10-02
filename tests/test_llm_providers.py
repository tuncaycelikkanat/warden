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
        with pytest.raises(httpx.ConnectError):
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


def test_llm_factory_anthropic():
    from core.llm.anthropic_provider import AnthropicProvider
    from core.llm.factory import LLMProviderFactory

    p_anthropic = LLMProviderFactory.create("anthropic", api_key="sk-ant-test")
    assert isinstance(p_anthropic, AnthropicProvider)

    p_claude = LLMProviderFactory.create("claude", api_key="sk-ant-test")
    assert isinstance(p_claude, AnthropicProvider)


def test_llm_factory_ollama():
    from core.llm.factory import LLMProviderFactory
    from core.llm.ollama_provider import OllamaProvider

    p_ollama = LLMProviderFactory.create("ollama")
    assert isinstance(p_ollama, OllamaProvider)
    # Ollama is always configured (no real API key needed)
    assert p_ollama.is_configured() is True


def test_llm_factory_groq_and_openrouter():
    from core.llm.factory import LLMProviderFactory

    p_groq = LLMProviderFactory.create("groq", api_key="gsk-test")
    assert isinstance(p_groq, OpenAICompatibleProvider)

    p_openrouter = LLMProviderFactory.create("openrouter", api_key="or-test")
    assert isinstance(p_openrouter, OpenAICompatibleProvider)


# ── LLMConfig panelist/confidence tests ───────────────────────────────────────

def test_llm_config_panelist_mode_default():
    from core.config.llm_config import LLMConfig
    cfg = LLMConfig()
    assert cfg.panelist_mode is False
    assert cfg.confidence_threshold == 0.5


def test_llm_config_panelist_mode_from_env_true(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_PANELIST_MODE", "true")
    cfg = LLMConfig.from_env()
    assert cfg.panelist_mode is True


def test_llm_config_panelist_mode_from_env_false(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_PANELIST_MODE", "false")
    cfg = LLMConfig.from_env()
    assert cfg.panelist_mode is False


def test_llm_config_confidence_threshold_from_env(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_CONFIDENCE_THRESHOLD", "0.75")
    cfg = LLMConfig.from_env()
    assert cfg.confidence_threshold == pytest.approx(0.75)


def test_llm_config_confidence_threshold_clamped_to_1(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_CONFIDENCE_THRESHOLD", "2.5")
    cfg = LLMConfig.from_env()
    assert cfg.confidence_threshold == 1.0


def test_llm_config_confidence_threshold_clamped_to_0(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_CONFIDENCE_THRESHOLD", "-1.0")
    cfg = LLMConfig.from_env()
    assert cfg.confidence_threshold == 0.0


def test_llm_config_confidence_threshold_invalid_falls_back(monkeypatch):
    from core.config.llm_config import LLMConfig
    monkeypatch.setenv("WARDEN_LLM_CONFIDENCE_THRESHOLD", "not-a-float")
    cfg = LLMConfig.from_env()
    assert cfg.confidence_threshold == 0.5
