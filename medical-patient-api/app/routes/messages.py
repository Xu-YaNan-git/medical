"""M2 消息中心 + 业务事件推送筛选."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import store

router = APIRouter(prefix="/api/messages", tags=["messages"])

MSG_DISCLAIMER = "消息为演示 Mock，不代表真实医院推送。"


@router.get("")
@router.get("/")
def list_messages(
    type: Optional[str] = Query(None, description="消息类型筛选"),
    unreadOnly: Optional[bool] = Query(
        None, description="仅未读；兼容 unread_only"
    ),
    unread_only: Optional[bool] = Query(None, include_in_schema=False),
) -> dict:
    only_unread = bool(unreadOnly if unreadOnly is not None else unread_only)
    items = store.list_messages(type=type, unread_only=only_unread)
    # unreadCount is global (or same type filter) for UI badge consistency
    unread = store.unread_message_count(type=type)
    return {
        "items": items,
        "unreadCount": unread,
        "disclaimer": MSG_DISCLAIMER,
    }


@router.get("/unread-count")
def unread_count(
    type: Optional[str] = Query(None, description="可选按类型统计未读"),
) -> dict:
    return {
        "unreadCount": store.unread_message_count(type=type),
        "disclaimer": MSG_DISCLAIMER,
    }


@router.patch("/{message_id}/read")
def mark_read(message_id: str) -> dict:
    msg = store.mark_message_read(message_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"消息不存在：{message_id}"},
        )
    return msg


@router.get("/{message_id}")
def get_message(message_id: str) -> dict:
    msg = store.get_message(message_id)
    if not msg:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"消息不存在：{message_id}"},
        )
    return msg
