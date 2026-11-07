"""M4 缴费 Mock（不发生真实扣款）."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("")
@router.get("/")
def list_bills(patientId: Optional[str] = Query(None)) -> dict:
    items = store.list_bills(patient_id=patientId)
    return {"items": items, "disclaimer": store.BILL_DISCLAIMER}


@router.get("/{bill_id}")
def get_bill(bill_id: str) -> dict:
    bill = store.get_bill(bill_id)
    if not bill:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"账单不存在：{bill_id}"},
        )
    return bill


@router.post("/{bill_id}/pay")
def pay_bill(bill_id: str) -> dict:
    bill = store.pay_bill(bill_id)
    if not bill:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"账单不存在：{bill_id}"},
        )
    return bill
