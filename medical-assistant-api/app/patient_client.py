"""HTTP client to patient API (8001) for pre-consult reports and workbench."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

PATIENT_API_BASE = os.environ.get("PATIENT_API_BASE", "http://127.0.0.1:8001").rstrip("/")


class PatientApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str):
        self.status_code = status_code
        self.error = error
        self.message = message
        super().__init__(message)


def _request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    json: Optional[dict] = None,
    retry_once: bool = True,
) -> Any:
    url = f"{PATIENT_API_BASE}{path}"
    last_exc: Optional[Exception] = None
    attempts = 2 if retry_once else 1
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.request(
                    method, url, params=params, headers=headers, json=json
                )
            break
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                raise PatientApiError(
                    503,
                    "patient_api_unavailable",
                    f"患者端 API 不可用（{PATIENT_API_BASE}）：{exc}",
                ) from exc
    else:
        raise PatientApiError(
            503,
            "patient_api_unavailable",
            f"患者端 API 不可用（{PATIENT_API_BASE}）：{last_exc}",
        )

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {"error": "upstream_error", "message": resp.text[:300]}
        if isinstance(body, dict):
            err = str(body.get("error") or "upstream_error")
            msg = str(
                body.get("message") or resp.text[:300] or f"HTTP {resp.status_code}"
            )
        else:
            err = "upstream_error"
            msg = str(body)[:300]
        raise PatientApiError(resp.status_code, err, msg)
    if resp.status_code == 204:
        return None
    return resp.json()


def normalize_items(payload: Any) -> dict:
    """Normalize upstream list payloads to `{items: [...]}`."""
    if isinstance(payload, list):
        return {"items": payload}
    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            return payload
        # Some endpoints return {reports: [...]} etc.
        for key in ("reports", "data", "results"):
            if key in payload and isinstance(payload[key], list):
                out = dict(payload)
                out["items"] = out.pop(key)
                return out
        return payload
    return {"items": []}


def get_preconsult_report(report_id: str) -> dict:
    return _request("GET", f"/api/doctor/preconsult/{report_id}")


def list_preconsult_reports(
    *, patient_id: Optional[str] = None, patient_name: Optional[str] = None
) -> Any:
    params = {}
    if patient_id:
        params["patientId"] = patient_id
    if patient_name:
        params["patientName"] = patient_name
    return _request("GET", "/api/doctor/preconsult", params=params or None)


def list_doctor_consult_queue(
    *, status: str = "waiting_doctor", role: str = "doctor"
) -> Any:
    return _request(
        "GET",
        "/api/doctor-consult/sessions",
        params={"role": role, "status": status},
        headers={"X-Role": "doctor", "Authorization": "Bearer doctor"},
    )


def ping() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{PATIENT_API_BASE}/health")
        return resp.status_code == 200
    except httpx.RequestError:
        return False


def list_followup_inbox() -> Any:
    """Doctor follow-up inbox from patient API; try primary then alias."""
    try:
        return _request("GET", "/api/doctor/followups")
    except PatientApiError as exc:
        if exc.status_code in (404, 405):
            return _request("GET", "/api/followups/inbox")
        raise


def get_followup_response(response_id: str) -> dict:
    try:
        return _request("GET", f"/api/doctor/followups/{response_id}")
    except PatientApiError as exc:
        if exc.status_code in (404, 405):
            return _request("GET", f"/api/followups/inbox/{response_id}")
        raise


def list_chronic_patients() -> Any:
    return _request("GET", "/api/doctor/chronic/patients")


def list_chronic_vitals(patient_id: str) -> Any:
    return _request("GET", f"/api/doctor/chronic/patients/{patient_id}/vitals")


def get_chronic_summary(patient_id: str) -> Any:
    return _request("GET", f"/api/doctor/chronic/patients/{patient_id}/summary")


def list_chronic_inbox() -> Any:
    return _request("GET", "/api/doctor/chronic/inbox")


def mark_chronic_alert_read(alert_id: str) -> Any:
    return _request("POST", f"/api/doctor/chronic/inbox/{alert_id}/read", json={})


def chronic_unread_count() -> int:
    """Best-effort unread chronic alerts for workbench badge."""
    try:
        raw = list_chronic_inbox()
        if isinstance(raw, dict):
            if "unreadCount" in raw:
                return int(raw.get("unreadCount") or 0)
            items = raw.get("items") or []
            return len(items) if isinstance(items, list) else 0
    except PatientApiError:
        return 0
    return 0


def list_appointments() -> Any:
    return _request("GET", "/api/appointments")


def list_pharmacy_deliveries() -> Any:
    return _request("GET", "/api/pharmacy/deliveries")


def list_refills(*, status: Optional[str] = None) -> Any:
    params = {"status": status} if status else None
    return _request("GET", "/api/refills", params=params)


def list_patient_audit(*, limit: int = 200) -> Any:
    return _request("GET", "/api/audit", params={"limit": limit})


def get_guardrail_stats() -> Any:
    """S2: patient-side guardrail hit counts (scrubbed audit aggregation)."""
    return _request("GET", "/api/guardrails/stats")
