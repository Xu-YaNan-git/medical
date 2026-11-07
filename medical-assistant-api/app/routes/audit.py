"""Doctor-side audit list + export (Bearer required, no sensitive plaintext)."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import require_auth
from app.privacy import scrub_audit_entry
from app.store import AUDIT_DISCLAIMER, store

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
def list_audit(
    limit: int = Query(50, ge=1, le=500),
    _user: str = Depends(require_auth),
) -> dict:
    items = store.list_audit(limit=limit)
    return {"items": items, "disclaimer": AUDIT_DISCLAIMER}


@router.get("/export")
def export_audit(
    format: str = Query("json", description="json|csv"),
    limit: int = Query(500, ge=1, le=2000),
    _user: str = Depends(require_auth),
):
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "csv"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"error": "invalid_format", "message": "format 须为 json 或 csv"})
    items = [scrub_audit_entry(x) for x in store.list_audit(limit=limit)]
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
                "Content-Disposition": 'attachment; filename="doctor-audit-export.csv"',
            },
        )

    return JSONResponse(
        {
            "items": items,
            "exportedAt": exported_at,
            "disclaimer": AUDIT_DISCLAIMER,
        }
    )
