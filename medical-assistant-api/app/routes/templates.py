"""M11 specialty templates listing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.models import SpecialtyTemplate
from app.templates_data import list_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[SpecialtyTemplate])
def get_templates(_user: str = Depends(require_auth)) -> list[dict[str, Any]]:
    return list_templates()
