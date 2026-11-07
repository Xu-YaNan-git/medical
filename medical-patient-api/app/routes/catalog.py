"""Departments / doctors / slots catalog."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import store

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/departments")
def list_departments() -> list[dict]:
    return store.list_departments()


@router.get("/departments/{department_id}/doctors")
def list_doctors(department_id: str) -> list[dict]:
    if not store.get_department(department_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"科室不存在：{department_id}"},
        )
    return store.list_doctors(department_id)


@router.get("/doctors/{doctor_id}/slots")
def list_slots(
    doctor_id: str,
    date: str = Query(..., description="YYYY-MM-DD"),
) -> list[dict]:
    if not store.get_doctor(doctor_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"医生不存在：{doctor_id}"},
        )
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "date 须为 YYYY-MM-DD"},
        )
    return store.list_slots(doctor_id, date)
