"""M10 chronic vitals: patient BP/glucose check-ins."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import store

router = APIRouter(prefix="/api/chronic", tags=["chronic"])

DISCLAIMER = store.CHRONIC_DISCLAIMER


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


class VitalCreate(BaseModel):
    patientId: str
    type: Literal["bp", "glucose"]
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    glucose: Optional[float] = None
    unit: Optional[str] = None
    measuredAt: Optional[str] = None
    note: Optional[str] = None


@router.post("/vitals")
def create_vital(body: VitalCreate) -> dict:
    try:
        return store.create_vital(body.model_dump())
    except ValueError as exc:
        code = str(exc)
        if code == "patient_not_found":
            raise _err(404, "not_found", f"就诊人不存在：{body.patientId}") from exc
        if code == "patientId_required":
            raise _err(422, "validation_error", "patientId 必填") from exc
        if code == "invalid_type":
            raise _err(422, "validation_error", "type 须为 bp 或 glucose") from exc
        if code == "bp_requires_systolic_diastolic":
            raise _err(422, "validation_error", "血压打卡需要 systolic 与 diastolic") from exc
        if code == "glucose_required":
            raise _err(422, "validation_error", "血糖打卡需要 glucose") from exc
        if code in ("invalid_bp_values", "invalid_glucose"):
            raise _err(422, "validation_error", "数值格式无效") from exc
        raise _err(400, "bad_request", code) from exc


@router.get("/vitals")
def list_vitals(
    patientId: Optional[str] = Query(None),
    type: Optional[str] = Query(None, description="bp|glucose"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    items = store.list_vitals(patient_id=patientId, vtype=type, limit=limit)
    return {"items": items, "disclaimer": DISCLAIMER}


@router.get("/vitals/summary")
def vitals_summary(patientId: str = Query(..., description="就诊人 id")) -> dict:
    try:
        return store.vitals_summary(patientId)
    except ValueError as exc:
        if str(exc) == "patient_not_found":
            raise _err(404, "not_found", f"就诊人不存在：{patientId}") from exc
        raise _err(400, "bad_request", str(exc)) from exc
