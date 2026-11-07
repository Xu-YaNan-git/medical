"""Doctor-side proxy to patient API pre-consult reports."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_auth
from app.patient_client import (
    PatientApiError,
    get_preconsult_report,
    list_preconsult_reports,
    normalize_items,
)

router = APIRouter(prefix="/api/preconsult", tags=["preconsult"])


def _raise(exc: PatientApiError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error, "message": exc.message},
    )


@router.get("/reports")
def list_reports(
    patientId: Optional[str] = Query(None),
    patientName: Optional[str] = Query(None),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    try:
        raw = list_preconsult_reports(patient_id=patientId, patient_name=patientName)
        return normalize_items(raw)
    except PatientApiError as exc:
        _raise(exc)
        raise  # for type checkers


@router.get("/reports/{report_id}")
def get_report(report_id: str, _user: str = Depends(require_auth)) -> dict:
    try:
        return get_preconsult_report(report_id)
    except PatientApiError as exc:
        _raise(exc)
        raise
