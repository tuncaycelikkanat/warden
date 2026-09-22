"""LLM provider configuration for WARDEN rubric evaluation."""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Ortam değişkeni adı — liste ise virgülle ayrılmış
_ENV_MODELS = "WARDEN_LLM_MODELS"
_ENV_TIMEOUT = "WARDEN_LLM_TIMEOUT_SEC"

# Varsayılan model öncelik sırası (soldan sağa denenecek)
DEFAULT_GEMINI_MODELS: list[str] = [
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]





@dataclass
class LLMConfig:
    """Configuration for the LLM provider used in Layer 2 rubric evaluation."""

    provider: str = "gemini"
    models: list[str] = field(default_factory=lambda: list(DEFAULT_GEMINI_MODELS))
    timeout_sec: int = 60
    temperature: float = 0.0

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

        return cls(models=models, timeout_sec=timeout)
