"""M4 简单操作审计 + 合规导出（演示用，无敏感明文）."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app import store
from app.privacy import scrub_audit_entry

router = APIRouter(prefix="/api/audit", tags=["audit"])

_TZ = ZoneInfo("Asia/Shanghai")
_CSV_HEADERS = [
    "id",
    "action",
    "resourceType",
    "resourceId",
    "actor",
    "detail",
    "createdAt",
]


@router.get("")
@router.get("/")
def list_audit(limit: int = Query(50, ge=1, le=500)) -> dict:
    items = store.list_audit(limit=limit)
    return {"items": items, "disclaimer": store.AUDIT_DISCLAIMER}


@router.get("/export")
def export_audit(
    format: str = Query("json", description="json|csv"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Export audit log as JSON or CSV. Detail fields are scrubbed (no full phone/id)."""
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "csv"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"error": "invalid_format", "message": "format 须为 json 或 csv"})
    raw_items = store.export_audit_items(limit=limit)
    items = [scrub_audit_entry(x) for x in raw_items]
    exported_at = datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S")

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in items:
            writer.writerow(
                {
                    "id": row.get("id", ""),
                    "action": row.get("action", ""),
                    "resourceType": row.get("resourceType", ""),
                    "resourceId": row.get("resourceId", ""),
                    "actor": row.get("actor", ""),
                    "detail": row.get("detail", ""),
                    "createdAt": row.get("createdAt", ""),
                }
            )
        data = buf.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            iter([data]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="audit-export.csv"',
            },
        )

    return JSONResponse(
        {
            "items": items,
            "exportedAt": exported_at,
            "disclaimer": store.AUDIT_DISCLAIMER,
        }
    )
