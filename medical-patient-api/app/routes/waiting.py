"""M2 候诊/报到 status & check-in."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.models import CheckInRequest

router = APIRouter(tags=["waiting"])


def _status_payload(items: list[dict]) -> dict:
    return {
        "items": items,
        "disclaimer": "候诊信息为演示 Mock，以医院现场叫号为准。",
    }


@router.get("/api/waiting/status")
@router.get("/api/queue")
def get_waiting_status(
    appointmentId: Optional[str] = Query(None, description="预约 ID；省略则返回当前候诊列表"),
) -> dict:
    if appointmentId:
        try:
            item = store.get_or_create_queue_for_appointment(appointmentId)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"预约不存在：{appointmentId}"},
            )
        except ValueError as e:
            msg = str(e)
            if msg.startswith("appointment_not_confirmed"):
                st = msg.split(":", 1)[-1]
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "appointment_not_confirmed",
                        "message": f"仅 confirmed 预约可生成候诊队列，当前状态：{st}",
                    },
                )
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": msg},
            )
        return _status_payload([item])

    items = store.list_queues(active_only=False)
    return _status_payload(items)


@router.post("/api/waiting/status")
@router.post("/api/queue")
def check_in(body: CheckInRequest) -> dict:
    appointment_id = (body.appointmentId or "").strip()
    if not appointment_id:
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "appointmentId 不能为空"},
        )
    if not store.get_appointment(appointment_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{appointment_id}"},
        )
    try:
        item = store.check_in_queue(appointment_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"预约不存在：{appointment_id}"},
        )
    except ValueError as e:
        msg = str(e)
        if msg == "already_done":
            raise HTTPException(
                status_code=409,
                detail={"error": "already_done", "message": "该候诊已完成，无法再次报到"},
            )
        if msg.startswith("appointment_not_confirmed"):
            st = msg.split(":", 1)[-1]
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "appointment_not_confirmed",
                    "message": f"仅 confirmed 预约可报到，当前状态：{st}",
                },
            )
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": msg},
        )
    return {
        **item,
        "disclaimer": "候诊信息为演示 Mock，以医院现场叫号为准。",
    }
