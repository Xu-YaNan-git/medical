"""check_output: post-process LLM / mock output before returning it to a client."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable, Optional, Union

from .constants import AI_NOTICE, DISCLAIMER, ROLES

try:  # declared dependency; guarded so import never breaks the API
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover
    jsonschema = None  # type: ignore

# --- deterministic diagnosis wording -------------------------------------------------
_HEDGE = re.compile(r"(可能|也许|或许|疑似|考虑|不排除|怀疑|倾向|需排除|是否)$")
_DIAG = re.compile(
    r"(?:"
    r"(?:(?:你|您|患者|孩子|他|她)(?:已经|就是|是)?)?"
    r"(?:得了|患了|患上了?|患有|确诊为|确诊是|确诊了|诊断为|诊断是|可以确诊为?|可确诊为?"
    r"|肯定是|一定是|毫无疑问是|明确是|可以确定是|可确定是|百分之百是|毋庸置疑是|就是得了)"
    r"|(?:你|您)这(?:就)?是"
    r")"
    r"\s*(?P<x>[^，,。.；;！!？?\n|（(]{1,20})"
)

# --- concrete dosage ----------------------------------------------------------------
_NUM = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半百]+)"
_UNIT = r"(?:mg|毫克|μg|ug|mcg|微克|g(?![a-z])|克|ml|毫升|iu|国际单位|单位|片|粒|颗|丸|袋|包|支|滴|喷|贴|勺)"
# concentration / lab units are NOT doses: 110 g/L, 35 IU/L, 5.6 mmol/L, 120 mg/dL, 4.5×10^9/L
_NOT_CONC = r"(?!\s*(?:/|每)\s*(?:[μu]?l|dl|ml|升|分升|毫升)(?![a-z]))"
_DOSE_PATTERNS = [
    # 每次1片 / 一次2粒 / 每次 500mg
    rf"(?:每|一)次\s*{_NUM}\s*{_UNIT}{_NOT_CONC}",
    # 500mg / 0.5 g / 两片 / 1-2 粒 / 10mg/kg
    rf"(?<![0-9.]){_NUM}\s*(?:(?:-|~|～|至|到)\s*{_NUM}\s*)?{_UNIT}(?:/(?:次|日|天|kg|千克))?{_NOT_CONC}",
    # 拉丁频次缩写
    r"(?<![a-z])(?:qd|bid|tid|qid|qn|qod|prn|q\d+h)(?![a-z])",
]
_DOSE = re.compile("|".join(f"(?:{p})" for p in _DOSE_PATTERNS), re.I)
# 每日3次 / 一天三次: treated as dosage frequency unless it describes a symptom
# right before it (e.g. "腹泻一天五六次", "咳嗽每天3次发作")
_FREQ = re.compile(rf"(?:每|一)?(?:日|天|晚|早|顿)\s*{_NUM}\s*(?:次|回)")
_SYMPTOM_CTX = re.compile(r"泻|拉|吐|呕|咳|喘|发作|大便|小便|排便|解便|尿|疼|痛|醒|晕|抽|烧|出血|心慌|胸闷")
_DOSE_REPLACEMENT = "［剂量请遵医嘱］"
_DUP_REPL = re.compile(r"［剂量请遵医嘱］(?:[，,、\s]*［剂量请遵医嘱］)+")

_SKIP_KEYS = {"id", "source", "disclaimer", "aiNotice", "rank", "urgency", "category", "action"}


def _drug_freq_spans(s: str) -> list[tuple[int, int]]:
    spans = []
    for m in _FREQ.finditer(s):
        before = re.split(r"[\n|;；]", s[max(0, m.start() - 6): m.start()])[-1]
        after = re.split(r"[\n|;；]", s[m.end(): m.end() + 4])[0]
        if not (_SYMPTOM_CTX.search(before) or re.match(r"[^，,。；;\n|]{0,2}(发作|大便|排便|腹泻)", after)):
            spans.append((m.start(), m.end()))
    return spans


def has_dosage(text: str) -> bool:
    t = text or ""
    return bool(_DOSE.search(t)) or bool(_drug_freq_spans(t))


def _fix_diagnosis(s: str) -> tuple[str, bool]:
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        before = s[max(0, m.start() - 4): m.start()]
        if _HEDGE.search(before):
            return m.group(0)
        changed = True
        return f"可能与{m.group('x').strip()}有关，需医生评估"

    out = _DIAG.sub(repl, s)
    return out, changed


def _fix_dosage(s: str) -> tuple[str, bool]:
    if not has_dosage(s):
        return s, False
    spans = _drug_freq_spans(s)
    for a, b in reversed(spans):
        s = s[:a] + _DOSE_REPLACEMENT + s[b:]
    out = _DOSE.sub(_DOSE_REPLACEMENT, s)
    out = _DUP_REPL.sub(_DOSE_REPLACEMENT, out)
    return out, True


def _sanitize_str(s: str, flags: set) -> str:
    s2, d = _fix_diagnosis(s)
    if d:
        flags.add("removed_diagnosis")
    s3, q = _fix_dosage(s2)
    if q:
        flags.add("removed_dosage")
    return s3


def _sanitize_obj(obj: Any, flags: set, key: Optional[str] = None) -> Any:
    if isinstance(obj, str):
        return obj if key in _SKIP_KEYS else _sanitize_str(obj, flags)
    if isinstance(obj, dict):
        return {k: _sanitize_obj(v, flags, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_obj(v, flags, key) for v in obj]
    return obj


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


def _validate(output: Any, schema: dict) -> tuple[bool, Any]:
    data = output
    if isinstance(output, str):
        try:
            data = json.loads(_strip_fence(output))
        except Exception:
            return False, output
    if jsonschema is None:  # pragma: no cover
        raise RuntimeError("jsonschema 未安装：pip install jsonschema")
    cls = jsonschema.validators.validator_for(schema)
    try:
        cls(schema).validate(data)
    except jsonschema.ValidationError:
        return False, output
    return True, data


def check_output(
    output: Union[str, dict, list],
    role: str = "patient",
    schema: Optional[dict] = None,
    fallback: Union[Callable[[], Any], dict, None] = None,
) -> dict:
    """Return {output, source, modified, flags, needs_doctor_confirm}."""
    role = role if role in ROLES else "patient"
    flags: set = set()
    order: list[str] = []
    source = None
    modified = False
    out: Any = copy.deepcopy(output)

    if schema is not None:
        ok, parsed = _validate(out, schema)
        if ok:
            out = parsed
        else:
            flags.add("schema_invalid")
            if fallback is not None:
                out = fallback() if callable(fallback) else copy.deepcopy(fallback)
                source = "mock_fallback"
                flags.add("mock_fallback")
                modified = True

    if role == "doctor":
        if isinstance(out, dict) and out.get("aiNotice") != AI_NOTICE:
            out["aiNotice"] = AI_NOTICE
            flags.add("added_ai_notice")
            modified = True
        flags.add("needs_doctor_confirm")
        needs_confirm = True
    else:
        needs_confirm = False
        before = json.dumps(out, ensure_ascii=False, sort_keys=True, default=str)
        out = _sanitize_obj(out, flags)
        if isinstance(out, dict):
            if not str(out.get("disclaimer") or "").strip():
                out["disclaimer"] = DISCLAIMER
                flags.add("added_disclaimer")
        elif isinstance(out, str):
            if DISCLAIMER not in out:
                out = (out.rstrip() + "\n\n" + DISCLAIMER) if out.strip() else DISCLAIMER
                flags.add("added_disclaimer")
        elif isinstance(out, list):
            out = {"items": out, "disclaimer": DISCLAIMER}
            flags.add("added_disclaimer")
        after = json.dumps(out, ensure_ascii=False, sort_keys=True, default=str)
        modified = modified or before != after

    for f in ("schema_invalid", "mock_fallback", "removed_diagnosis", "removed_dosage",
              "added_disclaimer", "added_ai_notice", "needs_doctor_confirm"):
        if f in flags:
            order.append(f)

    return {
        "output": out,
        "source": source,
        "modified": modified,
        "flags": order,
        "needs_doctor_confirm": needs_confirm,
    }
