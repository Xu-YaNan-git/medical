"""Doctor-facing chronic inbox / patients (proxied by 8000)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store

router = APIRouter(prefix="/api/doctor/chronic", tags=["doctor-chronic"])

DISCLAIMER = store.CHRONIC_DISCLAIMER


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


@router.get("/inbox")
def chronic_inbox() -> dict:
    items = store.list_chronic_alerts(unread_only=True, limit=200)
    return {
        "items": items,
        "unreadCount": store.unread_chronic_alert_count(),
        "disclaimer": DISCLAIMER,
    }


@router.post("/inbox/{alert_id}/read")
def mark_inbox_read(alert_id: str) -> dict:
    item = store.mark_chronic_alert_read(alert_id)
    if not item:
        raise _err(404, "not_found", f"慢病告警不存在：{alert_id}")
    return item


@router.get("/patients")
def chronic_patients() -> dict:
    return {
        "items": store.list_chronic_patients(),
        "disclaimer": DISCLAIMER,
    }


@router.get("/patients/{patient_id}/vitals")
def patient_vitals(patient_id: str) -> dict:
    if not store.get_patient(patient_id):
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    items = store.list_vitals(patient_id=patient_id, limit=100)
    summary = store.vitals_summary(patient_id)
    return {"items": items, "summary": summary, "disclaimer": DISCLAIMER}


@router.get("/patients/{patient_id}/summary")
def patient_summary(patient_id: str) -> dict:
    try:
        return store.vitals_summary(patient_id)
    except ValueError as exc:
        if str(exc) == "patient_not_found":
            raise _err(404, "not_found", f"就诊人不存在：{patient_id}") from exc
        raise _err(400, "bad_request", str(exc)) from exc
