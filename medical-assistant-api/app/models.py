"""Pydantic request/response models. Field names use camelCase to match the frontend."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ---------- Auth ----------
class LoginRequest(CamelModel):
    username: str
    password: str


class LoginResponse(CamelModel):
    token: str
    displayName: str


# ---------- Chart / Visit ----------
class ChartFields(CamelModel):
    chief: str = ""
    hpi: str = ""
    pmh: str = ""
    allergy: str = ""
    pe: str = ""
    labs: str = ""
    rawText: str = ""


class DifferentialItem(CamelModel):
    id: str
    name: str
    rationale: str
    rank: int
    prob: str = ""
    decision: Optional[Literal["accept", "reject", "pending"]] = "pending"


class OrderItem(CamelModel):
    type: str  # 检查 | 药品 | 其他
    text: str
    conflict: Optional[bool] = None
    warn: Optional[str] = None
    source: Optional[str] = None  # e.g. ai_suggest


class VisitSummary(CamelModel):
    id: str
    name: str
    gender: str
    age: int
    chief: str
    time: str
    status: str  # waiting | in_progress | done | draft


class VisitDetail(VisitSummary):
    chief: str = ""
    hpi: str = ""
    pmh: str = ""
    allergy: str = ""
    pe: str = ""
    labs: str = ""
    rawText: str = ""
    diagnosis: str = ""
    assessment: str = ""
    specialty: str = ""
    differential: list[DifferentialItem] = Field(default_factory=list)
    orders: list[OrderItem] = Field(default_factory=list)
    note: str = ""
    preconsultReportId: Optional[str] = None


class CreateVisitRequest(CamelModel):
    name: str = "新患者"
    gender: str = "男"
    age: int = 40
    chief: str = "（待填写）"
    status: str = "waiting"
    preconsultReportId: Optional[str] = None


class UpdateVisitRequest(CamelModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    chief: Optional[str] = None
    status: Optional[str] = None
    hpi: Optional[str] = None
    pmh: Optional[str] = None
    allergy: Optional[str] = None
    pe: Optional[str] = None
    labs: Optional[str] = None
    rawText: Optional[str] = None
    diagnosis: Optional[str] = None
    assessment: Optional[str] = None
    specialty: Optional[str] = None
    preconsultReportId: Optional[str] = None


# ---------- AI endpoints ----------
class ParseTextRequest(CamelModel):
    rawText: str


class ParseTextResponse(CamelModel):
    chief: str = ""
    hpi: str = ""
    pmh: str = ""
    allergy: str = ""
    pe: str = ""
    labs: str = ""
    disclaimer: str
    # llm | mock | mock_fallback (guardrail schema fallback) | guardrail (short-circuit)
    source: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    aiNotice: Optional[str] = None
    guardrail: Optional[dict[str, Any]] = None


class DifferentialResponse(CamelModel):
    items: list[DifferentialItem]
    disclaimer: str
    # llm | mock | mock_fallback (guardrail schema fallback) | guardrail (short-circuit)
    source: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    aiNotice: Optional[str] = None
    guardrail: Optional[dict[str, Any]] = None


class DifferentialDecisionRequest(CamelModel):
    itemId: str
    decision: Literal["accept", "reject"]


class SuggestItem(CamelModel):
    type: str
    text: str
    conflict: bool = False
    warn: Optional[str] = None


class OrdersSuggestResponse(CamelModel):
    exams: list[SuggestItem]
    drugs: list[SuggestItem]
    disclaimer: str
    # llm | mock | mock_fallback (guardrail schema fallback) | guardrail (short-circuit)
    source: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    aiNotice: Optional[str] = None
    guardrail: Optional[dict[str, Any]] = None


class OrderWriteItem(CamelModel):
    """Flexible order draft item for batch write (AI suggest → orders)."""

    text: str
    type: Optional[str] = None
    source: Optional[str] = None  # ai_suggest | exam | drug | ...
    conflict: Optional[bool] = None
    warn: Optional[str] = None

class OrdersWriteRequest(CamelModel):
    items: Optional[list[OrderWriteItem]] = None
    type: Optional[str] = None
    text: Optional[str] = None
    source: Optional[str] = None


class NoteGenerateResponse(CamelModel):
    sections: dict[str, Any]
    fullText: str
    disclaimer: str
    # llm | mock | mock_fallback (guardrail schema fallback) | guardrail (short-circuit)
    source: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    aiNotice: Optional[str] = None
    guardrail: Optional[dict[str, Any]] = None


class NotePolishRequest(CamelModel):
    style: Literal["concise", "formal"]
    content: str = ""


class NotePolishResponse(CamelModel):
    text: str
    disclaimer: str
    # llm | mock | mock_fallback (guardrail schema fallback) | guardrail (short-circuit)
    source: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    aiNotice: Optional[str] = None
    guardrail: Optional[dict[str, Any]] = None


class ExportMdResponse(CamelModel):
    content: str
    filename: str = "visit.md"


class ErrorResponse(CamelModel):
    error: str
    message: str


# ---------- M11 Templates / differential → note ----------
class TemplateFields(CamelModel):
    chief: str = ""
    hpi: str = ""
    pmh: str = ""
    allergy: str = ""
    pe: str = ""
    labs: str = ""
    diagnosis: str = ""
    assessment: str = ""


class SpecialtyTemplate(CamelModel):
    id: str
    specialty: str
    name: str
    fields: TemplateFields


class ApplyTemplateRequest(CamelModel):
    templateId: str
    overwrite: bool = False


class ApplyDifferentialToNoteRequest(CamelModel):
    names: list[str]
    target: Literal["diagnosis", "assessment"]


