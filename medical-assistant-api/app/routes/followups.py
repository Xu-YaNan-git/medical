"""Doctor-side follow-up inbox proxy to patient API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth
from app.patient_client import (
    PatientApiError,
    get_followup_response,
    list_followup_inbox,
    normalize_items,
    ping,
)

router = APIRouter(prefix="/api/followups", tags=["followups"])

DISCLAIMER = "随访问卷为演示采集，结果仅供参考，不构成诊疗结论；如有不适请及时就医。"


def _raise(exc: PatientApiError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error, "message": exc.message},
    )


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    submitted = raw.get("submittedAt") or raw.get("createdAt") or ""
    risk_level = raw.get("riskLevel") or "none"
    risk_flag = raw.get("riskFlag")
    if risk_flag is None:
        risk_flag = risk_level in ("high", "medium")
    return {
        "id": raw.get("id"),
        "patientId": raw.get("patientId"),
        "patientName": raw.get("patientName") or raw.get("patientId") or "",
        "surveyId": raw.get("surveyId"),
        "surveyTitle": raw.get("surveyTitle") or "",
        "submittedAt": submitted,
        "createdAt": raw.get("createdAt") or submitted,
        "riskLevel": risk_level,
        "riskFlag": risk_flag,
        "riskNote": raw.get("riskNote") or "",
        "answers": raw.get("answers") or {},
        "disclaimer": raw.get("disclaimer") or DISCLAIMER,
    }


@router.get("/inbox")
def inbox(_user: str = Depends(require_auth)) -> dict[str, Any]:
    patient_ok = ping()
    try:
        raw = list_followup_inbox()
        payload = normalize_items(raw)
        items = [_normalize_item(x) for x in payload.get("items") or [] if isinstance(x, dict)]
        disclaimer = (
            payload.get("disclaimer")
            if isinstance(payload, dict)
            else None
        ) or DISCLAIMER
        return {
            "items": items,
            "disclaimer": disclaimer,
            "patientApiOk": True,
        }
    except PatientApiError as exc:
        if exc.status_code == 503 or not patient_ok:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": exc.error or "patient_api_unavailable",
                    "message": exc.message,
                    "patientApiOk": False,
                },
            )
        _raise(exc)
        raise


@router.get("/inbox/{response_id}")
def inbox_detail(response_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    try:
        raw = get_followup_response(response_id)
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=502,
                detail={"error": "upstream_error", "message": "随访详情格式异常"},
            )
        out = _normalize_item(raw)
        out["patientApiOk"] = True
        return out
    except PatientApiError as exc:
        if exc.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": exc.error or "patient_api_unavailable",
                    "message": exc.message,
                    "patientApiOk": False,
                },
            )
        _raise(exc)
        raise
