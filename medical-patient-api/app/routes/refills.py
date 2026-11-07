"""M3 复诊续方申请（Mock，不真开方）."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import CreateRefillRequest, PatchRefillRequest

router = APIRouter(prefix="/api/refills", tags=["refills"])

_ALLOWED = {"pending", "approved", "rejected", "cancelled"}


@router.get("")
@router.get("/")
def list_refills(
    patientId: Optional[str] = Query(None),
) -> dict:
    items = store.list_refills(patient_id=patientId)
    return {
        "items": items,
        "disclaimer": store.REFILL_DISCLAIMER,
    }


@router.post("")
@router.post("/")
def create_refill(body: CreateRefillRequest) -> dict:
    name = (body.medicationName or "").strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "medicationName 必填"},
        )
    item = store.create_refill(
        {
            "patientId": body.patientId,
            "medicationName": name,
            "dosage": body.dosage,
            "quantity": body.quantity,
            "reason": body.reason,
            "departmentId": body.departmentId,
        }
    )
    store.append_audit(
        action="refill.create",
        resource_type="refill",
        resource_id=item["id"],
        detail=f"新建续方申请 medication={name} patientId={body.patientId or ''}",
    )
    return item


@router.get("/{refill_id}")
def get_refill(refill_id: str) -> dict:
    item = store.get_refill(refill_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"续方申请不存在：{refill_id}"},
        )
    return item


@router.patch("/{refill_id}")
def patch_refill(refill_id: str, body: PatchRefillRequest) -> dict:
    if body.status not in _ALLOWED:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": f"status 须为 {sorted(_ALLOWED)}",
            },
        )
    item = store.update_refill(
        refill_id,
        {"status": body.status, "reviewNote": body.reviewNote},
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"续方申请不存在：{refill_id}"},
        )
    store.append_audit(
        action="refill.patch",
        resource_type="refill",
        resource_id=refill_id,
        detail=f"更新续方状态 status={body.status}",
    )
    return item
