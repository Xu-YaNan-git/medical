"""Multi-turn consult session routes (JSON + optional SSE stream)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app import ai_service, guardrail_flow, store
from app import guardrails as gr
from app.ai_service import DISCLAIMER
from app.models import (
    CreatePreconsultFromSessionRequest,
    CreateSessionRequest,
    PostMessageRequest,
)

REPORT_DISCLAIMER = "辅助导诊/辅助解读，不替代面诊或医师诊断。"

router = APIRouter(prefix="/api/consult", tags=["consult"])


def _public_session(sess: dict) -> dict:
    return {
        "id": sess["id"],
        "messages": sess.get("messages") or [],
        "status": sess.get("status") or "active",
        "triage": sess.get("triage"),
        "patientId": sess.get("patientId"),
        "preconsultReportId": sess.get("preconsultReportId"),
    }


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _want_stream(
    request: Request,
    stream_q: Optional[bool],
    body_stream: Optional[bool],
) -> bool:
    if stream_q is True or body_stream is True:
        return True
    if stream_q is False or body_stream is False:
        return False
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _llm_public(result: dict | None, *, skipped: bool = False) -> dict:
    """Explicit model/fallback marker for the HTTP response. No secrets."""
    if skipped or not result:
        return {"fallback": False, "llmCalled": False, "llmStatus": "skipped"}
    status = result.get("llmStatus")
    if status not in ("ok", "error", "skipped"):
        status = "ok" if result.get("source") == "llm" else "skipped"
    return {
        "fallback": bool(result.get("fallback")),
        "llmCalled": bool(result.get("llmCalled")),
        "llmStatus": status,
    }


@router.post("/sessions")
def create_session(body: CreateSessionRequest = CreateSessionRequest()) -> dict:
    patient_id = None
    if body.patientId:
        patient_id = body.patientId
        if not store.get_patient(patient_id):
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"就诊人不存在：{patient_id}"},
            )
    sess = store.create_session(patient_id=patient_id)
    return _public_session(sess)


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"会话不存在：{session_id}"},
        )
    return _public_session(sess)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: PostMessageRequest,
    request: Request,
    stream: Optional[bool] = Query(
        None,
        description="true 时以 SSE 流式返回 token + final；默认非流式 JSON",
    ),
):
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "content 不能为空"},
        )

    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"会话不存在：{session_id}"},
        )
    if sess.get("status") == "completed":
        raise HTTPException(
            status_code=409,
            detail={"error": "session_completed", "message": "会话已结束，请新建会话"},
        )

    now = _now()
    # S2 guardrails: input check before anything reaches the LLM; the stored /
    # forwarded user text is the masked form (history is re-sent each turn).
    gi = guardrail_flow.guard_input(content, "POST /api/consult/sessions/{id}/messages")
    llm_content = gi.get("masked_text") or content
    user_msg = {"role": "user", "content": llm_content, "createdAt": now}
    sess["messages"].append(user_msg)
    want_stream = _want_stream(request, stream, body.stream)
    # Same guardrail object top-level and on the assistant message it produced (persisted).
    gfield = guardrail_flow.guardrail_field(gi)

    if gi["action"] != gr.ALLOW:
        # Short-circuit: NO LLM call, session not advanced, no auto pre-consult.
        ai_service.log_consult_llm(
            llm_called=False,
            llm_status="skipped",
            fallback=False,
            turns=int(sess.get("turns") or 0),
            history_count=len(sess.get("messages") or []),
            error_code="guardrail",
        )
        reply_text = guardrail_flow.consult_blocked_reply(gi)
        asst_msg = {"role": "assistant", "content": reply_text, "createdAt": now, "guardrail": gfield}
        sess["messages"].append(asst_msg)
        store.save_session(sess)
        sess = store.get_session(session_id) or sess
        payload = {
            "id": sess["id"],
            "messages": sess["messages"],
            "status": sess["status"],
            "reply": asst_msg,
            "triage": sess.get("triage"),
            "patientId": sess.get("patientId"),
            "preconsultReportId": sess.get("preconsultReportId"),
            "disclaimer": gr.disclaimer(),
            "source": "guardrail",
            "error": None,
            "message": reply_text,
            "guardrail": gfield,
            **_llm_public(None, skipped=True),
        }
        if not want_stream:
            return payload

        def blocked_gen():
            for i in range(0, len(reply_text), 12):
                yield _sse("token", {"text": reply_text[i : i + 12]})
            yield _sse("final", payload)
            yield _sse("done", {"ok": True})

        return StreamingResponse(
            blocked_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    if want_stream:
        def event_gen():
            sess_cur = sess
            final = None
            try:
                # consult_turn_stream chunks a complete reply, so we drain it,
                # run the output guardrail on the full reply, then re-chunk.
                for ev in ai_service.consult_turn_stream(sess_cur, llm_content):
                    if ev.get("type") == "final":
                        final = ev
                if final is None:
                    raise RuntimeError("流式问诊未返回 final")
                reply_text = guardrail_flow.guard_output_text(str(final.get("reply") or ""))
                for i in range(0, len(reply_text), 12):
                    yield _sse("token", {"text": reply_text[i : i + 12]})

                asst_msg = {
                    "role": "assistant",
                    "content": reply_text,
                    "createdAt": now,
                    "guardrail": gfield,
                }
                sess_cur["messages"].append(asst_msg)
                if final.get("status") == "completed":
                    sess_cur["status"] = "completed"
                if final.get("triage"):
                    sess_cur["triage"] = final["triage"]
                store.save_session(sess_cur)
                _maybe_auto_preconsult(sess_cur)
                sess_cur = store.get_session(session_id) or sess_cur

                payload = {
                    "id": sess_cur["id"],
                    "messages": sess_cur["messages"],
                    "status": sess_cur["status"],
                    "reply": asst_msg,
                    "triage": sess_cur.get("triage"),
                    "patientId": sess_cur.get("patientId"),
                    "preconsultReportId": sess_cur.get("preconsultReportId"),
                    "disclaimer": final.get("disclaimer") or DISCLAIMER,
                    "source": final.get("source") or "mock",
                    "error": final.get("error"),
                    "message": final.get("message"),
                    "guardrail": gfield,
                    **_llm_public(final),
                }
                yield _sse("final", payload)
                yield _sse("done", {"ok": True})
            except Exception as exc:
                err = {"error": "stream_error", "message": gr.mask_pii(str(exc))}
                yield _sse("error", err)

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = ai_service.consult_turn(sess, llm_content)
    reply_text = guardrail_flow.guard_output_text(str(result.get("reply") or ""))
    asst_msg = {
        "role": "assistant",
        "content": reply_text,
        "createdAt": now,
        "guardrail": gfield,
    }
    sess["messages"].append(asst_msg)
    if result.get("status") == "completed":
        sess["status"] = "completed"
    if result.get("triage"):
        sess["triage"] = result["triage"]

    store.save_session(sess)
    _maybe_auto_preconsult(sess)
    # reload for linked report id
    sess = store.get_session(session_id) or sess

    return {
        "id": sess["id"],
        "messages": sess["messages"],
        "status": sess["status"],
        "reply": asst_msg,
        "triage": sess.get("triage"),
        "patientId": sess.get("patientId"),
        "preconsultReportId": sess.get("preconsultReportId"),
        "disclaimer": result.get("disclaimer") or DISCLAIMER,
        "source": result.get("source") or "mock",
        "error": result.get("error"),
        "message": result.get("message"),
        "guardrail": gfield,
        **_llm_public(result),
    }


def build_preconsult_report(session_id: str, patient_id: str | None = None) -> dict:
    """Build & persist a pre-consult report from a consult session."""
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"会话不存在：{session_id}"},
        )

    existing = store.find_preconsult_by_session(session_id)
    if existing:
        return existing

    pid = patient_id or sess.get("patientId")
    patient_name = None
    if pid:
        pat = store.get_patient(pid)
        if not pat:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"就诊人不存在：{pid}"},
            )
        patient_name = pat.get("name")

    triage = sess.get("triage") or {}
    messages = sess.get("messages") or []

    # S2: chief complaint goes through check_input BEFORE any prompt is built;
    # the prompt only ever sees masked_text. redflag → rules-only report (flagged);
    # refuse → no LLM, neutral report.
    chief_in = str(
        (sess.get("facts") or {}).get("chief")
        or triage.get("chiefComplaint")
        or next((m.get("content") for m in messages if m.get("role") == "user" and m.get("content")), "")
        or ""
    )[:200]
    gi = guardrail_flow.guard_input(chief_in, "POST /api/consult/sessions/{id}/preconsult-report") if chief_in.strip() else gr.check_input("", "patient")
    refused = gi["action"] == gr.REFUSE
    redflag = gi["action"] == gr.REDFLAG

    ai_report = None
    try:
        if refused:
            raise LookupError("guardrail refuse: no LLM")
        sess_mut = dict(sess)
        sess_mut["facts"] = dict(sess.get("facts") or {})
        sess_mut["messages"] = list(messages)
        if triage:
            sess_mut["triage"] = dict(triage)
        # prompt input only ever sees masked text (chief + user messages + facts)
        sess_mut["messages"] = [
            ({**m, "content": gr.mask_pii(str(m.get("content") or ""))} if m.get("role") == "user" else m)
            for m in (sess_mut.get("messages") or [])
        ]
        if sess_mut.get("facts"):
            sess_mut["facts"] = {k: (gr.mask_pii(v) if isinstance(v, str) else v) for k, v in sess_mut["facts"].items()}
        payload: dict = {}
        if chief_in.strip():
            payload["chiefComplaint"] = gi.get("masked_text") or gr.mask_pii(chief_in)
        if redflag and not sess_mut.get("triage"):
            # avoid force_summary → recommend_triage (LLM) on a redflag session
            from app import ai_mock
            sess_mut["triage"] = {**ai_mock.recommend(chief=payload["chiefComplaint"], duration="", body_part="",
                                                     severity=None, age=None, gender=None, extra=None),
                                  "urgency": "emergency"}
        if pid:
            prof = store.get_profile(pid) or {}
            if prof.get("allergies"):
                payload["allergies"] = "、".join(prof["allergies"])
            if prof.get("medications"):
                payload["medications"] = "、".join(prof["medications"])
            if prof.get("chronicDiseases"):
                payload["pastHistory"] = "慢病：" + "、".join(prof["chronicDiseases"])
            pat = store.get_patient(pid)
            if pat:
                payload["age"] = pat.get("age")
                payload["gender"] = pat.get("gender")
        ai_report = ai_service.generate_previsit_report(
            session=sess_mut, payload=payload or None, use_llm=not redflag
        )
        if sess_mut.get("triage"):
            sess["triage"] = sess_mut["triage"]
            triage = sess["triage"]
        if sess_mut.get("status") == "completed":
            sess["status"] = "completed"
    except Exception:
        ai_report = None
    ar = ai_report or {}  # empty / refused session → no AI report; never .get() on None

    chief = (
        (ai_report or {}).get("chiefComplaint")
        or triage.get("chiefComplaint")
        or triage.get("summary")
        or next((m["content"] for m in messages if m.get("role") == "user"), "")
        or ""
    )
    accompanying = (ai_report or {}).get("accompanying") or triage.get("accompanying") or []
    depts = (ai_report or {}).get("suggestedDepartments") or triage.get("departments") or []
    summary = (
        (ai_report or {}).get("summaryText")
        or (ai_report or {}).get("presentIllness")
        or ""
    )
    if not summary:
        parts = []
        if chief:
            parts.append(f"主诉/主要不适：{chief}")
        if accompanying:
            parts.append("伴随症状：" + "、".join(str(x) for x in accompanying))
        if depts:
            parts.append(
                "建议科室："
                + "、".join(
                    f"{d.get('name')}（{d.get('reason', '')}）" for d in depts[:3]
                )
            )
        urg = (ai_report or {}).get("urgency") or triage.get("urgency")
        if urg:
            parts.append(f"急诊分级建议：{urg}")
        summary = "\n".join(parts) if parts else (chief or "（问诊摘要待补充）")

    depts = (
        ar.get("suggestedDepartments")
        or triage.get("departments")
        or []
    )
    structured = {
        "chiefComplaint": ar.get("chiefComplaint"),
        "presentIllness": ar.get("presentIllness"),
        "accompanying": ar.get("accompanying") or [],
        "relevantHistory": ar.get("relevantHistory"),
        "urgency": ar.get("urgency"),
        "suggestedDepartments": depts,
        "patientNarrative": ar.get("patientNarrative"),
        "redFlags": ar.get("redFlags") or [],
        "doctorHints": ar.get("doctorHints") or [],
        "summaryText": ar.get("summaryText"),
        "departments": depts,
        "suggestOnline": triage.get("suggestOnline"),
        "nextSteps": triage.get("nextSteps") or [],
        "facts": sess.get("facts") or {},
    }

    gfield = guardrail_flow.guardrail_field(gi)
    source = (ar.get("source")
              or (triage.get("source") if isinstance(triage, dict) else None)
              or "mock")
    if refused:
        chief = ""
        accompanying, depts = [], []
        summary = "（主诉内容未通过安全策略检查，未生成 AI 摘要；请医生面诊时直接询问病情。）"
        structured.update(chiefComplaint=None, suggestedDepartments=[], departments=[], accompanying=[])
        source = "guardrail"
    elif redflag:
        structured["urgency"] = "emergency"
        flag = f"⚠️ 急危红旗：{gfield.get('advice')}"
        if flag not in structured["redFlags"]:
            structured["redFlags"] = [flag] + list(structured["redFlags"])
        source = "guardrail"
    report = store.create_preconsult_report(
        {
            "patientId": pid,
            "patientName": patient_name,
            "sessionId": session_id,
            "chief": chief,
            "summary": summary,
            "structuredSummary": structured,
            "triage": triage or None,
            "aiReport": ai_report,
            "sessionStatus": sess.get("status"),
            "disclaimer": (ai_report or {}).get("disclaimer") or REPORT_DISCLAIMER,
            "source": source,
            "guardrail": gfield,
        }
    )

    sess["preconsultReportId"] = report["id"]
    if pid and not sess.get("patientId"):
        sess["patientId"] = pid
    store.save_session(sess)
    return report


def _maybe_auto_preconsult(sess: dict) -> None:
    """When consult completes and patientId is set, auto-create report once."""
    if sess.get("status") != "completed":
        return
    if not sess.get("patientId"):
        return
    if sess.get("preconsultReportId"):
        return
    if store.find_preconsult_by_session(sess["id"]):
        return
    try:
        report = build_preconsult_report(sess["id"], sess.get("patientId"))
        sess["preconsultReportId"] = report["id"]
        store.save_session(sess)
    except Exception:
        pass


@router.post("/sessions/{session_id}/preconsult-report", status_code=201)
def create_preconsult_from_session(
    session_id: str,
    body: CreatePreconsultFromSessionRequest = CreatePreconsultFromSessionRequest(),
) -> dict:
    return build_preconsult_report(session_id, body.patientId)
