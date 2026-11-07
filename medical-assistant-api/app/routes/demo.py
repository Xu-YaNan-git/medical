"""M9 golden-path demo reset (doctor API)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth
from app.settings import allow_demo_reset
from app.store import store

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
def demo_reset(user: str = Depends(require_auth)) -> dict:
    """Clear demo visits and re-seed. Requires Bearer. Prod gated unless ALLOW_RESET_IN_PROD=1."""
    if not allow_demo_reset():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "生产环境默认禁止演示重置；需设置 ALLOW_RESET_IN_PROD=1",
            },
        )
    return store.reset_demo_seed(actor=user or "doctor")
