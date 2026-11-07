"""M5 兼容别名 /api/consultations* + /api/doctor/consultations*（需求整理口径）.

主路径见 doctor_consult.py → /api/doctor-consult/sessions。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app import store
from app.models import (
    CreateConsultationRequest,
    DoctorReplyRequest,
    PatchConsultationStatusRequest,
    PostConsultationMessageRequest,
)

router = APIRouter(tags=["consultations-alias"])
doctor_router = APIRouter(prefix="/api/doctor/consultations", tags=["doctor-consultations-alias"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


def _is_doctor(
    request: Request,
    x_role: Optional[str] = None,
    authorization: Optional[str] = None,
) -> bool:
    role = (x_role or request.headers.get("X-Role") or "").strip().lower()
    if role == "doctor":
        return True
    auth = (authorization or request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip().lower()
        if token in ("doctor", "doctor-demo"):
            return True
    return False


def _require_doctor(request: Request, x_role: Optional[str], authorization: Optional[str]) -> None:
    if not _is_doctor(request, x_role, authorization):
        raise _err(
            403,
            "forbidden",
            "需要医生身份：请传 Header X-Role: doctor 或 Authorization: Bearer doctor",
        )


# ---------- Patient-facing alias /api/consultations ----------
@router.post("/api/consultations")
@router.post("/api/consultations/")
def create_consultation(body: CreateConsultationRequest) -> dict:
    mode = body.mode or body.type or "text"
    try:
        return store.create_consultation(
            {
                "mode": mode,
                "type": mode,
                "patientId": body.patientId,
                "departmentId": body.departmentId,
                "departmentName": body.departmentName,
                "doctorId": body.doctorId,
                "chief": body.chief,
                "chiefComplaint": body.chiefComplaint or body.chief,
                "reason": body.reason,
            },
            shape="alias",
        )
    except ValueError as e:
        raise _err(422, "validation_error", str(e)) from e


@router.get("/api/consultations")
@router.get("/api/consultations/")
def list_consultations(
    patientId: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctype: Optional[str] = Query(None, alias="type"),
) -> dict:
    items = store.list_consultations(
        patient_id=patientId, status=status, ctype=ctype, shape="alias"
    )
    return {"items": items, "disclaimer": store.CONSULTATION_DISCLAIMER}


@router.get("/api/consultations/{consultation_id}")
def get_consultation(consultation_id: str) -> dict:
    item = store.get_consultation(consultation_id, include_messages=True, shape="alias")
    if not item:
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    return item


@router.post("/api/consultations/{consultation_id}/end")
def end_consultation_patient(
    consultation_id: str,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    actor = "doctor" if _is_doctor(request, x_role, authorization) else "patient"
    item = store.end_consultation(consultation_id, actor=actor, shape="alias")
    if not item:
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    return item


@router.get("/api/consultations/{consultation_id}/messages")
def list_messages(consultation_id: str) -> dict:
    msgs = store.list_consultation_messages(consultation_id)
    if msgs is None:
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    return {"items": msgs, "disclaimer": store.CONSULTATION_DISCLAIMER}


@router.post("/api/consultations/{consultation_id}/messages")
def post_message(
    consultation_id: str,
    body: PostConsultationMessageRequest,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    role = (body.senderRole or body.role or "patient").strip().lower()
    if role == "doctor":
        _require_doctor(request, x_role, authorization)
    content = (body.content or "").strip()
    if not content:
        raise _err(422, "validation_error", "content 必填")
    msg, err = store.add_consultation_message(
        consultation_id,
        content=content,
        sender_role=role,
        allow_queued=(role == "patient"),
    )
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    if err == "ended":
        raise _err(409, "conflict", "会话已结束，无法发消息")
    if err == "not_in_progress":
        raise _err(409, "conflict", "当前状态不可发消息")
    if err == "empty":
        raise _err(422, "validation_error", "content 必填")
    return msg  # type: ignore[return-value]


@router.patch("/api/consultations/{consultation_id}")
def patch_consultation(
    consultation_id: str,
    body: PatchConsultationStatusRequest,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    if body.status in ("in_progress", "ended"):
        _require_doctor(request, x_role, authorization)
    item, err = store.patch_consultation_status(
        consultation_id, body.status, actor="doctor", shape="alias"
    )
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    if err:
        raise _err(409, "conflict", f"状态变更失败：{err}")
    return item  # type: ignore[return-value]


# ---------- Doctor alias /api/doctor/consultations ----------
@doctor_router.get("")
@doctor_router.get("/")
def doctor_list(
    request: Request,
    status: Optional[str] = Query("queued"),
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    _require_doctor(request, x_role, authorization)
    items = store.list_consultations(status=status or "queued", role="doctor", shape="alias")
    return {"items": items, "disclaimer": store.CONSULTATION_DISCLAIMER}


@doctor_router.post("/{consultation_id}/claim")
def doctor_claim(
    consultation_id: str,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    _require_doctor(request, x_role, authorization)
    item, err = store.claim_consultation(consultation_id, shape="alias")
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    if err == "ended":
        raise _err(409, "conflict", "会话已结束")
    if err == "invalid_status":
        raise _err(409, "conflict", "当前状态不可接诊")
    return item  # type: ignore[return-value]


@doctor_router.post("/{consultation_id}/reply")
def doctor_reply(
    consultation_id: str,
    body: DoctorReplyRequest,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    _require_doctor(request, x_role, authorization)
    content = (body.content or "").strip()
    if not content:
        raise _err(422, "validation_error", "content 必填")
    item, err = store.doctor_reply_consultation(consultation_id, content, shape="alias")
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    if err == "ended":
        raise _err(409, "conflict", "会话已结束")
    if err == "not_in_progress":
        raise _err(409, "conflict", "需先接诊再回复")
    return item  # type: ignore[return-value]


@doctor_router.post("/{consultation_id}/end")
def doctor_end(
    consultation_id: str,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    _require_doctor(request, x_role, authorization)
    item = store.end_consultation(consultation_id, actor="doctor", shape="alias")
    if not item:
        raise _err(404, "not_found", f"接诊会话不存在：{consultation_id}")
    return item
