"""Unit tests for JWT Authentication and RBAC."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import core.api.auth as auth_mod
from core.api.auth import (
    create_access_token,
    get_current_user,
    require_role,
    verify_access_token,
)


def test_jwt_token_roundtrip():
    token = create_access_token("user123", role="auditor", expires_in_sec=3600)
    payload = verify_access_token(token)
    assert payload["sub"] == "user123"
    assert payload["role"] == "auditor"
    assert "exp" in payload


def test_jwt_token_malformed():
    with pytest.raises(HTTPException) as exc:
        verify_access_token("invalid.token")
    assert exc.value.status_code == 401
    assert "Malformed token" in exc.value.detail


def test_jwt_token_invalid_signature():
    token = create_access_token("user123", role="auditor", secret="secret-A")
    with pytest.raises(HTTPException) as exc:
        verify_access_token(token, secret="secret-B")
    assert exc.value.status_code == 401
    assert "Invalid token signature" in exc.value.detail


def test_jwt_token_expired():
    token = create_access_token("user123", role="auditor", expires_in_sec=-10)
    with pytest.raises(HTTPException) as exc:
        verify_access_token(token)
    assert exc.value.status_code == 401
    assert "Token has expired" in exc.value.detail


def test_jwt_token_invalid_payload():
    # Build token with non-JSON payload
    h = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    p = "bm90LWpzb24"  # "not-json"
    import hashlib
    import hmac
    sig = auth_mod._b64encode(hmac.new(auth_mod.JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    bad_token = f"{h}.{p}.{sig}"
    with pytest.raises(HTTPException) as exc:
        verify_access_token(bad_token)
    assert exc.value.status_code == 401
    assert "Invalid token payload" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_auth_disabled():
    with patch_auth_enabled(False):
        user = await get_current_user(None)
        assert user["role"] == "admin"
        assert user["sub"] == "anonymous-local"


@pytest.mark.asyncio
async def test_get_current_user_auth_enabled():
    with patch_auth_enabled(True):
        # Missing credentials
        with pytest.raises(HTTPException) as exc1:
            await get_current_user(None)
        assert exc1.value.status_code == 401

        # Valid credentials
        token = create_access_token("dev-user", role="developer")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = await get_current_user(creds)
        assert user["sub"] == "dev-user"
        assert user["role"] == "developer"


@pytest.mark.asyncio
async def test_require_role():
    checker = require_role(["auditor", "admin"])

    # Allowed role
    user_auditor = {"sub": "a", "role": "auditor"}
    assert await checker(user_auditor) == user_auditor

    # Admin is always allowed
    user_admin = {"sub": "b", "role": "admin"}
    assert await checker(user_admin) == user_admin

    # Forbidden role
    user_viewer = {"sub": "c", "role": "viewer"}
    with pytest.raises(HTTPException) as exc:
        await checker(user_viewer)
    assert exc.value.status_code == 403
    assert "Operation requires one of roles" in exc.value.detail


class patch_auth_enabled:
    def __init__(self, val: bool):
        self.val = val
        self.prev = auth_mod.AUTH_ENABLED

    def __enter__(self):
        auth_mod.AUTH_ENABLED = self.val

    def __exit__(self, *args):
        auth_mod.AUTH_ENABLED = self.prev
