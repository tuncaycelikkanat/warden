"""Anthropic Claude LLM provider implementation for WARDEN."""

import logging
import os

import httpx
from dotenv import load_dotenv

from core.llm.base import BaseLLMProvider

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_ANTHROPIC_MODELS: list[str] = [
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
]

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider with multi-model fallback.

    Uses the Anthropic Messages API directly via httpx to avoid adding
    the ``anthropic`` SDK as a hard dependency — the same pattern as
    the OpenAI-compatible provider.
    """

    provider_name: str = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        models: list[str] | None = None,
    ) -> None:
        self.api_key: str = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        self.models: list[str] = models or list(DEFAULT_ANTHROPIC_MODELS)

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Returns True if ANTHROPIC_API_KEY is non-empty."""
        return bool(self.api_key.strip())

    def get_default_models(self) -> list[str]:
        """Returns the ordered model fallback list."""
        return list(self.models)

    async def generate_json(
        self,
        prompt: str,
        system_instruction: str,
        model: str | None = None,
        temperature: float = 0.0,
        timeout_sec: int = 60,
    ) -> tuple[str, str]:
        """Calls Anthropic Messages API and returns (raw_json_text, model_used).

        Iterates through the model list and returns on first success.
        Forces JSON output via a ``{"type": "json_object"}`` assistant
        message prefix (Claude does not natively support response_format,
        so we prime the assistant turn).

        Raises:
            ValueError: When no API key is configured.
            RuntimeError: When all models fail.
        """
        if not self.is_configured():
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        models_to_try = [model] if model else self.models
        last_err: Exception | None = None

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=float(timeout_sec)) as client:
            for m_name in models_to_try:
                payload = {
                    "model": m_name,
                    "max_tokens": 1024,
                    "temperature": temperature,
                    "system": system_instruction,
                    "messages": [
                        {"role": "user", "content": prompt},
                        # Prime Claude to start responding with JSON
                        {"role": "assistant", "content": "{"},
                    ],
                }
                try:
                    response = await client.post(
                        ANTHROPIC_API_URL,
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        # Prepend the "{" we primed in the assistant turn
                        raw_text = "{" + data["content"][0]["text"]
                        return raw_text, m_name
                    else:
                        logger.warning(
                            "Anthropic model '%s' returned HTTP %s: %s",
                            m_name,
                            response.status_code,
                            response.text[:200],
                        )
                        last_err = RuntimeError(
                            f"HTTP {response.status_code}: {response.text[:200]}"
                        )
                except Exception as err:
                    logger.warning("Anthropic request for model '%s' failed: %s", m_name, err)
                    last_err = err
                    continue

        raise last_err if last_err else RuntimeError("All Anthropic models failed")
