"""Google Gemini LLM provider implementation."""

import asyncio
import logging
import os
from typing import Any

from core.llm.base import BaseLLMProvider
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider with multi-model fallback."""

    def __init__(self, api_key: str | None = None, models: list[str] | None = None) -> None:
        from core.config.llm_config import DEFAULT_GEMINI_MODELS
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.models = models or list(DEFAULT_GEMINI_MODELS)



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
        """Calls Gemini with model fallback chain and JSON enforcement."""
        if not self.is_configured():
            raise ValueError("GEMINI_API_KEY is not configured")

        from google import genai
        from google.genai import types

        models_to_try = [model] if model else self.models

        def _sync_call() -> tuple[str, str]:
            client = genai.Client(api_key=self.api_key)
            last_err = None

            for m_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=temperature,
                            response_mime_type="application/json",
                        ),
                    )
                    if response and response.text:
                        return response.text, m_name
                except Exception as err:
                    logger.warning(f"Gemini model '{m_name}' failed: {err}")
                    last_err = err
                    continue

            raise last_err if last_err else RuntimeError("All Gemini models failed")

        return await asyncio.to_thread(_sync_call)
