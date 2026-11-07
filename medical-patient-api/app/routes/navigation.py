"""M2 院内科室导航."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store

router = APIRouter(prefix="/api/navigation", tags=["navigation"])


@router.get("/departments")
def list_nav_departments() -> dict:
    items = store.list_navigation_departments()
    return {
        "items": items,
        "disclaimer": "导航文案为院内占位 Mock，请以现场指引为准。",
    }


@router.get("/{dept_id}")
def get_nav(dept_id: str) -> dict:
    # Avoid colliding with /departments if somehow matched — FastAPI matches static first
    item = store.get_navigation(dept_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"科室不存在：{dept_id}"},
        )
    return {
        **item,
        "disclaimer": "导航文案为院内占位 Mock，请以现场指引为准。",
    }
