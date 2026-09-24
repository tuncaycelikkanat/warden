"""Tests for JWT authentication and RBAC."""

import pytest
from fastapi import HTTPException

from core.api.auth import create_access_token, verify_access_token


class TestJWTAuthentication:
    def test_create_and_verify_valid_token(self) -> None:
        token = create_access_token(subject="user1", role="auditor", expires_in_sec=3600)
        payload = verify_access_token(token)
        assert payload["sub"] == "user1"
        assert payload["role"] == "auditor"
        assert "exp" in payload

    def test_invalid_signature_raises_401(self) -> None:
        token = create_access_token(subject="user1", role="auditor", secret="secret-A")
        with pytest.raises(HTTPException) as exc:
            verify_access_token(token, secret="secret-B")
        assert exc.value.status_code == 401
        assert "signature" in exc.value.detail.lower()

    def test_expired_token_raises_401(self) -> None:
        # Token expired 10 seconds ago
        token = create_access_token(subject="user1", role="auditor", expires_in_sec=-10)
        with pytest.raises(HTTPException) as exc:
            verify_access_token(token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_tampered_payload_raises_401(self) -> None:
        token = create_access_token(subject="user1", role="viewer")
        parts = token.split(".")
        # Tamper middle part
        parts[1] = "eyJzdWIiOiAiaGFja2VyIiwgInJvbGUiOiAiYWRtaW4ifQ"
        tampered_token = ".".join(parts)
        with pytest.raises(HTTPException) as exc:
            verify_access_token(tampered_token)
        assert exc.value.status_code == 401

    def test_malformed_token_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc:
            verify_access_token("not-a-jwt")
        assert exc.value.status_code == 401
