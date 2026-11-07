"""M4 实名/就诊卡绑定占位（双路径 /api/identity 与 /api/identity/binding）."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.models import UpdateIdentityRequest

router = APIRouter(tags=["identity"])


def _get() -> dict:
    return store.get_identity_public()


def _put(body: UpdateIdentityRequest) -> dict:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "至少提供 realName / idNumber / visitCardNo 之一"},
        )
    return store.update_identity(data)


@router.get("/api/identity")
@router.get("/api/identity/")
@router.get("/api/identity/binding")
@router.get("/api/identity/binding/")
def get_identity() -> dict:
    return _get()


@router.put("/api/identity")
@router.put("/api/identity/")
@router.put("/api/identity/binding")
@router.put("/api/identity/binding/")
def put_identity(body: UpdateIdentityRequest) -> dict:
    return _put(body)
