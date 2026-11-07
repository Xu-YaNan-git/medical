"""医生端只读拉取随访问卷结果（MVP 无患者鉴权）."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store

router = APIRouter(prefix="/api/doctor/followups", tags=["doctor-followups"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


@router.get("")
def list_for_doctor() -> dict:
    items = store.list_doctor_followups()
    return {
        "items": items,
        "disclaimer": store.FOLLOWUP_DISCLAIMER,
    }


@router.get("/{response_id}")
def get_for_doctor(response_id: str) -> dict:
    item = store.get_followup_response(response_id)
    if not item:
        raise _err(404, "not_found", f"随访回复不存在：{response_id}")
    return item
