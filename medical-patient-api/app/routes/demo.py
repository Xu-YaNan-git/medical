"""M9 golden-path demo reset (patient API)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.settings import allow_demo_reset

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
def demo_reset() -> dict:
    """Clear demo data and re-seed golden path. Prod gated unless ALLOW_RESET_IN_PROD=1."""
    if not allow_demo_reset():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "生产环境默认禁止演示重置；需设置 ALLOW_RESET_IN_PROD=1",
            },
        )
    return store.reset_demo_seed(actor="demo")
