"""Visit CRUD + AI endpoints (LLM with mock fallback)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app import ai_mock
from app import ai_service
from app import guardrail_flow as gf
from app.auth import require_auth
from app.patient_client import PatientApiError, get_preconsult_report
from app.models import (
    ApplyDifferentialToNoteRequest,
    ApplyTemplateRequest,
    CreateVisitRequest,
    DifferentialDecisionRequest,
    DifferentialResponse,
    NoteGenerateResponse,
    NotePolishRequest,
    NotePolishResponse,
    OrdersSuggestResponse,
    OrdersWriteRequest,
    ParseTextRequest,
    ParseTextResponse,
    SuggestItem,
    UpdateVisitRequest,
    VisitDetail,
    VisitSummary,
)
from app.store import store
from app.templates_data import TEMPLATE_FIELD_KEYS, get_template

router = APIRouter(prefix="/api/visits", tags=["visits"])


def _err(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})


def _get_visit(visit_id: str) -> dict[str, Any]:
    visit = store.get(visit_id)
    if not visit:
        raise _err(404, "not_found", f"就诊记录不存在：{visit_id}")
    return visit


@router.get("", response_model=list[VisitSummary])
def list_visits(
    hasPreconsult: Optional[int] = Query(
        None, description="1=仅返回已关联预问诊报告的就诊"
    ),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    visits = store.list_visits()
    if hasPreconsult == 1:
        visits = [v for v in visits if v.get("preconsultReportId")]
    return [store.summary(v) for v in visits]


@router.post("", response_model=VisitDetail, status_code=status.HTTP_201_CREATED)
def create_visit(
    body: CreateVisitRequest,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    visit = store.create(
        name=body.name,
        gender=body.gender,
        age=body.age,
        chief=body.chief,
        status=body.status or "waiting",
        preconsultReportId=body.preconsultReportId,
    )
    return store.detail(visit)


@router.get("/{visit_id}", response_model=VisitDetail)
def get_visit(visit_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    return store.detail(_get_visit(visit_id))


@router.get("/{visit_id}/preconsult")
def get_visit_preconsult(visit_id: str, _user: str = Depends(require_auth)) -> dict[str, Any]:
    visit = _get_visit(visit_id)
    report_id = visit.get("preconsultReportId")
    if not report_id:
        # Visit exists; missing link is not "就诊记录不存在". Return 200 so list ids
        # never 404 on this sub-resource just because no report is attached yet.
        return {
            "visitId": visit_id,
            "preconsultReportId": None,
            "report": None,
            "message": "该就诊未关联预问诊报告",
        }
    try:
        report = get_preconsult_report(str(report_id))
    except PatientApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.error, "message": exc.message},
        ) from exc
    return {
        "visitId": visit_id,
        "preconsultReportId": report_id,
        "report": report,
    }


@router.put("/{visit_id}", response_model=VisitDetail)
def update_visit(
    visit_id: str,
    body: UpdateVisitRequest,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    _get_visit(visit_id)
    fields = body.model_dump(exclude_unset=True)
    updated = store.update(visit_id, fields)
    assert updated is not None
    return store.detail(updated)


@router.post("/{visit_id}/parse-text", response_model=ParseTextResponse)
def parse_text(
    visit_id: str,
    body: ParseTextRequest,
    _user: str = Depends(require_auth),
) -> ParseTextResponse:
    visit = _get_visit(visit_id)
    raw = (body.rawText or "").strip()
    if not raw:
        raise _err(400, "bad_request", "rawText 不能为空")
    masked_raw = gf.gr.mask_pii(raw)
    result, gi = gf.run(
        text=raw,
        endpoint="POST /api/visits/{id}/parse-text",
        schema=gf.SCHEMAS["parse"],
        actor=_user,
        call_ai=lambda: ai_service.parse_text(masked_raw),
        call_mock=lambda: {**ai_mock.parse_unstructured(masked_raw), "disclaimer": ai_service.DISCLAIMER, "source": "mock"},
        refused=lambda msg: {k: "" for k in ("chief", "hpi", "pmh", "allergy", "pe", "labs")} | {"disclaimer": ai_service.DISCLAIMER},
    )
    if gi["action"] == gf.gr.REFUSE:
        return ParseTextResponse(**result)
    fields = {
        "chief": result["chief"],
        "hpi": result["hpi"],
        "pmh": result["pmh"],
        "allergy": result["allergy"],
        "pe": result["pe"],
        "labs": result["labs"],
    }
    store.update(
        visit_id,
        {
            **fields,
            "rawText": raw,
            "chief": fields["chief"] or visit.get("chief", ""),
        },
    )
    return ParseTextResponse(
        **fields,
        disclaimer=result["disclaimer"],
        source=result.get("source"),
        error=result.get("error"),
        message=result.get("message"),
        aiNotice=result.get("aiNotice"),
        guardrail=result.get("guardrail"),
    )


@router.post("/{visit_id}/differential", response_model=DifferentialResponse)
def differential(
    visit_id: str,
    _user: str = Depends(require_auth),
) -> DifferentialResponse:
    visit = _get_visit(visit_id)
    if not (visit.get("chief") or "").strip() and not (visit.get("rawText") or "").strip():
        raise _err(400, "bad_request", "请先填写主诉或粘贴病情")
    mv = gf.masked_visit(visit)
    result, gi = gf.run(
        text=gf.visit_text(visit),
        endpoint="POST /api/visits/{id}/differential",
        schema=gf.SCHEMAS["differential"],
        actor=_user,
        call_ai=lambda: ai_service.generate_differential(mv),
        call_mock=lambda: {"items": ai_mock.generate_differential(mv), "disclaimer": ai_service.DISCLAIMER, "source": "mock"},
        refused=lambda msg: {"items": [], "disclaimer": ai_service.DISCLAIMER},
    )
    items = result["items"]
    if gi["action"] == gf.gr.REFUSE:
        return DifferentialResponse(**result)
    store.update(visit_id, {"differential": items, "status": "in_progress" if visit["status"] == "waiting" else visit["status"]})
    return DifferentialResponse(
        items=items,
        disclaimer=result["disclaimer"],
        source=result.get("source"),
        error=result.get("error"),
        message=result.get("message"),
        aiNotice=result.get("aiNotice"),
        guardrail=result.get("guardrail"),
    )


@router.post("/{visit_id}/differential/decision", response_model=DifferentialResponse)
def differential_decision(
    visit_id: str,
    body: DifferentialDecisionRequest,
    _user: str = Depends(require_auth),
) -> DifferentialResponse:
    visit = _get_visit(visit_id)
    items = list(visit.get("differential") or [])
    if not items:
        raise _err(400, "bad_request", "请先生成鉴别诊断")
    found = False
    for item in items:
        if item.get("id") == body.itemId:
            item["decision"] = body.decision
            found = True
            break
    if not found:
        raise _err(404, "not_found", f"鉴别项不存在：{body.itemId}")
    store.update(visit_id, {"differential": items})
    return DifferentialResponse(items=items, disclaimer=ai_service.DISCLAIMER)


@router.post("/{visit_id}/orders/suggest", response_model=OrdersSuggestResponse)
def orders_suggest(
    visit_id: str,
    _user: str = Depends(require_auth),
) -> OrdersSuggestResponse:
    visit = _get_visit(visit_id)
    mv = gf.masked_visit(visit)
    result, _gi = gf.run(
        text=gf.visit_text(visit),
        endpoint="POST /api/visits/{id}/orders/suggest",
        schema=gf.SCHEMAS["orders"],
        actor=_user,
        call_ai=lambda: ai_service.suggest_orders(mv),
        call_mock=lambda: {**ai_mock.suggest_orders(mv), "disclaimer": ai_service.DISCLAIMER, "source": "mock"},
        refused=lambda msg: {"exams": [], "drugs": [], "disclaimer": ai_service.DISCLAIMER},
    )
    exams = [SuggestItem(**e) for e in result["exams"]]
    drugs = [SuggestItem(**d) for d in result["drugs"]]
    return OrdersSuggestResponse(
        exams=exams,
        drugs=drugs,
        disclaimer=result["disclaimer"],
        source=result.get("source"),
        error=result.get("error"),
        message=result.get("message"),
        aiNotice=result.get("aiNotice"),
        guardrail=result.get("guardrail"),
    )


def _resolve_order_type(otype: str | None, source: str | None) -> str:
    if otype and str(otype).strip():
        t = str(otype).strip()
        # allow English shortcuts
        low = t.lower()
        if low in ("exam", "labs", "lab", "检查"):
            return "检查"
        if low in ("drug", "med", "medicine", "药品"):
            return "药品"
        if low in ("other", "其他"):
            return "其他"
        return t
    src = (source or "").strip().lower()
    if src in ("exam", "labs", "lab", "检查"):
        return "检查"
    if src in ("drug", "med", "medicine", "药品"):
        return "药品"
    return "其他"


def _is_blank(val: Any) -> bool:
    if val is None:
        return True
    return str(val).strip() == ""


def _split_note_parts(text: str) -> list[str]:
    raw = text or ""
    parts: list[str] = []
    buf = ""
    seps = {"；", ";", chr(10), chr(13)}
    for ch in raw:
        if ch in seps:
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _merge_note_names(existing: str, names: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in _split_note_parts(existing) + [n.strip() for n in names if (n or "").strip()]:
        if not part:
            continue
        if part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return "；".join(ordered)


@router.post("/{visit_id}/apply-template", response_model=VisitDetail)
def apply_template(
    visit_id: str,
    body: ApplyTemplateRequest,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    visit = _get_visit(visit_id)
    tpl = get_template(body.templateId)
    if not tpl:
        raise _err(404, "not_found", f"模板不存在：{body.templateId}")
    fields = tpl.get("fields") or {}
    patch: dict[str, Any] = {}
    overwrite = bool(body.overwrite)
    for key in TEMPLATE_FIELD_KEYS:
        if key not in fields:
            continue
        tpl_val = fields.get(key) or ""
        if overwrite or _is_blank(visit.get(key)):
            patch[key] = tpl_val
    specialty = tpl.get("specialty") or ""
    if specialty:
        patch["specialty"] = specialty
    if patch:
        store.update(visit_id, patch)
    return store.detail(_get_visit(visit_id))


@router.post("/{visit_id}/differential/apply-to-note", response_model=VisitDetail)
def differential_apply_to_note(
    visit_id: str,
    body: ApplyDifferentialToNoteRequest,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    visit = _get_visit(visit_id)
    names = [n.strip() for n in (body.names or []) if (n or "").strip()]
    if not names:
        raise _err(400, "bad_request", "names 不能为空")
    target = body.target
    if target not in ("diagnosis", "assessment"):
        raise _err(400, "bad_request", "target 须为 diagnosis 或 assessment")
    merged = _merge_note_names(str(visit.get(target) or ""), names)
    store.update(visit_id, {target: merged})
    return store.detail(_get_visit(visit_id))


@router.post("/{visit_id}/orders", response_model=VisitDetail)
def write_orders(
    visit_id: str,
    body: OrdersWriteRequest,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    visit = _get_visit(visit_id)
    orders = list(visit.get("orders") or [])

    def _add(
        otype: str | None,
        text: str,
        conflict: bool | None = None,
        warn: str | None = None,
        source: str | None = None,
    ) -> None:
        text = (text or "").strip()
        if not text:
            return
        resolved = _resolve_order_type(otype, source)
        # dedupe by type+text (ignore source)
        if any(o.get("type") == resolved and o.get("text") == text for o in orders):
            return
        entry: dict[str, Any] = {"type": resolved, "text": text}
        if source:
            entry["source"] = source
        if conflict is not None:
            entry["conflict"] = conflict
        if warn is not None:
            entry["warn"] = warn
        # Auto-check allergy for drugs
        if resolved == "药品":
            w = ai_mock.has_allergy_conflict(visit.get("allergy") or "", text)
            if w:
                entry["conflict"] = True
                entry["warn"] = w
        orders.append(entry)

    if body.items:
        for it in body.items:
            _add(it.type, it.text, it.conflict, it.warn, it.source)
    elif body.type and body.text:
        _add(body.type, body.text, source=body.source)
    elif body.text:
        _add(None, body.text, source=body.source)
    else:
        raise _err(400, "bad_request", "请提供 items 或 type+text")

    store.update(visit_id, {"orders": orders})
    return store.detail(_get_visit(visit_id))


@router.post("/{visit_id}/note/generate", response_model=NoteGenerateResponse)
def note_generate(
    visit_id: str,
    _user: str = Depends(require_auth),
) -> NoteGenerateResponse:
    visit = _get_visit(visit_id)
    mv = gf.masked_visit(visit)
    result, gi = gf.run(
        text=gf.visit_text(visit),
        endpoint="POST /api/visits/{id}/note/generate",
        schema=gf.SCHEMAS["note"],
        actor=_user,
        call_ai=lambda: ai_service.generate_note(mv),
        call_mock=lambda: {
            "sections": ai_mock.note_sections(mv),
            "fullText": ai_mock.build_note(mv, style="structured"),
            "disclaimer": ai_service.DISCLAIMER,
            "source": "mock",
        },
        refused=lambda msg: {"sections": {}, "fullText": msg, "disclaimer": ai_service.DISCLAIMER},
    )
    full = result["fullText"]
    sections = result["sections"]
    if gi["action"] != gf.gr.REFUSE:
        store.update(visit_id, {"note": full})
    return NoteGenerateResponse(
        sections=sections,
        fullText=full,
        disclaimer=result["disclaimer"],
        source=result.get("source"),
        error=result.get("error"),
        message=result.get("message"),
        aiNotice=result.get("aiNotice"),
        guardrail=result.get("guardrail"),
    )


@router.post("/{visit_id}/note/polish", response_model=NotePolishResponse)
def note_polish(
    visit_id: str,
    body: NotePolishRequest,
    _user: str = Depends(require_auth),
) -> NotePolishResponse:
    visit = _get_visit(visit_id)
    content = body.content or visit.get("note") or ""
    mv = gf.masked_visit(visit)
    masked_content = gf.gr.mask_pii(content)
    result, gi = gf.run(
        text=content,
        endpoint="POST /api/visits/{id}/note/polish",
        schema=gf.SCHEMAS["polish"],
        actor=_user,
        call_ai=lambda: ai_service.polish_note(masked_content, body.style, visit=mv),
        call_mock=lambda: {
            "text": ai_mock.polish_note(masked_content, body.style, visit=mv),
            "disclaimer": ai_service.DISCLAIMER,
            "source": "mock",
        },
        refused=lambda msg: {"text": content, "disclaimer": ai_service.DISCLAIMER},
    )
    polished = result["text"]
    if gi["action"] != gf.gr.REFUSE:
        store.update(visit_id, {"note": polished})
    return NotePolishResponse(
        text=polished,
        disclaimer=result["disclaimer"],
        source=result.get("source"),
        error=result.get("error"),
        message=result.get("message"),
        aiNotice=result.get("aiNotice"),
        guardrail=result.get("guardrail"),
    )


@router.get("/{visit_id}/export.md")
def export_md(visit_id: str, _user: str = Depends(require_auth)) -> Response:
    visit = _get_visit(visit_id)
    md = ai_mock.to_markdown(visit)
    filename = f"visit-{visit_id}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
