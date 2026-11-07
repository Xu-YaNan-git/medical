"""M5 图文/视频接诊 — 产品 UI 主路径 /api/doctor-consult/sessions.

勿与 AI 导诊 /api/consult/sessions 混用。无真 WebRTC。
医生鉴权：X-Role: doctor 或 Authorization: Bearer doctor / Bearer doctor-demo。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app import store
from app.models import (
    CreateDoctorConsultSessionRequest,
    EndDoctorConsultRequest,
    PostConsultationMessageRequest,
)

router = APIRouter(prefix="/api/doctor-consult/sessions", tags=["doctor-consult"])


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


def _require_doctor(
    request: Request,
    x_role: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    if not _is_doctor(request, x_role, authorization):
        raise _err(
            403,
            "forbidden",
            "需要医生身份：请传 Header X-Role: doctor 或 Authorization: Bearer doctor",
        )


@router.post("")
@router.post("/")
def create_session(body: CreateDoctorConsultSessionRequest) -> dict:
    try:
        return store.create_consultation(
            {
                "mode": body.mode,
                "patientId": body.patientId,
                "chiefComplaint": body.chiefComplaint,
                "departmentName": body.departmentName,
                "departmentId": body.departmentId,
                "doctorId": body.doctorId,
            },
            shape="doctor",
        )
    except ValueError as e:
        raise _err(422, "validation_error", str(e)) from e


@router.get("")
@router.get("/")
def list_sessions(
    role: Optional[str] = Query(None, description="patient|doctor"),
    status: Optional[str] = Query(None),
    patientId: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
) -> dict:
    items = store.list_consultations(
        patient_id=patientId,
        status=status,
        ctype=mode,
        role=role,
        shape="doctor",
    )
    return {"items": items, "disclaimer": store.CONSULTATION_DISCLAIMER}


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    item = store.get_consultation(session_id, include_messages=True, shape="doctor")
    if not item:
        raise _err(404, "not_found", f"接诊会话不存在：{session_id}")
    return item


@router.post("/{session_id}/accept")
def accept_session(
    session_id: str,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    _require_doctor(request, x_role, authorization)
    item, err = store.claim_consultation(session_id, shape="doctor")
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{session_id}")
    if err == "ended":
        raise _err(409, "conflict", "会话已结束，无法接诊")
    if err == "invalid_status":
        raise _err(409, "conflict", "当前状态不可接诊")
    return item  # type: ignore[return-value]


@router.get("/{session_id}/messages")
def get_messages(session_id: str) -> dict:
    msgs = store.list_consultation_messages(session_id)
    if msgs is None:
        raise _err(404, "not_found", f"接诊会话不存在：{session_id}")
    return {"items": msgs, "disclaimer": store.CONSULTATION_DISCLAIMER}


@router.post("/{session_id}/messages")
def post_message(
    session_id: str,
    body: PostConsultationMessageRequest,
    request: Request,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    role = (body.role or body.senderRole or "patient").strip().lower()
    if role == "doctor":
        _require_doctor(request, x_role, authorization)
    content = (body.content or "").strip()
    if not content:
        raise _err(422, "validation_error", "content 必填")
    allow_queued = role == "patient"
    msg, err = store.add_consultation_message(
        session_id,
        content=content,
        sender_role=role,
        allow_queued=allow_queued,
    )
    if err == "not_found":
        raise _err(404, "not_found", f"接诊会话不存在：{session_id}")
    if err == "ended":
        raise _err(409, "conflict", "会话已结束，无法发消息")
    if err == "not_in_progress":
        raise _err(409, "conflict", "当前状态不可发消息（医生消息需已接诊）")
    if err == "empty":
        raise _err(422, "validation_error", "content 必填")
    return msg  # type: ignore[return-value]


@router.post("/{session_id}/end")
def end_session(
    session_id: str,
    request: Request,
    body: Optional[EndDoctorConsultRequest] = None,
    x_role: Optional[str] = Header(None, alias="X-Role"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    actor = "doctor" if _is_doctor(request, x_role, authorization) else "patient"
    summary = body.summary if body else None
    item = store.end_consultation(
        session_id, actor=actor, summary=summary, shape="doctor"
    )
    if not item:
        raise _err(404, "not_found", f"接诊会话不存在：{session_id}")
    return item
