"""医生端只读拉取预问诊报告（MVP 无患者鉴权）."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store

router = APIRouter(prefix="/api/doctor/preconsult", tags=["doctor-preconsult"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


@router.get("")
def list_for_doctor(
    patientId: Optional[str] = Query(None),
    patientName: Optional[str] = Query(None),
) -> list[dict]:
    return store.list_preconsult_reports(
        patient_id=patientId, patient_name=patientName
    )


@router.get("/{report_id}")
def get_for_doctor(report_id: str) -> dict:
    r = store.get_preconsult_report(report_id)
    if not r:
        raise _err(404, "not_found", f"预问诊报告不存在：{report_id}")
    return r
