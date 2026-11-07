"""M12 operations dashboard summary — aggregate local + patient API metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.patient_client import (
    PatientApiError,
    chronic_unread_count,
    get_guardrail_stats,
    list_appointments,
    list_doctor_consult_queue,
    list_followup_inbox,
    list_patient_audit,
    list_pharmacy_deliveries,
    list_refills,
    normalize_items,
    ping,
)
from app import guardrail_flow
from app.store import store

router = APIRouter(prefix="/api/ops", tags=["ops"])

DISCLAIMER = "演示运营数据，非真实院内部署指标。"
_TZ = ZoneInfo("Asia/Shanghai")

_ACTIVE_DELIVERY = {
    "pending",
    "shipped",
    "pending_shipment",
    "in_transit",
}


def _today_str() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _as_items(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    items = normalize_items(raw).get("items") or []
    return items if isinstance(items, list) else []


def _count_appointments_today(raw: Any, today: str) -> int:
    n = 0
    for item in _as_items(raw):
        if not isinstance(item, dict):
            continue
        date = (
            item.get("date")
            or item.get("slotDate")
            or item.get("appointmentDate")
            or ""
        )
        date_s = str(date)[:10]
        if date_s == today:
            n += 1
            continue
        # Fallback: createdAt starts with today
        created = str(item.get("createdAt") or "")[:10]
        if not date_s and created == today:
            n += 1
    return n


def _count_active_deliveries(raw: Any) -> int:
    n = 0
    for item in _as_items(raw):
        if not isinstance(item, dict):
            continue
        st = str(item.get("status") or "").lower()
        ui = str(item.get("uiStatus") or "").lower()
        if st in _ACTIVE_DELIVERY or ui in _ACTIVE_DELIVERY:
            n += 1
    return n


def _count_pending_refills(raw: Any) -> int:
    n = 0
    for item in _as_items(raw):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").lower() == "pending":
            n += 1
    return n


def _count_followups(raw: Any) -> int:
    if isinstance(raw, dict):
        if "unreadCount" in raw and raw.get("unreadCount") is not None:
            try:
                return int(raw.get("unreadCount") or 0)
            except (TypeError, ValueError):
                pass
        # Prefer unread items when a read flag exists
        items = raw.get("items") or []
        if isinstance(items, list) and items:
            if any(isinstance(x, dict) and "read" in x for x in items):
                return sum(
                    1
                    for x in items
                    if isinstance(x, dict) and not bool(x.get("read"))
                )
            return len(items)
        return 0
    return len(_as_items(raw))


def _count_audits_today_local(today: str) -> int:
    items = store.list_audit(limit=500)
    n = 0
    for item in items:
        created = str(item.get("createdAt") or "")[:10]
        if created == today:
            n += 1
    return n


def _count_audits_today_patient(today: str) -> Optional[int]:
    try:
        raw = list_patient_audit(limit=500)
        items = _as_items(raw)
        n = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            created = str(item.get("createdAt") or "")[:10]
            if created == today:
                n += 1
        return n
    except PatientApiError:
        return None


def _merge_counts(dst: dict[str, int], src: Any) -> None:
    if not isinstance(src, dict):
        return
    for k, v in src.items():
        try:
            dst[str(k)] = dst.get(str(k), 0) + int(v or 0)
        except (TypeError, ValueError):
            continue


def _guardrail_hits() -> dict[str, Any]:
    """S2: guardrail hits aggregated from doctor + patient audit (no raw text)."""
    local = guardrail_flow.stats()
    by_cat: dict[str, int] = {}
    by_act: dict[str, int] = {}
    _merge_counts(by_cat, local.get("byCategory"))
    _merge_counts(by_act, local.get("byAction"))
    total = int(local.get("total") or 0)
    patient_total: Optional[int] = None
    try:
        raw = get_guardrail_stats()
        if isinstance(raw, dict):
            patient_total = int(raw.get("total") or 0)
            total += patient_total
            _merge_counts(by_cat, raw.get("byCategory"))
            _merge_counts(by_act, raw.get("byAction"))
    except (PatientApiError, TypeError, ValueError):
        patient_total = None
    return {
        "total": total,
        "byCategory": by_cat,
        "byAction": by_act,
        "bySide": {"doctor": int(local.get("total") or 0), "patient": patient_total},
    }


@router.get("/summary")
def ops_summary(_user: str = Depends(require_auth)) -> dict[str, Any]:
    today = _today_str()
    errors: list[str] = []
    patient_ok = ping()

    appointments_today = 0
    waiting_consults = 0
    deliveries_active = 0
    refills_pending = 0
    followups_unread = 0
    chronic_abnormal = 0

    # --- patient API metrics (best-effort; zero on failure) ---
    try:
        appointments_today = _count_appointments_today(list_appointments(), today)
    except PatientApiError as exc:
        errors.append(f"appointments: {exc.message}")
        patient_ok = False

    try:
        raw_q = list_doctor_consult_queue(status="waiting_doctor")
        waiting_consults = len(_as_items(raw_q))
    except PatientApiError as exc:
        errors.append(f"waitingConsults: {exc.message}")
        patient_ok = False

    try:
        deliveries_active = _count_active_deliveries(list_pharmacy_deliveries())
    except PatientApiError as exc:
        errors.append(f"deliveries: {exc.message}")
        patient_ok = False

    try:
        raw_refills = list_refills()
        refills_pending = _count_pending_refills(raw_refills)
    except PatientApiError as exc:
        errors.append(f"refills: {exc.message}")
        patient_ok = False

    try:
        followups_unread = _count_followups(list_followup_inbox())
    except PatientApiError as exc:
        errors.append(f"followups: {exc.message}")
        patient_ok = False

    try:
        chronic_abnormal = int(chronic_unread_count())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"chronic: {exc}")
        patient_ok = False

    # Local audits + optional patient-side today count
    audits_local = _count_audits_today_local(today)
    audits_patient = _count_audits_today_patient(today) if patient_ok or ping() else None
    if audits_patient is not None:
        audits_today: Optional[int] = audits_local + audits_patient
    else:
        audits_today = audits_local

    body: dict[str, Any] = {
        "appointmentsToday": appointments_today,
        "waitingConsults": waiting_consults,
        "deliveriesActive": deliveries_active,
        "refillsPending": refills_pending,
        "followupsUnread": followups_unread,
        "chronicAbnormal": chronic_abnormal,
        "auditsToday": audits_today,
        "updatedAt": _now_iso(),
        "disclaimer": DISCLAIMER,
        "patientApiOk": bool(patient_ok and not errors),
        "breakdown": {
            "auditsLocalToday": audits_local,
            "auditsPatientToday": audits_patient,
        },
    }
    body["guardrailHits"] = _guardrail_hits()
    if errors:
        body["patientApiOk"] = False
        body["patientApiError"] = "; ".join(errors)[:500]
    return body
