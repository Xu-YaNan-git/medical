"""S2 doctor-side guardrail orchestration (role="doctor").

Doctor-side prescribing/dosage discussion is legitimate; the package decides
based on role. Redflag → warn only: normal AI flow + guardrail object (audited);
refuse → empty/neutral payload + guardrail object, no AI call, nothing persisted.
"""

from __future__ import annotations

from typing import Any, Callable

from app import guardrails as gr
from app.store import store

ROLE = "doctor"

_VISIT_TEXT_FIELDS = ("chief", "hpi", "pmh", "allergy", "pe", "labs", "rawText")
_VISIT_MASK_FIELDS = _VISIT_TEXT_FIELDS + ("name", "note", "phone", "idCard", "idNumber")

# Minimal structural schemas: invalid structured output → rule mock (source=mock_fallback)
SCHEMAS: dict[str, dict[str, Any]] = {
    "differential": {
        "type": "object",
        "required": ["items"],
        "properties": {"items": {"type": "array", "minItems": 1,
                                 "items": {"type": "object", "required": ["id", "name"]}}},
    },
    "orders": {
        "type": "object",
        "required": ["exams", "drugs"],
        "properties": {"exams": {"type": "array"}, "drugs": {"type": "array"}},
    },
    "note": {
        "type": "object",
        "required": ["sections", "fullText"],
        "properties": {"sections": {"type": "object"}, "fullText": {"type": "string", "minLength": 1}},
    },
    "polish": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
    "parse": {"type": "object", "required": ["chief", "hpi"]},
}

REFUSE_TEXT = "该请求被安全策略拒绝（疑似提示注入/越权指令），未调用 AI。请仅输入临床相关内容。"


def visit_text(visit: dict[str, Any], extra: str = "") -> str:
    parts = [str(visit.get(k) or "") for k in _VISIT_TEXT_FIELDS if visit.get(k)]
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def masked_visit(visit: dict[str, Any]) -> dict[str, Any]:
    out = dict(visit)
    for k in _VISIT_MASK_FIELDS:
        if isinstance(out.get(k), str):
            out[k] = gr.mask_pii(out[k])
    return out


def guard_input(text: str, endpoint: str, actor: str | None = None) -> dict[str, Any]:
    gi = gr.check_input(text, ROLE)
    gr.record_hit(store.append_audit, gi, endpoint=endpoint, role=ROLE, actor=actor or ROLE)
    return gi


def run(
    *,
    text: str,
    endpoint: str,
    actor: str | None,
    call_ai: Callable[[], dict[str, Any]],
    call_mock: Callable[[], dict[str, Any]],
    refused: Callable[[str], dict[str, Any]],
    schema: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (result, gi). result always carries `guardrail` (+ aiNotice when checked)."""
    gi = guard_input(text, endpoint, actor)
    if gi["action"] == gr.REFUSE:
        out = refused(REFUSE_TEXT)
        out.update(source="guardrail", error=None, message=REFUSE_TEXT)
        out["guardrail"] = gr.guardrail_field(gi, ROLE)
        out.setdefault("aiNotice", gr.DOCTOR_AI_NOTICE)
        return out, gi
    # Doctor side: redflag = warn only (需求整理 S2 follow-up). Normal AI flow on the
    # masked input; the redflag is attached as `guardrail` and audited/counted above.
    res = call_ai()
    out, co = gr.apply_output_dict(res, ROLE, schema=schema, fallback=call_mock)
    out.setdefault("aiNotice", gr.DOCTOR_AI_NOTICE)
    field = gr.guardrail_field(gi, ROLE)
    if co.get("modified"):
        field["outputModified"] = True
        field["flags"] = co.get("flags") or []
    out["guardrail"] = field
    return out, gi


def stats() -> dict[str, Any]:
    return gr.stats_from_audit(list(store._audit))
