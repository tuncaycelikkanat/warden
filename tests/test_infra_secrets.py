from core.infra.secrets import SecretsManagerService


def test_secrets_manager_env(monkeypatch):
    monkeypatch.setenv("WARDEN_SECRET_PROVIDER", "env")
    monkeypatch.setenv("TEST_API_KEY", "secret_123")

    service = SecretsManagerService()
    assert service.get_secret("TEST_API_KEY") == "secret_123"
    assert service.get_secret("NON_EXISTENT", default="fallback") == "fallback"

    # Verify cache
    monkeypatch.setenv("TEST_API_KEY", "changed_456")
    assert service.get_secret("TEST_API_KEY") == "secret_123"

    service.clear_cache()
    assert service.get_secret("TEST_API_KEY") == "changed_456"


def test_secrets_manager_vault(monkeypatch):
    monkeypatch.setenv("VAULT_DATABASE_URL", "postgres://vault-user@host/db")
    service = SecretsManagerService(provider="vault")
    assert service.get_secret("DATABASE_URL") == "postgres://vault-user@host/db"


def test_secrets_manager_aws(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_JWT_KEY", "aws_jwt_token")
    service = SecretsManagerService(provider="aws")
    assert service.get_secret("JWT_KEY") == "aws_jwt_token"


def test_secrets_manager_unknown_provider(monkeypatch):
    monkeypatch.setenv("CUSTOM_VAR", "custom_val")
    service = SecretsManagerService(provider="unknown_provider")
    assert service.get_secret("CUSTOM_VAR") == "custom_val"
