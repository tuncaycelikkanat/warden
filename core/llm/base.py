"""Base abstract class for LLM providers in WARDEN."""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract interface for LLM evaluation providers."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the required API keys or endpoints are configured."""

    @abstractmethod
    def get_default_models(self) -> list[str]:
        """Returns ordered fallback list of model names."""

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_instruction: str,
        model: str | None = None,
        temperature: float = 0.0,
        timeout_sec: int = 60,
    ) -> tuple[str, str]:
        """Sends prompt to the LLM and returns raw JSON text and model name used.

        Returns:
            tuple of (raw_response_text, model_name_used)
        """

    def generate_response(self, prompt: str, system_instruction: str = "") -> str:
        """Optional synchronous text generation method for CLI tools and queries."""
        return ""

    def generate_text(self, prompt: str) -> str:
        """Optional synchronous text generation method."""
        return ""
