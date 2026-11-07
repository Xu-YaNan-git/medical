"""M6 检查检验预约（独立于门诊 /api/appointments）."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import (
    CancelUiExamBookingRequest,
    CreateLabExamBookingRequest,
    CreateUiExamBookingRequest,
    PatchLabExamBookingRequest,
    RescheduleUiExamBookingRequest,
)

router = APIRouter(tags=["lab-exams"])

# Thin aliases for UI that may use /api/exams* or /api/exam-appointments
alias_router = APIRouter(tags=["lab-exams-alias"])


def _map_store_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    mapping = {
        "exam_not_found": (404, "not_found", "检查项目不存在"),
        "slot_not_found": (404, "not_found", "号源不存在"),
        "booking_not_found": (404, "not_found", "预约不存在"),
        "slot_exam_mismatch": (422, "validation_error", "号源不属于该检查项目"),
        "slot_full": (409, "slot_full", "该时段已约满"),
        "booking_cancelled": (409, "booking_cancelled", "预约已取消，无法改约"),
        "reschedule_limit": (400, "reschedule_limit", "最多改约3次"),
        "missing_slot": (422, "validation_error", "请提供 slotId 或 date+time"),
        "same_slot": (422, "validation_error", "改约目标与当前时段相同"),
    }
    status, err, msg = mapping.get(code, (400, "bad_request", code))
    return HTTPException(status_code=status, detail={"error": err, "message": msg})


# ---------- Catalog ----------
@router.get("/api/lab-exams")
@router.get("/api/lab-exams/")
@router.get("/api/exams/catalog")
@router.get("/api/exams/catalog/")
def list_lab_exams(category: Optional[str] = Query(None)) -> dict:
    items = store.list_lab_exams(category=category)
    return {"items": items, "disclaimer": store.LAB_EXAM_DISCLAIMER}


@router.get("/api/lab-exams/{exam_id}")
@router.get("/api/exams/{exam_id}")
def get_lab_exam(exam_id: str) -> dict:
    # avoid colliding with /api/exams/catalog — FastAPI matches static first if registered;
    # catalog is registered above as separate path; if exam_id == "catalog" redirect to list
    if exam_id == "catalog":
        return list_lab_exams()
    exam = store.get_lab_exam(exam_id)
    if not exam:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"检查项目不存在：{exam_id}"},
        )
    return exam


# ---------- Slots ----------
@router.get("/api/lab-exams/{exam_id}/slots")
@router.get("/api/exams/{exam_id}/slots")
def list_lab_exam_slots(
    exam_id: str, date: Optional[str] = Query(None, description="YYYY-MM-DD")
) -> dict:
    if not store.get_lab_exam(exam_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"检查项目不存在：{exam_id}"},
        )
    slots = store.list_lab_exam_slots(exam_id, date=date)
    return {
        "examId": exam_id,
        "date": date,
        "items": slots,
        "disclaimer": store.LAB_EXAM_DISCLAIMER,
    }


# ---------- Bookings ----------
@router.post("/api/lab-exam-bookings")
@router.post("/api/lab-exam-bookings/")
@router.post("/api/exam-appointments")
@router.post("/api/exam-appointments/")
def create_booking(body: CreateLabExamBookingRequest) -> dict:
    try:
        booking = store.create_lab_exam_booking(
            exam_id=body.examId,
            slot_id=body.slotId,
            patient_id=body.patientId,
            patient_name=body.patientName,
        )
    except ValueError as e:
        raise _map_store_error(e) from e
    store.append_audit(
        action="lab_exam_booking.create",
        resource_type="lab_exam_booking",
        resource_id=booking["id"],
        detail=f"创建检查预约 exam={body.examId} slot={body.slotId} date={booking.get('date')} {booking.get('time')}",
    )
    return booking


@router.get("/api/lab-exam-bookings")
@router.get("/api/lab-exam-bookings/")
@router.get("/api/exam-appointments")
@router.get("/api/exam-appointments/")
def list_bookings(patientId: Optional[str] = Query(None)) -> dict:
    items = store.list_lab_exam_bookings(patient_id=patientId)
    return {"items": items, "disclaimer": store.LAB_EXAM_DISCLAIMER}


@router.get("/api/lab-exam-bookings/{booking_id}")
@router.get("/api/exam-appointments/{booking_id}")
def get_booking(booking_id: str) -> dict:
    booking = store.get_lab_exam_booking(booking_id)
    if not booking:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{booking_id}"},
        )
    return booking


@router.patch("/api/lab-exam-bookings/{booking_id}")
@router.patch("/api/exam-appointments/{booking_id}")
def patch_booking(booking_id: str, body: PatchLabExamBookingRequest) -> dict:
    if body.status == "cancelled":
        try:
            booking = store.cancel_lab_exam_booking(booking_id)
        except ValueError as e:
            raise _map_store_error(e) from e
        store.append_audit(
            action="lab_exam_booking.cancel",
            resource_type="lab_exam_booking",
            resource_id=booking_id,
            detail="取消检查预约",
        )
        return booking

    if body.slotId or (body.date and body.time):
        try:
            booking = store.reschedule_lab_exam_booking(
                booking_id,
                slot_id=body.slotId,
                date=body.date,
                time=body.time,
            )
        except ValueError as e:
            raise _map_store_error(e) from e
        store.append_audit(
            action="lab_exam_booking.reschedule",
            resource_type="lab_exam_booking",
            resource_id=booking_id,
            detail=(
                f"改约#{booking.get('rescheduleCount')} "
                f"→ {booking.get('date')} {booking.get('time')} slot={booking.get('slotId')}"
            ),
        )
        return booking

    raise HTTPException(
        status_code=422,
        detail={
            "error": "validation_error",
            "message": "请提供 slotId 或 date+time 改约，或 status=cancelled 取消",
        },
    )


@router.post("/api/lab-exam-bookings/{booking_id}/cancel")
@router.post("/api/exam-appointments/{booking_id}/cancel")
def cancel_booking(booking_id: str) -> dict:
    try:
        booking = store.cancel_lab_exam_booking(booking_id)
    except ValueError as e:
        raise _map_store_error(e) from e
    store.append_audit(
        action="lab_exam_booking.cancel",
        resource_type="lab_exam_booking",
        resource_id=booking_id,
        detail="取消检查预约",
    )
    return booking


# Also expose GET /api/exams as catalog alias (same as list)
@alias_router.get("/api/exams")
@alias_router.get("/api/exams/")
def list_exams_alias(category: Optional[str] = Query(None)) -> dict:
    return list_lab_exams(category=category)


# ---------- Product UI contract: /api/exam-items + /api/exam-bookings ----------
ui_router = APIRouter(tags=["exam-ui-contract"])


def _add_minutes(hhmm: str, minutes: int) -> str:
    try:
        parts = (hhmm or "00:00").split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        h, m = 0, 0
    total = h * 60 + m + int(minutes or 0)
    total = total % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _ui_item(exam: dict) -> dict:
    return {
        "id": exam.get("id"),
        "name": exam.get("name"),
        "category": exam.get("category"),
        "durationMin": exam.get("durationMinutes"),
        "durationMinutes": exam.get("durationMinutes"),
        "prepNotes": exam.get("prepNotes"),
        "注意事项": exam.get("prepNotes") or exam.get("注意事项"),
        "price": exam.get("price"),
        "location": exam.get("location"),
        "disclaimer": store.LAB_EXAM_DISCLAIMER,
    }


def _ui_slot(slot: dict, *, duration_min: int = 30) -> dict:
    start = slot.get("time") or ""
    return {
        "slotId": slot.get("id"),
        "id": slot.get("id"),
        "examId": slot.get("examId"),
        "date": slot.get("date"),
        "time": start,
        "startTime": start,
        "endTime": _add_minutes(start, duration_min),
        "remaining": slot.get("remaining"),
        "available": slot.get("available"),
    }


def _ui_status(booking: dict) -> str:
    status = booking.get("status") or ""
    if status == "cancelled":
        return "cancelled"
    if status == "completed":
        return "completed"
    if int(booking.get("rescheduleCount") or 0) > 0:
        return "rescheduled"
    if status in ("confirmed", "booked"):
        return "booked"
    return status or "booked"


def _ui_booking(booking: dict) -> dict:
    time = booking.get("time") or ""
    date = booking.get("date") or ""
    slot_label = f"{date} {time}".strip() if date or time else time
    return {
        "id": booking.get("id"),
        "itemId": booking.get("examId"),
        "examId": booking.get("examId"),
        "itemName": booking.get("examName"),
        "examName": booking.get("examName"),
        "category": booking.get("category"),
        "date": date,
        "time": time,
        "slotId": booking.get("slotId"),
        "slotLabel": slot_label,
        "status": _ui_status(booking),
        "statusRaw": booking.get("status"),
        "rescheduleCount": int(booking.get("rescheduleCount") or 0),
        "maxReschedule": store.LAB_EXAM_RESCHEDULE_LIMIT,
        "prepNotes": booking.get("prepNotes"),
        "注意事项": booking.get("注意事项") or booking.get("prepNotes"),
        "patientId": booking.get("patientId"),
        "patientName": booking.get("patientName"),
        "note": booking.get("note"),
        "cancelReason": booking.get("cancelReason"),
        "location": booking.get("location"),
        "createdAt": booking.get("createdAt"),
        "updatedAt": booking.get("updatedAt"),
        "cancelledAt": booking.get("cancelledAt"),
        "disclaimer": store.LAB_EXAM_DISCLAIMER,
    }


@ui_router.get("/api/exam-items")
@ui_router.get("/api/exam-items/")
def ui_list_exam_items(category: Optional[str] = Query(None)) -> dict:
    items = [_ui_item(e) for e in store.list_lab_exams(category=category)]
    return {"items": items, "disclaimer": store.LAB_EXAM_DISCLAIMER}


@ui_router.get("/api/exam-items/{item_id}")
def ui_get_exam_item(item_id: str) -> dict:
    exam = store.get_lab_exam(item_id)
    if not exam:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"检查项目不存在：{item_id}"},
        )
    return _ui_item(exam)


@ui_router.get("/api/exam-items/{item_id}/slots")
def ui_list_exam_item_slots(
    item_id: str, date: Optional[str] = Query(None, description="YYYY-MM-DD")
) -> dict:
    exam = store.get_lab_exam(item_id)
    if not exam:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"检查项目不存在：{item_id}"},
        )
    duration = int(exam.get("durationMinutes") or 30)
    slots = [
        _ui_slot(s, duration_min=duration)
        for s in store.list_lab_exam_slots(item_id, date=date)
    ]
    return {
        "itemId": item_id,
        "examId": item_id,
        "date": date,
        "items": slots,
        "disclaimer": store.LAB_EXAM_DISCLAIMER,
    }


@ui_router.post("/api/exam-bookings")
@ui_router.post("/api/exam-bookings/")
def ui_create_exam_booking(body: CreateUiExamBookingRequest) -> dict:
    # optional date consistency check
    if body.date:
        slot = store.get_lab_exam_slot(body.slotId)
        if slot and slot.get("date") != body.date:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "validation_error",
                    "message": f"slot 日期 {slot.get('date')} 与请求 date {body.date} 不一致",
                },
            )
    try:
        booking = store.create_lab_exam_booking(
            exam_id=body.itemId,
            slot_id=body.slotId,
            patient_id=body.patientId,
            patient_name=body.patientName,
            note=body.note,
        )
    except ValueError as e:
        raise _map_store_error(e) from e
    store.append_audit(
        action="lab_exam_booking.create",
        resource_type="lab_exam_booking",
        resource_id=booking["id"],
        detail=f"UI创建检查预约 item={body.itemId} slot={body.slotId}",
    )
    return _ui_booking(booking)


@ui_router.get("/api/exam-bookings")
@ui_router.get("/api/exam-bookings/")
def ui_list_exam_bookings(patientId: Optional[str] = Query(None)) -> dict:
    items = [_ui_booking(b) for b in store.list_lab_exam_bookings(patient_id=patientId)]
    return {"items": items, "disclaimer": store.LAB_EXAM_DISCLAIMER}


@ui_router.get("/api/exam-bookings/{booking_id}")
def ui_get_exam_booking(booking_id: str) -> dict:
    booking = store.get_lab_exam_booking(booking_id)
    if not booking:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{booking_id}"},
        )
    return _ui_booking(booking)


@ui_router.post("/api/exam-bookings/{booking_id}/reschedule")
def ui_reschedule_exam_booking(
    booking_id: str, body: RescheduleUiExamBookingRequest
) -> dict:
    if body.date:
        slot = store.get_lab_exam_slot(body.slotId)
        if slot and slot.get("date") != body.date:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "validation_error",
                    "message": f"号源日期 {slot.get('date')} 与请求 date {body.date} 不一致",
                },
            )
    try:
        booking = store.reschedule_lab_exam_booking(
            booking_id,
            slot_id=body.slotId,
            date=None,
            time=None,
        )
    except ValueError as e:
        raise _map_store_error(e) from e
    store.append_audit(
        action="lab_exam_booking.reschedule",
        resource_type="lab_exam_booking",
        resource_id=booking_id,
        detail=(
            f"UI改约#{booking.get('rescheduleCount')} "
            f"→ {booking.get('date')} {booking.get('time')} slot={booking.get('slotId')}"
        ),
    )
    return _ui_booking(booking)


@ui_router.post("/api/exam-bookings/{booking_id}/cancel")
def ui_cancel_exam_booking(
    booking_id: str, body: CancelUiExamBookingRequest = CancelUiExamBookingRequest()
) -> dict:
    reason = body.reason
    try:
        booking = store.cancel_lab_exam_booking(booking_id, reason=reason)
    except ValueError as e:
        raise _map_store_error(e) from e
    store.append_audit(
        action="lab_exam_booking.cancel",
        resource_type="lab_exam_booking",
        resource_id=booking_id,
        detail=f"UI取消检查预约 reason={reason or ''}",
    )
    return _ui_booking(booking)
