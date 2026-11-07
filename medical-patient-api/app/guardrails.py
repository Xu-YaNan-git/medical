"""Thin fail-open adapter around the shared ``guardrails`` package (S2).

Fail-open applies only when ``check_input`` raises/returns unusable or the
package cannot be imported — then input is treated as allow. Audit write
failures log a warning and keep the guardrail decision; they never skip
``check_input``. Output-check failures keep the prior output without
affecting input checks.

Contract (frozen):
    from guardrails import check_input, check_output, mask_pii, DISCLAIMER
    check_input(text, role)  -> {action, reason, category, advice, masked_text,
                                 caution, caution_category}   # 0.2.0: last two always present, None unless patient+allow
    check_output(output, role, schema=None, fallback=None)
                             -> {output, source, modified, flags, needs_doctor_confirm}

Behaviour of this adapter:
- GUARDRAILS_ENABLED=1 (default on). 0/false/no/off disables → allow / passthrough.
- If the package cannot be imported, or a call raises, we FAIL OPEN
  (allow / passthrough) and log ONE warning per failure kind (no request text,
  no secrets).
- Results are normalised so routes can rely on the keys always being present.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, Callable, Optional

logger = logging.getLogger("app.guardrails")

ALLOW = "allow"
REDFLAG = "redflag"
REFUSE = "refuse"

REDFLAG_FALLBACK_ADVICE = "立即急诊/拨打120"
DOCTOR_AI_NOTICE = "AI 建议，需医生确认"
DEFAULT_DISCLAIMER = "AI 辅助信息，仅供参考，不能替代医生面诊、诊断或处方。"

_CANDIDATE_PATHS = (
    os.environ.get("GUARDRAILS_PATH") or "",
    "/opt/medical-guardrails",
    "/workspace/medical-guardrails",
)

_state: dict[str, Any] = {"loaded": None, "mod": None, "warned": set()}

# Category enumerations (package >= 0.2.0 exports them; these are the fallbacks).
_FALLBACK_REDFLAG_CATEGORIES = (
    "redflag_cardiac", "redflag_stroke", "redflag_bleeding",
    "redflag_suicide", "redflag_breathing", "redflag_other",
)
_FALLBACK_REFUSE_CATEGORIES = ("injection", "prompt_leak", "role_override", "prescription_request", "off_topic")
_FALLBACK_CAUTION_CATEGORIES = (
    "caution_mood", "caution_pregnancy", "caution_pediatric",
    "caution_hypoglycemia", "caution_cardiac", "caution_other",
)


def _categories(name: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    mod = _module()
    try:
        v = getattr(mod, name, None) if mod is not None else None
        if v:
            return tuple(str(x) for x in v)
    except Exception:
        pass
    return fallback


def redflag_categories() -> tuple[str, ...]:
    return _categories("REDFLAG_CATEGORIES", _FALLBACK_REDFLAG_CATEGORIES)


def refuse_categories() -> tuple[str, ...]:
    return _categories("REFUSE_CATEGORIES", _FALLBACK_REFUSE_CATEGORIES)


def caution_categories() -> tuple[str, ...]:
    return _categories("CAUTION_CATEGORIES", _FALLBACK_CAUTION_CATEGORIES)


def is_suicide(category: Any) -> bool:
    return "suicide" in str(category or "")


def _warn_once(kind: str, exc: BaseException | None = None) -> None:
    """Log adapter degradation. Only true input fail-open says "pass through unguarded".

    - check_input_* / import_* → requests may pass as allow (unguarded input).
    - audit_error → decision already made; audit write failed; input was NOT skipped.
    - check_output_* → keep prior output / skip modify; input checks unaffected.
    """
    if kind in _state["warned"]:
        return
    _state["warned"].add(kind)
    # Exception *type* only: messages could echo user text.
    etype = type(exc).__name__ if exc is not None else "-"
    if kind == "audit_error":
        logger.warning(
            "guardrails audit write failed (%s); continuing with guardrail decision (input was checked)",
            etype,
        )
    elif kind in ("check_output_error", "check_output_bad_result"):
        logger.warning(
            "guardrails output check degraded (%s, %s); keeping prior output (input checks unaffected)",
            kind,
            etype,
        )
    else:
        # import / check_input failures — true fail-open on input
        logger.warning(
            "guardrails fail-open (%s, %s); requests pass through unguarded",
            kind,
            etype,
        )


def enabled() -> bool:
    v = (os.environ.get("GUARDRAILS_ENABLED", "1") or "").strip().lower()
    return v not in ("0", "false", "no", "off")


def _module() -> Any:
    if _state["loaded"] is not None:
        return _state["mod"]
    mod = None
    try:
        import guardrails as mod  # type: ignore[no-redef]
    except Exception:
        mod = None
        for p in _CANDIDATE_PATHS:
            if p and os.path.isdir(p) and p not in sys.path:
                sys.path.append(p)
                try:
                    import guardrails as mod  # type: ignore[no-redef]
                    break
                except Exception:
                    mod = None
        if mod is None:
            _warn_once("import_failed")
    if mod is not None and not all(hasattr(mod, n) for n in ("check_input", "check_output", "mask_pii")):
        _warn_once("bad_interface")
        mod = None
    _state["mod"] = mod
    _state["loaded"] = True
    return mod


def status() -> dict[str, Any]:
    mod = _module()
    return {
        "enabled": enabled(),
        "packageLoaded": mod is not None,
        "version": getattr(mod, "__version__", None) if mod is not None else None,
    }


def disclaimer() -> str:
    mod = _module()
    d = getattr(mod, "DISCLAIMER", None) if mod is not None else None
    return str(d) if d else DEFAULT_DISCLAIMER


# ---------- PII ----------
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")


def _local_mask(text: str) -> str:
    s = _PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", text)
    return re.sub(r"(?<!\d)(\d{14})(\d{3}[\dXx])(?!\d)", lambda m: "*" * 14 + m.group(2), s)


def mask_pii(text: Any) -> str:
    s = "" if text is None else str(text)
    if not s:
        return s
    mod = _module()
    if mod is not None:
        try:
            out = mod.mask_pii(s)
            return s if out is None else str(out)
        except Exception as exc:
            _warn_once("mask_pii_error", exc)
    return _local_mask(s)


# ---------- input ----------
def _allow(text: str) -> dict[str, Any]:
    return {"action": ALLOW, "reason": "", "category": "none", "advice": "", "masked_text": mask_pii(text)}


def check_input(text: Any, role: str = "patient") -> dict[str, Any]:
    s = "" if text is None else str(text)
    if not enabled():
        return {**_allow(s), "masked_text": s}
    mod = _module()
    if mod is None:
        return _allow(s)
    try:
        raw = mod.check_input(s, role)
    except Exception as exc:
        _warn_once("check_input_error", exc)
        return _allow(s)
    if not isinstance(raw, dict):
        _warn_once("check_input_bad_result")
        return _allow(s)
    action = str(raw.get("action") or ALLOW).lower()
    if action not in (ALLOW, REDFLAG, REFUSE):
        action = ALLOW
    masked = raw.get("masked_text")
    out = {
        "action": action,
        "reason": str(raw.get("reason") or ""),
        "category": _norm_category(action, raw.get("category")),
        "advice": str(raw.get("advice") or ""),
        "masked_text": str(masked) if masked is not None else mask_pii(s),
    }
    if action == REDFLAG and not out["advice"].strip():
        out["advice"] = REDFLAG_FALLBACK_ADVICE
    # Optional package fields (boundary band, still allowed): passed through verbatim,
    # only when not None / non-empty (0.2.0 always sends the keys, usually None).
    for key in _PASSTHROUGH_KEYS:
        if _present(raw.get(key)):
            out[key] = raw[key]
    return out


_PASSTHROUGH_KEYS = ("caution", "caution_category")


def _norm_category(action: str, cat: Any) -> str:
    c = str(cat or "").strip()
    if action == ALLOW:
        return c or "none"
    if c:
        return c  # unknown-but-present categories are kept verbatim (never invented)
    return "redflag_other" if action == REDFLAG else "other"


# Patient/doctor-facing refusal advice (friendly; never echoes the matched text).
_REFUSE_ADVICE = {
    "patient": {
        "prescription_request": "抱歉，我不能开具处方、推荐管制类药物或给出具体用药剂量。请到正规医院由医生面诊后开具处方。",
        "injection": "抱歉，该请求超出导诊助手的服务范围，无法处理。请直接描述您的症状，我会帮您推荐就诊科室。",
        "prompt_leak": "抱歉，无法提供系统设定等内部信息。请直接描述您的症状，我会帮您推荐就诊科室。",
        "role_override": "抱歉，我只能作为导诊助手提供就医指引，无法切换角色。请直接描述您的症状。",
        "off_topic": "抱歉，我只能协助就医导诊、问诊与报告解读相关问题。",
        "_default": "抱歉，该请求无法处理。请直接描述您的症状，我会帮您推荐就诊科室。",
    },
    "doctor": {
        "prompt_leak": "该请求涉及系统设定等内部信息，已被安全策略拦截，未调用 AI。请仅输入临床相关内容后重试。",
        "off_topic": "该内容与临床诊疗无关，已被安全策略拦截，未调用 AI。请输入病历或临床问题后重试。",
        "_default": "该内容疑似包含提示注入或越权指令，已被安全策略拦截，未调用 AI。请删除相关内容、仅保留临床信息后重试。",
    },
}


# Generic public `reason` for refuse (the package reason quotes the matched words,
# e.g. 「命中「开处方」」; that detail stays server-side in the scrubbed audit only).
_PUBLIC_REFUSE_REASON = {
    "injection": "疑似提示注入",
    "prompt_leak": "疑似套取系统设定",
    "role_override": "疑似越权/角色篡改指令",
    "prescription_request": "涉及处方或具体用药剂量请求",
    "off_topic": "与医疗服务无关",
}


def public_reason(category: Any) -> str:
    return "安全策略拦截：" + _PUBLIC_REFUSE_REASON.get(str(category or ""), "不符合使用规范的请求")


def refuse_advice(category: Any, role: str = "patient") -> str:
    table = _REFUSE_ADVICE.get(role) or _REFUSE_ADVICE["patient"]
    return table.get(str(category or ""), table["_default"])


def _present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) > 0
    return True


def guardrail_field(res: dict[str, Any], role: str = "patient") -> dict[str, Any]:
    """Public `guardrail` object for responses (never contains user text).

    allow   → {action, category:"none"}
    redflag → {action, category, advice}
    refuse  → {action, category, advice (friendly, role-specific), reason (generic; no hit words)}
    `caution` / `caution_category` pass through verbatim for any action when not None/empty."""
    action = res.get("action") or ALLOW
    if action == REDFLAG:
        field = {"action": REDFLAG, "category": res.get("category") or "redflag_other",
                 "advice": res.get("advice") or REDFLAG_FALLBACK_ADVICE}
    elif action == REFUSE:
        cat = res.get("category") or "other"
        field = {"action": REFUSE, "category": cat,
                 "advice": refuse_advice(cat, role),
                 "reason": public_reason(cat)}
    else:
        field = {"action": ALLOW, "category": "none"}
    for key in _PASSTHROUGH_KEYS:
        if _present(res.get(key)):
            field[key] = res[key]
    return field


# ---------- output ----------
# Lab concentration values ("110 g/L", "35 IU/L", "5.2 mg/dL") are measurements, not
# doses, but the package's dosage pattern matches "<num> g" / "<num> IU".  We shield
# only <num><unit>/<volume> tokens from the patient-side sanitizer and restore them
# afterwards; per-kg / per-dose expressions are left for the package to strip.
_LAB_VALUE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|g|μg|ug|ng|pg|mmol|μmol|umol|nmol|pmol|mol|iu|u|mu|miu|meq|ml|mL)"
    r"\s*/\s*(?:l|dl|ml|μl|ul|hl)(?![a-z])",
    re.I,
)
_PH_OPEN, _PH_CLOSE = "\ue000", "\ue001"


def _ph(n: int) -> str:
    return _PH_OPEN + "".join(chr(0xE100 + int(c)) for c in str(n)) + _PH_CLOSE


def _shield(obj: Any, table: list[str]) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match) -> str:
            table.append(m.group(0))
            return _ph(len(table) - 1)
        return _LAB_VALUE_RE.sub(repl, obj)
    if isinstance(obj, dict):
        return {k: _shield(v, table) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shield(v, table) for v in obj]
    return obj


_PH_RE = re.compile(_PH_OPEN + "([\ue100-\ue109]+)" + _PH_CLOSE)


def _unshield(obj: Any, table: list[str]) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match) -> str:
            idx = int("".join(str(ord(c) - 0xE100) for c in m.group(1)))
            return table[idx] if 0 <= idx < len(table) else ""
        return _PH_RE.sub(repl, obj)
    if isinstance(obj, dict):
        return {k: _unshield(v, table) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unshield(v, table) for v in obj]
    return obj


def check_output(
    output: Any,
    role: str = "patient",
    *,
    schema: Any = None,
    fallback: Any = None,
) -> dict[str, Any]:
    """Returns {output, source, modified, flags, needs_doctor_confirm}; passthrough on failure."""
    passthrough = {"output": output, "source": None, "modified": False, "flags": [], "needs_doctor_confirm": role == "doctor"}
    if not enabled():
        return passthrough
    mod = _module()
    if mod is None:
        return passthrough
    table: list[str] = []
    try:
        shielded, fb = output, fallback
        if role != "doctor":
            shielded = _shield(output, table)
            if callable(fallback):
                fb = lambda: _shield(fallback(), table)  # noqa: E731
            elif fallback is not None:
                fb = _shield(fallback, table)
        raw = mod.check_output(shielded, role, schema=schema, fallback=fb)
        if table and isinstance(raw, dict) and "output" in raw:
            raw["output"] = _unshield(raw["output"], table)
    except Exception as exc:
        _warn_once("check_output_error", exc)
        return passthrough
    if not isinstance(raw, dict) or "output" not in raw:
        _warn_once("check_output_bad_result")
        return passthrough
    src = raw.get("source")
    return {
        "output": raw.get("output"),
        "source": str(src) if src else None,
        "modified": bool(raw.get("modified")),
        "flags": list(raw.get("flags") or []),
        "needs_doctor_confirm": bool(raw.get("needs_doctor_confirm", role == "doctor")),
    }


def apply_output_dict(
    result: dict[str, Any],
    role: str,
    *,
    schema: Any = None,
    fallback: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """check_output on a dict result; keeps original keys when the package drops them.

    Returns (new_result, check_meta). `source` is overridden when the package
    reports a fallback (e.g. "mock_fallback").
    """
    co = check_output(result, role, schema=schema, fallback=fallback)
    out = co["output"]
    if not isinstance(out, dict):
        out = result
    merged = {**result, **out}
    if co["source"]:
        merged["source"] = co["source"]
    return merged, co


# ---------- audit ----------
def record_hit(
    append_audit: Callable[..., Any],
    res: dict[str, Any],
    *,
    endpoint: str,
    role: str,
    actor: Optional[str] = None,
) -> None:
    """Audit every non-allow hit. Detail carries category/endpoint only — never raw text.

    Audit failures are logged and swallowed — they must never skip or undo check_input.
    """
    action = res.get("action")
    if action not in (REDFLAG, REFUSE):
        return
    try:
        append_audit(
            action=f"guardrail.{action}",
            resource_type="guardrail",
            resource_id=mask_pii(endpoint)[:120],
            detail=mask_pii(
                f"category={res.get('category') or 'other'}; role={role}; endpoint={endpoint}"
                + (f"; reason={str(res.get('reason'))[:80]}" if res.get("reason") else "")
            ),
            actor=actor or role,
        )
    except Exception as exc:  # audit must never break the request
        _warn_once("audit_error", exc)


def stats_from_audit(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate guardrail.* audit rows → {total, byCategory, byAction}."""
    by_cat: dict[str, int] = {}
    by_act: dict[str, int] = {}
    total = 0
    for e in entries:
        act = str(e.get("action") or "")
        if not act.startswith("guardrail."):
            continue
        total += 1
        a = act.split(".", 1)[1]
        by_act[a] = by_act.get(a, 0) + 1
        m = re.search(r"category=([A-Za-z_]+)", str(e.get("detail") or ""))
        c = m.group(1) if m else "other"
        by_cat[c] = by_cat.get(c, 0) + 1
    return {"total": total, "byCategory": by_cat, "byAction": by_act}
