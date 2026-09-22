"""JWT Authentication and Role-Based Access Control (RBAC) for WARDEN API."""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("WARDEN_JWT_SECRET", "warden-insecure-dev-secret-change-in-production")
AUTH_ENABLED = os.getenv("WARDEN_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

security_bearer = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_access_token(
    subject: str,
    role: str = "viewer",
    expires_in_sec: int = 86400,
    secret: str = JWT_SECRET,
) -> str:
    """Generates a signed JWT access token in pure Python (HS256)."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_sec,
    }

    h_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")

    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)

    return f"{h_b64}.{p_b64}.{sig_b64}"


def verify_access_token(token: str, secret: str = JWT_SECRET) -> dict[str, Any]:
    """Verifies and decodes a signed JWT access token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    h_b64, p_b64, sig_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = _b64encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = json.loads(_b64decode(p_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if "exp" in payload and time.time() > payload["exp"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> dict[str, Any]:
    """FastAPI dependency extracting the authenticated user.

    If WARDEN_AUTH_ENABLED is false, returns a default admin user.
    """
    if not AUTH_ENABLED:
        return {"sub": "anonymous-local", "role": "admin"}

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (Bearer token)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_access_token(credentials.credentials)


def require_role(allowed_roles: list[str]) -> Callable:
    """Dependency factory enforcing role-based permissions."""
    async def _role_checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = user.get("role", "viewer")
        if user_role not in allowed_roles and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of roles: {allowed_roles}, current: '{user_role}'",
            )
        return user
    return _role_checker
