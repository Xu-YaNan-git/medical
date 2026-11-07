"""AI 医疗智能助手 · 医生端 FastAPI backend."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import auth as auth_routes
from app.routes import visits as visits_routes
from app.routes import preconsult as preconsult_routes
from app.routes import workbench as workbench_routes
from app.routes import followups as followups_routes
from app.routes import audit as audit_routes
from app.routes import demo as demo_routes
from app.routes import chronic as chronic_routes
from app.routes import templates as templates_routes
from app.routes import ops as ops_routes

app = FastAPI(
    title="AI 医疗智能助手 API",
    description="医生端原型后端（OpenAI 兼容 LLM + Mock 降级，不替代执业医师）",
    version="0.1.0",
)

# Allow local prototype origins (any port on localhost / 127.0.0.1)
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
    from app import guardrails as gr
    from app.llm import is_configured

    return {"status": "ok", "llmConfigured": is_configured(), "guardrails": gr.status()}


app.include_router(auth_routes.router)
app.include_router(visits_routes.router)
app.include_router(preconsult_routes.router)
app.include_router(workbench_routes.router)
app.include_router(followups_routes.router)
app.include_router(audit_routes.router)
app.include_router(demo_routes.router)
app.include_router(chronic_routes.router)
app.include_router(templates_routes.router)
app.include_router(ops_routes.router)
