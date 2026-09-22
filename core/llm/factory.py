"""Factory for instantiating LLM providers based on name or configuration."""

import logging
from typing import Any

from core.llm.base import BaseLLMProvider
from core.llm.gemini_provider import GeminiProvider
from core.llm.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Creates configured LLM providers for WARDEN."""

    @staticmethod
    def create(
        provider_name: str = "gemini",
        models: list[str] | None = None,
        **kwargs: Any,
    ) -> BaseLLMProvider:
        """Instantiates the requested provider with appropriate configuration."""
        name = provider_name.lower().strip()

        if name == "gemini":
            return GeminiProvider(models=models, **kwargs)
        elif name in ("openai", "groq", "deepseek", "openrouter"):
            return OpenAICompatibleProvider(models=models, **kwargs)
        else:
            logger.warning(f"Unknown LLM provider '{provider_name}', falling back to Gemini.")
            return GeminiProvider(models=models, **kwargs)
