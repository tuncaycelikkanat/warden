"""Unit tests for AnthropicProvider."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.llm.anthropic_provider import (
    ANTHROPIC_API_URL,
    DEFAULT_ANTHROPIC_MODELS,
    AnthropicProvider,
)

# ── Configuration tests ────────────────────────────────────────────────────────

def test_anthropic_provider_not_configured_when_empty_key():
    provider = AnthropicProvider(api_key="")
    assert provider.is_configured() is False


def test_anthropic_provider_not_configured_when_whitespace_key():
    provider = AnthropicProvider(api_key="   ")
    assert provider.is_configured() is False


def test_anthropic_provider_configured_with_valid_key():
    provider = AnthropicProvider(api_key="sk-ant-valid-key")
    assert provider.is_configured() is True


def test_anthropic_provider_default_models():
    provider = AnthropicProvider(api_key="key")
    assert provider.get_default_models() == DEFAULT_ANTHROPIC_MODELS


def test_anthropic_provider_custom_models():
    custom = ["claude-3-opus-20240229"]
    provider = AnthropicProvider(api_key="key", models=custom)
    assert provider.get_default_models() == custom


def test_anthropic_provider_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    provider = AnthropicProvider()
    assert provider.api_key == "env-key-123"
    assert provider.is_configured() is True


def test_anthropic_provider_no_env_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider()
    assert provider.is_configured() is False


# ── generate_json tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_json_raises_when_not_configured():
    provider = AnthropicProvider(api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not configured"):
        await provider.generate_json("prompt", "system")


@pytest.mark.asyncio
async def test_generate_json_success():
    provider = AnthropicProvider(api_key="sk-ant-test", models=["claude-3-5-haiku-20241022"])

    # Anthropic returns the content after the assistant-primed "{",
    # so the mock response text must NOT include the leading "{" (provider prepends it).
    response_body = {
        "content": [{"text": '"level": 8, "justification": "Good architecture"}'}],
    }
    fake_response = httpx.Response(
        200,
        json=response_body,
        request=httpx.Request("POST", ANTHROPIC_API_URL),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        raw_text, model_used = await provider.generate_json("prompt", "system")

    assert model_used == "claude-3-5-haiku-20241022"
    # Provider prepends "{" to assistant-primed response
    assert raw_text.startswith("{")
    assert "level" in raw_text


@pytest.mark.asyncio
async def test_generate_json_fallback_on_http_error():
    provider = AnthropicProvider(
        api_key="sk-ant-test",
        models=["model-bad", "claude-3-5-haiku-20241022"],
    )

    error_response = httpx.Response(
        529,
        text="Overloaded",
        request=httpx.Request("POST", ANTHROPIC_API_URL),
    )
    success_response = httpx.Response(
        200,
        json={"content": [{"text": '"level": 7}'}]},
        request=httpx.Request("POST", ANTHROPIC_API_URL),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [error_response, success_response]
        raw_text, model_used = await provider.generate_json("prompt", "system")

    assert model_used == "claude-3-5-haiku-20241022"


@pytest.mark.asyncio
async def test_generate_json_all_models_fail():
    provider = AnthropicProvider(api_key="sk-ant-test", models=["model-a", "model-b"])

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(httpx.ConnectError):
            await provider.generate_json("prompt", "system")


@pytest.mark.asyncio
async def test_generate_json_single_model_override():
    provider = AnthropicProvider(
        api_key="sk-ant-test",
        models=["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"],
    )

    success_response = httpx.Response(
        200,
        json={"content": [{"text": '"ok": true}'}]},
        request=httpx.Request("POST", ANTHROPIC_API_URL),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = success_response
        raw_text, model_used = await provider.generate_json(
            "prompt", "system", model="claude-3-5-sonnet-20241022"
        )

    # Only one call should have been made (the override model)
    assert mock_post.call_count == 1
    assert model_used == "claude-3-5-sonnet-20241022"


@pytest.mark.asyncio
async def test_generate_json_respects_timeout(monkeypatch):
    """Verify timeout_sec is forwarded to the httpx client."""
    provider = AnthropicProvider(api_key="sk-ant-test", models=["claude-3-5-haiku-20241022"])

    captured_timeout: list[float] = []

    class _FakeClient:
        def __init__(self, timeout, **_):
            captured_timeout.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={"content": [{"text": '"ok": true}'}]},
                request=httpx.Request("POST", ANTHROPIC_API_URL),
            )

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    await provider.generate_json("prompt", "system", timeout_sec=42)
    assert captured_timeout == [42.0]
