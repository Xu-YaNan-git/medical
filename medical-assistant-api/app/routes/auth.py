"""Auth routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.auth import authenticate, issue_token
from app.models import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": "账号或密码错误"},
        )
    token = issue_token(user["displayName"])
    return LoginResponse(token=token, displayName=user["displayName"])
