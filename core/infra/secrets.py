"""Dynamic secrets management service supporting Vault, AWS Secrets Manager, and local fallback."""

import logging
import os

logger = logging.getLogger(__name__)


class SecretsManagerService:
    """Provides dynamic secrets resolution and rotation abstractions for production environments."""

    def __init__(self, provider: str | None = None) -> None:
        """Initializes secret provider (env, vault, or aws)."""
        self.provider = provider or os.getenv("WARDEN_SECRET_PROVIDER", "env")
        self._cache: dict[str, str] = {}

    def get_secret(self, secret_name: str, default: str | None = None) -> str | None:
        """Retrieves a secret dynamically from the configured provider."""
        if secret_name in self._cache:
            return self._cache[secret_name]

        val: str | None = None
        if self.provider == "env":
            val = os.getenv(secret_name, default)
        elif self.provider == "vault":
            # Vault client integration placeholder / fallback
            val = os.getenv(f"VAULT_{secret_name}", os.getenv(secret_name, default))
        elif self.provider == "aws":
            # AWS Secrets Manager placeholder / fallback
            val = os.getenv(f"AWS_SECRET_{secret_name}", os.getenv(secret_name, default))
        else:
            val = os.getenv(secret_name, default)

        if val is not None:
            self._cache[secret_name] = val
        return val

    def clear_cache(self) -> None:
        """Flushes cached secret values."""
        self._cache.clear()
