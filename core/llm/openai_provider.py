"""OpenAI-compatible LLM provider implementation via HTTP."""

import logging
import os
from typing import Any

import httpx

from core.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, DeepSeek, Groq, OpenRouter, etc.)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        models: list[str] | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.models = models or ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    def get_default_models(self) -> list[str]:
        return list(self.models)

    async def generate_json(
        self,
        prompt: str,
        system_instruction: str,
        model: str | None = None,
        temperature: float = 0.0,
        timeout_sec: int = 60,
    ) -> tuple[str, str]:
        """Calls OpenAI-compatible /chat/completions endpoint with response_format=json_object."""
        if not self.is_configured():
            raise ValueError("OPENAI_API_KEY is not configured")

        models_to_try = [model] if model else self.models
        last_err = None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=float(timeout_sec)) as client:
            for m_name in models_to_try:
                payload = {
                    "model": m_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": temperature,
                }
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        return content, m_name
                    else:
                        logger.warning(
                            f"Model '{m_name}' returned status {response.status_code}: {response.text[:200]}"
                        )
                        last_err = RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
                except Exception as err:
                    logger.warning(f"Request for model '{m_name}' failed: {err}")
                    last_err = err
                    continue

        raise last_err if last_err else RuntimeError("All OpenAI-compatible models failed")
