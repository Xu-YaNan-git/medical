"""M8 doctor workbench summary: visits + preconsult + doctor-consult queue."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.patient_client import (
    PatientApiError,
    chronic_unread_count,
    list_doctor_consult_queue,
    list_preconsult_reports,
    normalize_items,
    ping,
)
from app.store import store

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


@router.get("/summary")
def workbench_summary(_user: str = Depends(require_auth)) -> dict[str, Any]:
    waiting_statuses = {"waiting", "in_progress"}
    visits_waiting = [
        store.summary(v)
        for v in store.list_visits()
        if (v.get("status") or "") in waiting_statuses
    ]

    preconsult_recent: list[Any] = []
    preconsult_error: str | None = None
    try:
        raw = list_preconsult_reports()
        items = normalize_items(raw).get("items") or []
        if isinstance(items, list):
            preconsult_recent = items[:10]
        else:
            preconsult_recent = []
    except PatientApiError as exc:
        preconsult_error = exc.message
        preconsult_recent = []

    doctor_consult_queued: list[Any] = []
    doctor_consult_error: str | None = None
    try:
        raw_q = list_doctor_consult_queue()
        items_q = normalize_items(raw_q).get("items") or []
        doctor_consult_queued = items_q if isinstance(items_q, list) else []
    except PatientApiError as exc:
        doctor_consult_error = exc.message
        doctor_consult_queued = []

    chronic_abnormal = 0
    chronic_error: str | None = None
    try:
        chronic_abnormal = int(chronic_unread_count())
    except Exception as exc:  # noqa: BLE001 — badge best-effort
        chronic_error = str(exc)
        chronic_abnormal = 0

    patient_ok = ping()
    body: dict[str, Any] = {
        "visitsWaiting": visits_waiting,
        "preconsultRecent": preconsult_recent,
        "doctorConsultQueued": doctor_consult_queued,
        "chronicAbnormal": chronic_abnormal,
        # aliases matching the M8 brief wording
        "preconsultReports": preconsult_recent,
        "doctorConsultQueue": doctor_consult_queued,
        "counts": {
            "visitsWaiting": len(visits_waiting),
            "preconsultRecent": len(preconsult_recent),
            "doctorConsultQueued": len(doctor_consult_queued),
            "chronicAbnormal": chronic_abnormal,
        },
        "patientApiOk": patient_ok,
    }
    if preconsult_error:
        body["preconsultError"] = preconsult_error
    if doctor_consult_error:
        body["doctorConsultError"] = doctor_consult_error
    if chronic_error:
        body["chronicError"] = chronic_error
    return body
