"""Previsit (诊前) doctor-facing report routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import ai_service, store
from app.models import PrevisitReportRequest

router = APIRouter(prefix="/api/previsit", tags=["previsit"])


@router.post("/report")
def create_previsit_report(body: PrevisitReportRequest) -> dict:
    """
    Generate a structured previsit summary for doctors.
    - With sessionId: AI-enrich + persist (same store as consult preconsult-report).
    - Without sessionId: AI from explicit structured fields (ephemeral JSON).
    """
    payload = body.model_dump(exclude_none=True)

    if body.sessionId:
        # Prefer shared builder (AI + persist + link session)
        from app.routes.consult import build_preconsult_report

        report = build_preconsult_report(body.sessionId, None)
        # Merge any extra explicit fields already baked via session; return doctor-friendly shape
        return {
            "id": report.get("id"),
            "sessionId": report.get("sessionId"),
            "chiefComplaint": report.get("chief") or (report.get("structuredSummary") or {}).get("chiefComplaint"),
            "presentIllness": report.get("presentIllness")
            or (report.get("structuredSummary") or {}).get("presentIllness"),
            "accompanying": report.get("accompanying")
            or (report.get("structuredSummary") or {}).get("accompanying")
            or [],
            "relevantHistory": report.get("relevantHistory")
            or (report.get("structuredSummary") or {}).get("relevantHistory")
            or "",
            "urgency": report.get("urgency")
            or (report.get("structuredSummary") or {}).get("urgency")
            or "routine",
            "suggestedDepartments": (
                report.get("suggestedDepartments")
                or (report.get("structuredSummary") or {}).get("suggestedDepartments")
                or (report.get("structuredSummary") or {}).get("departments")
                or (report.get("triage") or {}).get("departments")
                or []
            ),
            "patientNarrative": report.get("patientNarrative")
            or (report.get("structuredSummary") or {}).get("patientNarrative")
            or "",
            "redFlags": report.get("redFlags")
            or (report.get("structuredSummary") or {}).get("redFlags")
            or [],
            "doctorHints": report.get("doctorHints")
            or (report.get("structuredSummary") or {}).get("doctorHints")
            or [],
            "summaryText": report.get("summary")
            or (report.get("structuredSummary") or {}).get("summaryText")
            or "",
            "disclaimer": report.get("disclaimer") or ai_service.PREVISIT_DISCLAIMER,
            "source": report.get("source") or "mock",
            "generatedAt": report.get("generatedAt") or report.get("createdAt"),
            "patientId": report.get("patientId"),
            "patientName": report.get("patientName"),
            "error": report.get("error"),
            "message": report.get("message"),
            "persisted": True,
            "preconsultReportId": report.get("id"),
        }

    has_explicit = bool(
        body.chiefComplaint
        or body.patientNotes
        or body.extra
        or body.departments
        or body.accompanying
    )
    if not has_explicit:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "请提供 sessionId 或结构化主诉/症状输入",
            },
        )

    try:
        result = ai_service.generate_previsit_report(session=None, payload=payload)
        result["persisted"] = False
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": str(exc)},
        ) from exc
