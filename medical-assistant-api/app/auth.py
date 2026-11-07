"""Simple in-memory bearer-token auth for the demo."""

from __future__ import annotations

import secrets
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DEMO_USER = {
    "username": "doctor",
    "password": "demo123",
    "displayName": "张医生",
}

# token -> displayName
_tokens: dict[str, str] = {}

_bearer = HTTPBearer(auto_error=False)


def issue_token(display_name: str) -> str:
    token = secrets.token_urlsafe(32) + "-" + uuid.uuid4().hex[:8]
    _tokens[token] = display_name
    return token


def revoke_token(token: str) -> None:
    _tokens.pop(token, None)


def resolve_token(token: str) -> Optional[str]:
    return _tokens.get(token)


def authenticate(username: str, password: str) -> Optional[dict]:
    if username == DEMO_USER["username"] and password == DEMO_USER["password"]:
        return {"displayName": DEMO_USER["displayName"]}
    return None


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Return displayName for a valid bearer token; raise 401 otherwise."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "缺少或无效的 Authorization Bearer token"},
        )
    name = resolve_token(credentials.credentials)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "无效或已过期的 token"},
        )
    return name
