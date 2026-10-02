"""LLM provider configuration for WARDEN rubric evaluation."""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Model list env variables ──────────────────────────────────────────────────
_ENV_MODELS = "WARDEN_LLM_MODELS"
_ENV_TIMEOUT = "WARDEN_LLM_TIMEOUT_SEC"

# ── Panelist / confidence env variables ───────────────────────────────────────
_ENV_PANELIST_MODE = "WARDEN_LLM_PANELIST_MODE"
_ENV_CONFIDENCE_THRESHOLD = "WARDEN_LLM_CONFIDENCE_THRESHOLD"

# ── Ollama env variables ──────────────────────────────────────────────────────
_ENV_OLLAMA_BASE_URL = "OLLAMA_BASE_URL"

# ── Default model lists ───────────────────────────────────────────────────────
DEFAULT_GEMINI_MODELS: list[str] = [
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]

DEFAULT_ANTHROPIC_MODELS: list[str] = [
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
]

DEFAULT_OLLAMA_MODELS: list[str] = [
    "qwen2.5-coder:1.5b",
    "deepseek-coder:1.3b",
    "codellama:7b",
    "llama3.2:3b",
]





@dataclass
class LLMConfig:
    """Configuration for the LLM provider used in Layer 2 rubric evaluation."""

    provider: str = "gemini"
    models: list[str] = field(default_factory=lambda: list(DEFAULT_GEMINI_MODELS))
    timeout_sec: int = 60
    temperature: float = 0.0
    panelist_mode: bool = False
    confidence_threshold: float = 0.5

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Builds LLMConfig from environment variables with safe fallbacks."""
        raw_models = os.getenv(_ENV_MODELS, "").strip()
        if raw_models:
            models = [m.strip() for m in raw_models.split(",") if m.strip()]
            logger.info(f"LLM model listesi ortam değişkeninden okundu: {models}")
        else:
            models = list(DEFAULT_GEMINI_MODELS)

        raw_timeout = os.getenv(_ENV_TIMEOUT, "")
        try:
            timeout = int(raw_timeout) if raw_timeout else 60
        except ValueError:
            logger.warning(f"Geçersiz {_ENV_TIMEOUT} değeri '{raw_timeout}', varsayılan 60s kullanılıyor.")
            timeout = 60

        panelist_mode = os.getenv(_ENV_PANELIST_MODE, "false").strip().lower() == "true"

        raw_threshold = os.getenv(_ENV_CONFIDENCE_THRESHOLD, "")
        try:
            confidence_threshold = float(raw_threshold) if raw_threshold else 0.5
            confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        except ValueError:
            logger.warning(
                f"Geçersiz {_ENV_CONFIDENCE_THRESHOLD} değeri '{raw_threshold}', varsayılan 0.5 kullanılıyor."
            )
            confidence_threshold = 0.5

        return cls(
            models=models,
            timeout_sec=timeout,
            panelist_mode=panelist_mode,
            confidence_threshold=confidence_threshold,
        )
