"""S2: guardrail hit statistics (aggregated from scrubbed audit rows)."""

from __future__ import annotations

from fastapi import APIRouter

from app import guardrail_flow
from app import guardrails as gr

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])


@router.get("/stats")
def guardrail_stats() -> dict:
    return {**guardrail_flow.stats(), "status": gr.status(), "side": "patient"}
