"""报告中心 Mock（检验/检查）+ 预问诊报告读写 + AI 解读钩子.

Route order matters: static paths (/interpret, /preconsult, /labs) BEFORE /{report_id}.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app import ai_service, guardrail_flow, store
from app.models import CreatePreconsultRequest, ReportInterpretRequest

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORT_DISCLAIMER = "辅助导诊/辅助解读，不替代面诊或医师诊断。"


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


def _report_text(report: dict) -> str:
    parts: list[str] = []
    if report.get("name"):
        parts.append(f"报告名称：{report['name']}")
    if report.get("category"):
        parts.append(f"类别：{report['category']}")
    if report.get("summary"):
        parts.append(f"摘要：{report['summary']}")
    for it in report.get("items") or []:
        line = it.get("name") or "项目"
        if it.get("value") is not None:
            line += f"：{it.get('value')}"
        if it.get("unit"):
            line += f" {it.get('unit')}"
        if it.get("ref"):
            line += f"（参考 {it.get('ref')}）"
        if it.get("flag"):
            line += f" [{it.get('flag')}]"
        parts.append(line)
    return "\n".join(parts)


def _do_interpret(report: dict) -> dict:
    text = _report_text(report)
    rtype = report.get("type") or "other"
    if rtype not in ("lab", "imaging", "other"):
        rtype = "other"
    try:
        result = guardrail_flow.interpret(
            text,
            rtype,
            f"POST /api/reports/{{id}}/interpret",
            lambda masked: ai_service.interpret_report(text=masked, report_type=rtype),
        )
    except ValueError as exc:
        raise _err(422, "validation_error", str(exc)) from exc
    out = dict(result)
    out["reportId"] = report["id"]
    if not out.get("disclaimer"):
        out["disclaimer"] = REPORT_DISCLAIMER
    store.notify_report_interpreted(report)
    return out


# ---------- Static paths first ----------
@router.get("")
def list_reports(patientId: Optional[str] = Query(None)) -> list[dict]:
    """报告中心列表（检验/检查 Mock）。"""
    return store.list_lab_reports(patient_id=patientId)


@router.post("/interpret")
def interpret_text(body: ReportInterpretRequest) -> dict:
    """自由文本解读（AI 钩子）。可选 body.reportId 拉取 Mock 报告文本。"""
    text = (body.text or "").strip()
    report_type = body.reportType
    report_id = getattr(body, "reportId", None)
    if not text and report_id:
        r = store.get_lab_report(str(report_id))
        if not r:
            raise _err(404, "not_found", f"报告不存在：{report_id}")
        text = _report_text(r)
        report_type = report_type or r.get("type")
    if not text:
        raise _err(422, "validation_error", "text 或 reportId 至少提供一个")
    try:
        result = guardrail_flow.interpret(
            text,
            report_type,
            "POST /api/reports/interpret",
            lambda masked: ai_service.interpret_report(text=masked, report_type=report_type),
        )
    except ValueError as exc:
        raise _err(422, "validation_error", str(exc)) from exc
    if report_id:
        result = dict(result)
        result["reportId"] = report_id
        r = store.get_lab_report(str(report_id))
        if r:
            store.notify_report_interpreted(r)
        else:
            store.notify_report_interpreted({"id": str(report_id), "name": "检查/检验"})
    else:
        store.notify_report_interpreted({"id": "", "name": "自由文本报告"})
    return result


@router.get("/preconsult")
def list_preconsult(patientId: Optional[str] = Query(None)) -> list[dict]:
    return store.list_preconsult_reports(patient_id=patientId)


@router.post("/preconsult", status_code=status.HTTP_201_CREATED)
def create_preconsult(body: CreatePreconsultRequest) -> dict:
    from app.routes.consult import build_preconsult_report

    return build_preconsult_report(body.sessionId, body.patientId)


@router.get("/preconsult/{report_id}")
def get_preconsult(report_id: str) -> dict:
    r = store.get_preconsult_report(report_id)
    if not r:
        raise _err(404, "not_found", f"预问诊报告不存在：{report_id}")
    return r


@router.get("/labs")
def list_labs(patientId: Optional[str] = Query(None)) -> list[dict]:
    return store.list_lab_reports(patient_id=patientId)


@router.get("/labs/{report_id}")
def get_lab(report_id: str) -> dict:
    r = store.get_lab_report(report_id)
    if not r:
        raise _err(404, "not_found", f"检验/检查报告不存在：{report_id}")
    return r


@router.post("/labs/{report_id}/interpret")
def interpret_lab(report_id: str) -> dict:
    r = store.get_lab_report(report_id)
    if not r:
        raise _err(404, "not_found", f"检验/检查报告不存在：{report_id}")
    return _do_interpret(r)


# ---------- Parameterized paths last ----------
@router.get("/{report_id}")
def get_report(report_id: str) -> dict:
    r = store.get_lab_report(report_id)
    if r:
        return r
    r = store.get_preconsult_report(report_id)
    if r:
        return r
    raise _err(404, "not_found", f"报告不存在：{report_id}")


@router.post("/{report_id}/interpret")
def interpret_report_by_id(report_id: str) -> dict:
    r = store.get_lab_report(report_id)
    if not r:
        raise _err(404, "not_found", f"检验/检查报告不存在：{report_id}")
    return _do_interpret(r)
