"""M3 用药提醒."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import CreateMedicationReminderRequest, PatchMedicationReminderRequest

router = APIRouter(prefix="/api/medications", tags=["medications"])


@router.get("/reminders")
def list_reminders(
    patientId: Optional[str] = Query(None),
) -> dict:
    items = store.list_medication_reminders(patient_id=patientId)
    return {
        "items": items,
        "disclaimer": store.MED_DISCLAIMER,
    }


@router.post("/reminders")
def create_reminder(body: CreateMedicationReminderRequest) -> dict:
    name = (body.drugName or "").strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "drugName 必填"},
        )
    item = store.create_medication_reminder(
        {
            "patientId": body.patientId,
            "drugName": name,
            "dose": body.dose,
            "frequency": body.frequency,
            "times": body.times or [],
            "startDate": body.startDate,
            "endDate": body.endDate,
            "enabled": body.enabled if body.enabled is not None else True,
        }
    )
    return item


@router.patch("/reminders/{reminder_id}")
def patch_reminder(reminder_id: str, body: PatchMedicationReminderRequest) -> dict:
    patch = body.model_dump(exclude_unset=True)
    item = store.update_medication_reminder(reminder_id, patch)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"用药提醒不存在：{reminder_id}"},
        )
    return item


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: str) -> dict:
    ok = store.delete_medication_reminder(reminder_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"用药提醒不存在：{reminder_id}"},
        )
    return {"ok": True, "id": reminder_id}


@router.get("/today")
def today_doses(
    patientId: Optional[str] = Query(None),
) -> dict:
    items = store.list_today_doses(patient_id=patientId)
    return {
        "items": items,
        "disclaimer": store.MED_DISCLAIMER,
    }
