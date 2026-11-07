"""M3 随访问卷 + 医生收件箱别名."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import FollowupSubmitRequest

router = APIRouter(prefix="/api/followups", tags=["followups"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


@router.get("/surveys")
def list_surveys() -> dict:
    items = store.list_followup_surveys()
    return {
        "items": items,
        "disclaimer": store.FOLLOWUP_DISCLAIMER,
    }


@router.post("/surveys/{survey_id}/submit")
def submit_survey(survey_id: str, body: FollowupSubmitRequest) -> dict:
    try:
        item = store.submit_followup_response(
            survey_id,
            {
                "patientId": body.patientId,
                "answers": body.answers or {},
            },
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"问卷不存在：{survey_id}"},
        )
    return item


@router.get("/responses")
def list_responses(
    patientId: Optional[str] = Query(None),
) -> dict:
    items = store.list_followup_responses(patient_id=patientId)
    return {
        "items": items,
        "disclaimer": store.FOLLOWUP_DISCLAIMER,
    }


@router.get("/inbox")
def followups_inbox_alias() -> dict:
    """Alias for doctor inbox on patient API (no auth for MVP)."""
    items = store.list_doctor_followups()
    return {
        "items": items,
        "disclaimer": store.FOLLOWUP_DISCLAIMER,
    }


@router.get("/inbox/{response_id}")
def followups_inbox_detail_alias(response_id: str) -> dict:
    item = store.get_followup_response(response_id)
    if not item:
        raise _err(404, "not_found", f"随访回复不存在：{response_id}")
    return item
