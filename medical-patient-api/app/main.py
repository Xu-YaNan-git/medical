"""看病用户端 · 导诊台 FastAPI backend."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import appointments as appointments_routes
from app.routes import catalog as catalog_routes
from app.routes import consult as consult_routes
from app.routes import previsit as previsit_routes
from app.routes import reports as reports_routes
from app.routes import patients as patients_routes
from app.routes import doctor_preconsult as doctor_preconsult_routes
from app.routes import triage as triage_routes
from app.routes import waiting as waiting_routes
from app.routes import messages as messages_routes
from app.routes import navigation as navigation_routes
from app.routes import refills as refills_routes
from app.routes import medications as medications_routes
from app.routes import followups as followups_routes
from app.routes import doctor_followups as doctor_followups_routes
from app.routes import bills as bills_routes
from app.routes import identity as identity_routes
from app.routes import audit as audit_routes
from app.routes import doctor_consult as doctor_consult_routes
from app.routes import consultations as consultations_routes
from app.routes import lab_exams as lab_exams_routes
from app.routes import pharmacy as pharmacy_routes
from app.routes import demo as demo_routes
from app.routes import chronic as chronic_routes
from app.routes import doctor_chronic as doctor_chronic_routes
from app.routes import guardrails as guardrails_routes

app = FastAPI(
    title="看病用户端 · 导诊台 API",
    description="患者端导诊/问诊/预约原型后端（OpenAI 兼容 LLM + Mock 降级，不替代面诊）",
    version="0.10.0",
)

# Optional override for LAN/remote direct-port access; default unchanged.
_DEFAULT_CORS_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX") or _DEFAULT_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        body = detail
    else:
        body = {"error": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": str(exc.errors())},
    )


@app.get("/health")
def health() -> dict:
    from app.llm import is_configured

    from app import guardrails as gr

    return {"status": "ok", "llmConfigured": is_configured(), "guardrails": gr.status()}


app.include_router(triage_routes.router)
app.include_router(consult_routes.router)
app.include_router(previsit_routes.router)
app.include_router(reports_routes.router)
app.include_router(catalog_routes.router)
app.include_router(appointments_routes.router)
app.include_router(patients_routes.router)
app.include_router(doctor_preconsult_routes.router)
app.include_router(waiting_routes.router)
app.include_router(messages_routes.router)
app.include_router(navigation_routes.router)
app.include_router(refills_routes.router)
app.include_router(medications_routes.router)
app.include_router(followups_routes.router)
app.include_router(doctor_followups_routes.router)
app.include_router(bills_routes.router)
app.include_router(identity_routes.router)
app.include_router(audit_routes.router)
app.include_router(doctor_consult_routes.router)
app.include_router(consultations_routes.router)
app.include_router(consultations_routes.doctor_router)
app.include_router(lab_exams_routes.router)
app.include_router(lab_exams_routes.alias_router)
app.include_router(lab_exams_routes.ui_router)
app.include_router(pharmacy_routes.router)
app.include_router(pharmacy_routes.alias_router)
app.include_router(demo_routes.router)
app.include_router(chronic_routes.router)
app.include_router(doctor_chronic_routes.router)
app.include_router(guardrails_routes.router)
