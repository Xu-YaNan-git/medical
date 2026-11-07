"""就诊人 CRUD + 健康档案."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app import store
from app.models import CreatePatientRequest, HealthProfile, PatchPatientRequest

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


@router.get("")
def list_patients() -> list[dict]:
    return store.list_patients()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_patient(body: CreatePatientRequest) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise _err(422, "validation_error", "name 不能为空")
    pat = store.create_patient(
        {
            "name": name,
            "gender": body.gender,
            "age": body.age,
            "relation": body.relation or "self",
        }
    )
    store.append_audit(
        action="patient.create",
        resource_type="patient",
        resource_id=pat["id"],
        detail=f"新建就诊人 relation={pat.get('relation')} gender={pat.get('gender')} age={pat.get('age')}",
    )
    return pat


@router.get("/{patient_id}")
def get_patient(patient_id: str) -> dict:
    pat = store.get_patient(patient_id)
    if not pat:
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    return pat


@router.patch("/{patient_id}")
def patch_patient(patient_id: str, body: PatchPatientRequest) -> dict:
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        patch["name"] = str(patch["name"]).strip()
        if not patch["name"]:
            raise _err(422, "validation_error", "name 不能为空")
    pat = store.update_patient(patient_id, patch)
    if not pat:
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    store.append_audit(
        action="patient.patch",
        resource_type="patient",
        resource_id=patient_id,
        detail=f"更新就诊人 fields={list(patch.keys())}",
    )
    return pat


# Alias: PUT also accepted for clients that prefer full replace-ish update
@router.put("/{patient_id}")
def put_patient(patient_id: str, body: PatchPatientRequest) -> dict:
    return patch_patient(patient_id, body)


@router.delete("/{patient_id}")
def delete_patient(patient_id: str) -> dict:
    ok = store.delete_patient(patient_id)
    if not ok:
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    return {"ok": True, "id": patient_id}


@router.get("/{patient_id}/profile")
def get_profile(patient_id: str) -> dict:
    prof = store.get_profile(patient_id)
    if prof is None:
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    return prof


@router.put("/{patient_id}/profile")
def put_profile(patient_id: str, body: HealthProfile) -> dict:
    prof = store.update_profile(
        patient_id,
        {
            "allergies": list(body.allergies or []),
            "chronicDiseases": list(body.chronicDiseases or []),
            "medications": list(body.medications or []),
            "bloodType": body.bloodType or "",
            "notes": body.notes or "",
        },
    )
    if prof is None:
        raise _err(404, "not_found", f"就诊人不存在：{patient_id}")
    return prof
