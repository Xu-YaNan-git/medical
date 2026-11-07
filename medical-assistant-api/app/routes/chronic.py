"""Doctor M10 chronic management — proxy to patient API 8001."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_auth
from app.patient_client import (
    PatientApiError,
    get_chronic_summary,
    list_chronic_inbox,
    list_chronic_patients,
    list_chronic_vitals,
    mark_chronic_alert_read,
    normalize_items,
    ping,
)

router = APIRouter(prefix="/api/chronic", tags=["chronic"])

DISCLAIMER = "演示数据，非真实慢病管理；异常规则为演示阈值，不构成诊疗建议。"


def _raise(exc: PatientApiError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error, "message": exc.message},
    )


def _proxy_or_503(fn, *, _user: str) -> Any:
    patient_ok = ping()
    try:
        return fn()
    except PatientApiError as exc:
        if exc.status_code == 503 or not patient_ok:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": exc.error or "patient_api_unavailable",
                    "message": exc.message,
                    "patientApiOk": False,
                },
            ) from exc
        _raise(exc)
        raise


@router.get("/patients")
def chronic_patients(_user: str = Depends(require_auth)) -> dict[str, Any]:
    raw = _proxy_or_503(list_chronic_patients, _user=_user)
    payload = normalize_items(raw) if not isinstance(raw, dict) or "items" not in raw else raw
    if not isinstance(payload, dict):
        payload = {"items": []}
    items = payload.get("items") or []
    return {
        "items": items if isinstance(items, list) else [],
        "disclaimer": (payload.get("disclaimer") if isinstance(payload, dict) else None)
        or DISCLAIMER,
        "patientApiOk": True,
    }


@router.get("/patients/{patient_id}/vitals")
def patient_vitals(patient_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    raw = _proxy_or_503(lambda: list_chronic_vitals(patient_id), _user=_user)
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "message": "vitals 响应格式异常"},
        )
    out = dict(raw)
    out.setdefault("disclaimer", DISCLAIMER)
    out["patientApiOk"] = True
    return out


@router.get("/patients/{patient_id}/summary")
def patient_summary(patient_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    raw = _proxy_or_503(lambda: get_chronic_summary(patient_id), _user=_user)
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "message": "summary 响应格式异常"},
        )
    out = dict(raw)
    out.setdefault("disclaimer", DISCLAIMER)
    out["patientApiOk"] = True
    return out


@router.get("/inbox")
def chronic_inbox(_user: str = Depends(require_auth)) -> dict[str, Any]:
    raw = _proxy_or_503(list_chronic_inbox, _user=_user)
    payload = normalize_items(raw) if not isinstance(raw, dict) or "items" not in raw else raw
    if not isinstance(payload, dict):
        payload = {"items": []}
    items = payload.get("items") or []
    return {
        "items": items if isinstance(items, list) else [],
        "unreadCount": int(payload.get("unreadCount") or len(items or [])),
        "disclaimer": payload.get("disclaimer") or DISCLAIMER,
        "patientApiOk": True,
    }


@router.post("/inbox/{alert_id}/read")
def inbox_mark_read(alert_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    raw = _proxy_or_503(lambda: mark_chronic_alert_read(alert_id), _user=_user)
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "message": "标已阅响应格式异常"},
        )
    out = dict(raw)
    out.setdefault("disclaimer", DISCLAIMER)
    out["patientApiOk"] = True
    return out
