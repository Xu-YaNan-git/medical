"""Appointment CRUD (in-memory Mock)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.models import CreateAppointmentRequest, PatchAppointmentRequest

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.post("")
@router.post("/")
def create_appointment(body: CreateAppointmentRequest) -> dict:
    dept = store.get_department(body.departmentId)
    if not dept:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"科室不存在：{body.departmentId}"},
        )
    doctor = store.get_doctor(body.doctorId)
    if not doctor:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"医生不存在：{body.doctorId}"},
        )
    if doctor["departmentId"] != body.departmentId:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "医生不属于该科室"},
        )
    slot = store.get_slot(body.slotId)
    if not slot:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"号源不存在：{body.slotId}"},
        )
    if slot["doctorId"] != body.doctorId:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "号源不属于该医生"},
        )
    if not slot.get("available") or slot.get("remaining", 0) <= 0:
        raise HTTPException(
            status_code=409,
            detail={"error": "slot_full", "message": "该时段已约满"},
        )
    name = (body.patientName or "").strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "patientName 不能为空"},
        )

    consumed = store.consume_slot(body.slotId)
    if not consumed:
        raise HTTPException(
            status_code=409,
            detail={"error": "slot_full", "message": "该时段已约满"},
        )

    appt = store.create_appointment(
        {
            "departmentId": body.departmentId,
            "departmentName": dept["name"],
            "doctorId": body.doctorId,
            "doctorName": doctor["name"],
            "slotId": body.slotId,
            "date": consumed["date"],
            "time": consumed["time"],
            "patientName": name,
            "phone": body.phone,
            "chief": body.chief,
            "triageSessionId": body.triageSessionId,
            "status": "confirmed",
        }
    )
    store.append_audit(
        action="appointment.create",
        resource_type="appointment",
        resource_id=appt["id"],
        detail=f"创建预约 dept={body.departmentId} doctor={body.doctorId} date={consumed['date']} {consumed['time']}",
    )
    return appt


@router.get("")
@router.get("/")
def list_appointments() -> list[dict]:
    return store.list_appointments()


@router.get("/{appointment_id}")
def get_appointment(appointment_id: str) -> dict:
    appt = store.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{appointment_id}"},
        )
    return appt


@router.patch("/{appointment_id}")
def patch_appointment(appointment_id: str, body: PatchAppointmentRequest) -> dict:
    if not store.get_appointment(appointment_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{appointment_id}"},
        )
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "无有效更新字段"},
        )
    updated = store.update_appointment(appointment_id, patch)
    if patch.get("status") == "cancelled":
        store.append_audit(
            action="appointment.cancel",
            resource_type="appointment",
            resource_id=appointment_id,
            detail="取消预约",
        )
    else:
        store.append_audit(
            action="appointment.patch",
            resource_type="appointment",
            resource_id=appointment_id,
            detail=f"更新预约 fields={list(patch.keys())}",
        )
    return updated
