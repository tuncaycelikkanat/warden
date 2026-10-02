"""Ollama local LLM provider for WARDEN (OpenAI-compatible endpoint)."""

import logging
import os

from dotenv import load_dotenv

from core.llm.openai_provider import OpenAICompatibleProvider

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_MODELS: list[str] = [
    "qwen2.5-coder:1.5b",
    "deepseek-coder:1.3b",
    "codellama:7b",
    "llama3.2:3b",
]

_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama local model provider using the OpenAI-compatible REST endpoint.

    Ollama exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint, so
    this class simply pre-configures ``OpenAICompatibleProvider`` with the
    correct base URL and a sentinel API key (Ollama ignores the key but the
    client requires a non-empty string).

    Environment variables:
        OLLAMA_BASE_URL: Base URL for the Ollama server.
                         Defaults to ``http://localhost:11434/v1``.
        OLLAMA_MODELS:   Comma-separated model list override.
    """

    provider_name: str = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        models: list[str] | None = None,
        **kwargs,  # absorb extra kwargs from factory
    ) -> None:
        resolved_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        )

        raw_models_env = os.getenv("OLLAMA_MODELS", "").strip()
        resolved_models: list[str]
        if models:
            resolved_models = models
        elif raw_models_env:
            resolved_models = [m.strip() for m in raw_models_env.split(",") if m.strip()]
        else:
            resolved_models = list(DEFAULT_OLLAMA_MODELS)

        super().__init__(
            # Ollama does not require a real API key; use a placeholder so that
            # is_configured() returns True when the server is reachable.
            api_key="ollama",
            base_url=resolved_url,
            models=resolved_models,
        )
        logger.debug("OllamaProvider initialised — base_url=%s models=%s", resolved_url, resolved_models)

    def is_configured(self) -> bool:
        """Always returns True; Ollama runs locally without an API key."""
        return True
