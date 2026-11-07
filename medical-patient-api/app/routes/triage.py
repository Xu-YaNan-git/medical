"""Symptom triage routes."""

from __future__ import annotations

from fastapi import APIRouter

from app import guardrail_flow
from app.models import TriageRecommendRequest

router = APIRouter(prefix="/api/triage", tags=["triage"])


@router.post("/recommend")
def recommend(body: TriageRecommendRequest) -> dict:
    return guardrail_flow.triage(body.model_dump())
