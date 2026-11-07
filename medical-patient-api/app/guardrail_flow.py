"""S2 patient-side guardrail orchestration (triage / consult / report interpret).

Routes call these helpers; the shared package is reached only through the
fail-open adapter in app.guardrails.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from app import ai_mock, ai_service, store
from app import guardrails as gr

ROLE = "patient"

# Redflag wording. `advice` stays in the guardrail object; the texts below are
# patient-facing and deliberately different from it (and from each other).
_REDFLAG_LABEL = {
    "redflag_cardiac": "胸痛/胸口压榨感等心源性急症信号",
    "redflag_stroke": "肢体无力、口角歪斜、言语不清等卒中（中风）信号",
    "redflag_bleeding": "大量出血/呕血/黑便等急性出血信号",
    "redflag_suicide": "轻生或自伤风险",
    "redflag_breathing": "严重呼吸困难/窒息信号",
    "redflag_other": "急危症状信号",
}
_COMMON_STEPS = [
    "立即拨打 120 急救电话，说明症状和所在位置",
    "或由家人陪同就近前往医院急诊科，不要等待线上回复或普通门诊预约",
    "不要独自驾车前往医院",
    "携带病历、正在服用的药物（或药盒）和过敏史信息",
]
_EXTRA_STEPS = {
    "redflag_cardiac": ["保持安静、停止活动，坐下或半卧休息"],
    "redflag_stroke": ["记下症状开始的准确时间（关系到溶栓/取栓时间窗）", "暂不进食进水，以防呛咳"],
    "redflag_bleeding": ["平卧休息，避免剧烈活动；外伤出血请持续按压止血"],
    "redflag_breathing": ["保持坐位或半坐位，松开衣领，远离可疑过敏原"],
}
_SUICIDE_STEPS = [
    "立即拨打心理援助热线 12356，或拨打 120 / 110",
    "请家人或朋友马上陪在身边，不要独处",
    "移开身边可能伤害自己的物品（药物、刀具等）",
    "尽快就近前往医院急诊或精神心理科",
]


def redflag_label(gi: dict[str, Any]) -> str:
    return _REDFLAG_LABEL.get(str(gi.get("category") or ""), _REDFLAG_LABEL["redflag_other"])


def redflag_summary(gi: dict[str, Any]) -> str:
    """What was detected (triage `summary`)."""
    if gr.is_suicide(gi.get("category")):
        return "您的描述中提到了轻生或自伤的想法。您的安全最重要，请马上联系专业帮助，不建议继续线上导诊。"
    return f"您描述的症状提示可能存在{redflag_label(gi)}，属于需要立即处理的急危情况，不建议线上导诊或等待预约。"


def redflag_steps(gi: dict[str, Any]) -> list[str]:
    """Concrete actions (triage `nextSteps`)."""
    cat = str(gi.get("category") or "")
    if gr.is_suicide(cat):
        return list(_SUICIDE_STEPS)
    return [_COMMON_STEPS[0], _COMMON_STEPS[1]] + _EXTRA_STEPS.get(cat, []) + _COMMON_STEPS[2:]


def emergency_text(gi: dict[str, Any]) -> str:
    """Short urgent message (consult reply / interpret banner); not a copy of `advice`."""
    if gr.is_suicide(gi.get("category")):
        return "⚠️ 谢谢您愿意说出来。您现在的安全最重要：请立即拨打心理援助热线 12356，或拨打 120，并请身边的人陪着您。"
    return f"⚠️ 您描述的情况可能是{redflag_label(gi)}，请立即拨打 120 或就近前往急诊，不要等待线上回复。"


def refusal_text(gi: dict[str, Any]) -> str:
    return gr.refuse_advice(gi.get("category"), ROLE)


def guard_input(text: str, endpoint: str) -> dict[str, Any]:
    gi = gr.check_input(text, ROLE)
    gr.record_hit(store.append_audit, gi, endpoint=endpoint, role=ROLE)
    return gi


# Minimal structural schemas: invalid structured output → rule mock (source=mock_fallback)
TRIAGE_SCHEMA = {
    "type": "object",
    "required": ["departments", "urgency"],
    "properties": {
        "departments": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["name"]}},
        "urgency": {"enum": ["emergency", "urgent", "routine"]},
    },
}
INTERPRET_SCHEMA = {
    "type": "object",
    "required": ["interpretation", "abnormalities", "advice"],
    "properties": {
        "interpretation": {"type": "string", "minLength": 1},
        "abnormalities": {"type": "array"},
        "advice": {"type": "array"},
    },
}


def guard_output_dict(result: dict[str, Any], fallback: Any = None, schema: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    out, co = gr.apply_output_dict(result, ROLE, schema=schema, fallback=fallback)
    return out, co


def guard_output_text(text: str) -> str:
    co = gr.check_output(text, ROLE)
    out = co.get("output")
    return out if isinstance(out, str) and out.strip() else text


def _with_guardrail(out: dict[str, Any], gi: dict[str, Any], co: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    field = gr.guardrail_field(gi, ROLE)
    if co and co.get("modified"):
        field["outputModified"] = True
        field["flags"] = co.get("flags") or []
    out["guardrail"] = field
    return out


# ---------- triage ----------
_TRIAGE_FIELDS = ("chief", "duration", "bodyPart", "severity", "extra")


def triage(payload: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(str(payload.get(k) or "") for k in _TRIAGE_FIELDS if payload.get(k))
    gi = guard_input(text, "POST /api/triage/recommend")
    masked = dict(payload)
    for k in _TRIAGE_FIELDS:
        if isinstance(masked.get(k), str):
            masked[k] = gr.mask_pii(masked[k])

    def _mock() -> dict[str, Any]:
        m = ai_mock.recommend(
            chief=str(masked.get("chief") or ""),
            duration=str(masked.get("duration") or ""),
            body_part=str(masked.get("bodyPart") or ""),
            severity=masked.get("severity"),
            age=masked.get("age"),
            gender=masked.get("gender"),
            extra=masked.get("extra"),
        )
        return {**m, "disclaimer": ai_service.DISCLAIMER}

    if gi["action"] == gr.REDFLAG:
        out = _mock()  # rules only — NO LLM call
        out.update(
            urgency="emergency",
            suggestOnline=False,
            nextSteps=redflag_steps(gi),
            summary=redflag_summary(gi),
            disclaimer=gr.disclaimer(),
            source="guardrail",
            error=None,
            message="命中急危红旗，已短路（未调用 LLM）",
        )
        return _with_guardrail(out, gi)

    if gi["action"] == gr.REFUSE:
        msg = refusal_text(gi)
        # summary stays neutral; action guidance lives only in guardrail.advice
        return _with_guardrail(
            {
                "departments": [],
                "urgency": "routine",
                "suggestOnline": False,
                "nextSteps": [],
                "summary": "本次请求未继续处理",
                "chiefComplaint": "",
                "accompanying": [],
                "disclaimer": gr.disclaimer(),
                "source": "guardrail",
                "error": None,
                "message": msg,
            },
            gi,
        )

    result = ai_service.recommend(masked)
    out, co = guard_output_dict(result, fallback=_mock, schema=TRIAGE_SCHEMA)
    # allow + non-null caution (not redflag): keep urgency mild — never urgent/emergency
    # API urgency enum is emergency|urgent|routine; "routine" is the normal/mild bucket.
    if gi.get("caution") or gi.get("caution_category"):
        urg = str(out.get("urgency") or "").lower()
        if urg in ("emergency", "urgent"):
            out["urgency"] = "routine"
            out["suggestOnline"] = True if out.get("suggestOnline") is None else out.get("suggestOnline")
    return _with_guardrail(out, gi, co)


# ---------- consult ----------
def guardrail_field(gi: dict[str, Any]) -> dict[str, Any]:
    return gr.guardrail_field(gi, ROLE)


def consult_blocked_reply(gi: dict[str, Any]) -> str:
    return emergency_text(gi) if gi["action"] == gr.REDFLAG else refusal_text(gi)


# ---------- report interpret ----------
def interpret(text: str, report_type: Optional[str], endpoint: str,
              call: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """`call(masked_text)` performs the (LLM-or-mock) interpretation."""
    gi = guard_input(text, endpoint)
    masked = gr.mask_pii(text)

    def _mock() -> dict[str, Any]:
        m = ai_mock.interpret_report(text=masked, report_type=report_type)
        return {**m, "disclaimer": ai_service.REPORT_INTERPRET_DISCLAIMER}

    if gi["action"] == gr.REDFLAG:
        msg = emergency_text(gi)
        out = _mock()  # rules only — NO LLM call
        out["advice"] = [msg] + list(out.get("advice") or [])
        out["interpretation"] = f"{msg}\n\n{out.get('interpretation') or ''}".strip()
        out.update(source="guardrail", error=None, message="命中急危红旗，已短路（未调用 LLM）")
        if not out.get("disclaimer"):
            out["disclaimer"] = gr.disclaimer()
        return _with_guardrail(out, gi)

    if gi["action"] == gr.REFUSE:
        msg = refusal_text(gi)
        return _with_guardrail(
            {
                "interpretation": msg,
                "abnormalities": [],
                "advice": [msg],
                "reportType": report_type or "other",
                "disclaimer": ai_service.REPORT_INTERPRET_DISCLAIMER,
                "source": "guardrail",
                "error": None,
                "message": msg,
            },
            gi,
        )

    result = call(masked)
    out, co = guard_output_dict(result, fallback=_mock, schema=INTERPRET_SCHEMA)
    return _with_guardrail(out, gi, co)


def stats() -> dict[str, Any]:
    return gr.stats_from_audit(list(store._AUDIT))
