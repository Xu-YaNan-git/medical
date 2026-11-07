"""M7 药品配送 Mock（非真实处方与物流）."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import (
    AdvancePharmacyDeliveryRequest,
    CancelPharmacyDeliveryRequest,
    CreatePharmacyAddressRequest,
    CreatePharmacyDeliveryRequest,
    UpdatePharmacyAddressRequest,
)

router = APIRouter(tags=["pharmacy"])
alias_router = APIRouter(tags=["pharmacy-alias"])


def _map_err(exc: ValueError) -> HTTPException:
    code = str(exc)
    mapping = {
        "order_not_found": (404, "not_found", "处方/购药单不存在"),
        "address_not_found": (404, "not_found", "地址不存在"),
        "delivery_not_found": (404, "not_found", "配送单不存在"),
        "delivery_exists": (409, "delivery_exists", "该订单已有进行中的配送"),
        "delivery_cancelled": (409, "delivery_cancelled", "配送已取消"),
        "already_delivered": (409, "already_delivered", "已送达，无法取消"),
        "invalid_status": (422, "validation_error", "无效的目标状态"),
        "missing_required": (422, "validation_error", "姓名、手机号、详细地址必填"),
    }
    status, err, msg = mapping.get(code, (400, "bad_request", code))
    return HTTPException(status_code=status, detail={"error": err, "message": msg})


# ---------- Pharmacy orders (可配送处方单) ----------
@router.get("/api/pharmacy/orders")
@router.get("/api/pharmacy/orders/")
@alias_router.get("/api/rx-orders")
@alias_router.get("/api/rx-orders/")
def list_orders(patientId: Optional[str] = Query(None)) -> dict:
    items = store.list_pharmacy_orders(patient_id=patientId)
    return {"items": items, "disclaimer": store.PHARMACY_DISCLAIMER}


@router.get("/api/pharmacy/orders/{order_id}")
@alias_router.get("/api/rx-orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = store.get_pharmacy_order(order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"处方/购药单不存在：{order_id}"},
        )
    return order


# ---------- Addresses CRUD ----------
@router.get("/api/pharmacy/addresses")
@router.get("/api/pharmacy/addresses/")
def list_addresses(patientId: Optional[str] = Query(None)) -> dict:
    items = store.list_pharmacy_addresses(patient_id=patientId)
    return {"items": items, "disclaimer": store.PHARMACY_DISCLAIMER}


@router.post("/api/pharmacy/addresses")
@router.post("/api/pharmacy/addresses/")
def create_address(body: CreatePharmacyAddressRequest) -> dict:
    try:
        addr = store.create_pharmacy_address(body.model_dump())
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.address.create",
        resource_type="pharmacy_address",
        resource_id=addr["id"],
        detail=f"创建配送地址 city={addr.get('city')} isDefault={addr.get('isDefault')}",
    )
    return addr


@router.get("/api/pharmacy/addresses/{address_id}")
def get_address(address_id: str) -> dict:
    addr = store.get_pharmacy_address(address_id)
    if not addr:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"地址不存在：{address_id}"},
        )
    return addr


@router.put("/api/pharmacy/addresses/{address_id}")
@router.patch("/api/pharmacy/addresses/{address_id}")
def update_address(address_id: str, body: UpdatePharmacyAddressRequest) -> dict:
    try:
        addr = store.update_pharmacy_address(
            address_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.address.update",
        resource_type="pharmacy_address",
        resource_id=address_id,
        detail=f"更新配送地址 isDefault={addr.get('isDefault')}",
    )
    return addr


@router.delete("/api/pharmacy/addresses/{address_id}")
def delete_address(address_id: str) -> dict:
    try:
        store.delete_pharmacy_address(address_id)
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.address.delete",
        resource_type="pharmacy_address",
        resource_id=address_id,
        detail="删除配送地址",
    )
    return {"ok": True, "id": address_id, "disclaimer": store.PHARMACY_DISCLAIMER}


# ---------- Deliveries ----------
@router.post("/api/pharmacy/deliveries")
@router.post("/api/pharmacy/deliveries/")
def create_delivery(body: CreatePharmacyDeliveryRequest) -> dict:
    try:
        d = store.create_pharmacy_delivery(
            order_id=body.orderId,
            address_id=body.addressId,
            patient_id=body.patientId,
        )
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.delivery.create",
        resource_type="pharmacy_delivery",
        resource_id=d["id"],
        detail=f"创建配送 orderId={body.orderId} addressId={body.addressId}",
    )
    return d


@router.get("/api/pharmacy/deliveries")
@router.get("/api/pharmacy/deliveries/")
def list_deliveries(patientId: Optional[str] = Query(None)) -> dict:
    items = store.list_pharmacy_deliveries(patient_id=patientId)
    return {"items": items, "disclaimer": store.PHARMACY_DISCLAIMER}


@router.get("/api/pharmacy/deliveries/{delivery_id}")
def get_delivery(delivery_id: str) -> dict:
    d = store.get_pharmacy_delivery(delivery_id)
    if not d:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"配送单不存在：{delivery_id}"},
        )
    return d


@router.post("/api/pharmacy/deliveries/{delivery_id}/advance")
def advance_delivery(
    delivery_id: str, body: Optional[AdvancePharmacyDeliveryRequest] = None
) -> dict:
    target = None
    if body:
        target = body.status or body.uiStatus
    try:
        d = store.advance_pharmacy_delivery(delivery_id, target=target)
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.delivery.advance",
        resource_type="pharmacy_delivery",
        resource_id=delivery_id,
        detail=f"推进配送状态 → {d.get('status')} / {d.get('uiStatus')}",
    )
    return d


@router.post("/api/pharmacy/deliveries/{delivery_id}/cancel")
@router.patch("/api/pharmacy/deliveries/{delivery_id}")
def cancel_delivery(
    delivery_id: str, body: Optional[CancelPharmacyDeliveryRequest] = None
) -> dict:
    # PATCH with status=cancelled also works via body if we add status field — keep simple cancel
    reason = body.reason if body else None
    # Allow PATCH {"status":"cancelled"} via CancelPharmacyDeliveryRequest only having reason;
    # also accept Advance body misuse? Keep dedicated cancel.
    try:
        d = store.cancel_pharmacy_delivery(delivery_id, reason=reason)
    except ValueError as e:
        raise _map_err(e) from e
    store.append_audit(
        action="pharmacy.delivery.cancel",
        resource_type="pharmacy_delivery",
        resource_id=delivery_id,
        detail="取消配送",
    )
    return d
