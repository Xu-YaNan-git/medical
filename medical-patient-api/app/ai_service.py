"""Patient triage AI: prefer real LLM, fall back to ai_mock with source + disclaimer."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator, Optional

from app import ai_mock
from app import llm as llm_client
from app.log_config import configure_app_logging

logger = logging.getLogger(__name__)

DISCLAIMER = ai_mock.DISCLAIMER

SYSTEM_PREAMBLE = (
    "你是患者端「导诊助手」，只做科室推荐与急诊分级辅助，不诊断、不开处方、不给出具体用药剂量。"
    "必须强调：辅助导诊，不替代面诊；急危重症请立即急诊或拨打急救电话。"
    "急诊分级宁严勿松：胸痛伴大汗、呼吸困难、大出血、意识障碍、剧烈/爆炸样头痛、一侧肢体无力等 → urgency 必须为 emergency。"
    "科室 id 尽量使用：dept-er, dept-gi, dept-resp, dept-cardio, dept-neuro, dept-uro, "
    "dept-gyn, dept-ortho, dept-gp, dept-ent, dept-derm。"
    "请严格返回可解析的 JSON 对象，不要 Markdown 围栏外的多余文字。"
)

_EMERGENCY_KW = (
    "胸痛",
    "胸口痛",
    "压榨",
    "呼吸困难",
    "气促",
    "喘不过气",
    "咯血",
    "昏迷",
    "意识不清",
    "抽搐",
    "大出血",
    "呕血",
    "剧烈头痛",
    "爆炸样头痛",
    "一侧肢体无力",
    "口角歪斜",
    "言语不清",
    "大汗",
)


def _meta_llm() -> dict[str, Optional[str]]:
    return {"source": "llm", "error": None, "message": None}


def _meta_mock(reason: str, err_code: str = "llm_fallback") -> dict[str, Optional[str]]:
    return {"source": "mock", "error": err_code, "message": reason}


def _blob(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p)


def _has_emergency(text: str) -> bool:
    """True if red-flag symptoms are affirmed (ignore negations like 没有胸痛 / 否认胸痛、呼吸困难)."""
    t = text or ""
    # Drop negation cue + following list up to sentence end (covers 否认A、B)
    cleaned = re.sub(r"(?:没有|无|否|未见|不伴有?|否认)[^。；;\n]{0,40}", " ", t)
    neg = (
        r"(?:没有|无|否|未见|不伴有?|否认)[^，。；,.\n]{0,10}("
        + "|".join(map(re.escape, _EMERGENCY_KW))
        + r")"
    )
    cleaned = re.sub(neg, " ", cleaned)
    return any(k in cleaned for k in _EMERGENCY_KW)

def _normalize_departments(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return items
    for i, it in enumerate(raw[:3]):
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        items.append(
            {
                "id": str(it.get("id") or f"dept-{i + 1}"),
                "name": name,
                "reason": str(it.get("reason") or "根据主诉的初步科室建议").strip(),
                "rank": int(it.get("rank") or (i + 1)),
            }
        )
    for i, d in enumerate(items, 1):
        d["rank"] = i
    return items


def _normalize_urgency(val: Any, blob: str) -> str:
    u = str(val or "routine").strip().lower()
    if u not in ("emergency", "urgent", "routine"):
        u = "routine"
    if _has_emergency(blob):
        return "emergency"
    return u


def _normalize_accompanying(raw: Any, blob: str) -> list[str]:
    items: list[str] = []
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str) and raw.strip():
        items = [p.strip() for p in re.split(r"[、,，/;；]", raw) if p.strip()]
    if not items:
        items = ai_mock._extract_accompanying(blob)
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out[:12]


def _normalize_triage(data: dict[str, Any], blob: str, fallback_summary: str) -> dict[str, Any]:
    depts = _normalize_departments(data.get("departments"))
    if not depts:
        raise ValueError("模型未返回有效科室")
    urgency = _normalize_urgency(data.get("urgency"), blob)
    # Soften over-cautious LLM: recurrent/mild GI without acute flags → routine
    if urgency == "urgent" and not _has_emergency(blob):
        acute = any(k in blob for k in ("剧痛", "突然", "突发", "右下腹", "转移性", "黑便", "呕血", "高热"))
        mild_gi = any(k in blob for k in ("腹痛", "上腹", "胃痛", "反酸", "胃胀"))
        recurrent = any(k in blob for k in ("反复", "偶尔")) or bool(re.search(r"\d+\s*天", blob))
        if mild_gi and recurrent and not acute:
            urgency = "routine"
    suggest_online = bool(data.get("suggestOnline"))
    if urgency == "emergency":
        suggest_online = False
    elif urgency == "routine":
        suggest_online = True if data.get("suggestOnline") is None else suggest_online
    next_steps = data.get("nextSteps") or data.get("next_steps") or []
    if not isinstance(next_steps, list):
        next_steps = [str(next_steps)]
    next_steps = [str(x).strip() for x in next_steps if str(x).strip()][:5]
    if not next_steps:
        next_steps = (
            ["请立即前往就近医院急诊科，或拨打 120"]
            if urgency == "emergency"
            else [f"建议预约：{depts[0]['name']}", "症状加重请及时就医"]
        )
    summary = str(data.get("summary") or fallback_summary or "").strip()
    chief = str(
        data.get("chiefComplaint") or data.get("chief_complaint") or fallback_summary or ""
    ).strip()
    accompanying = _normalize_accompanying(
        data.get("accompanying") or data.get("accompanyingSymptoms"), blob
    )
    return {
        "departments": depts,
        "urgency": urgency,
        "suggestOnline": suggest_online,
        "nextSteps": next_steps,
        "disclaimer": DISCLAIMER,
        "summary": summary,
        "chiefComplaint": chief or (fallback_summary or "")[:80],
        "accompanying": accompanying,
    }


def recommend_triage(
    *,
    chief: str = "",
    duration: str = "",
    body_part: str = "",
    severity: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    extra: Optional[str] = None,
) -> dict[str, Any]:
    """Symptom → departments + urgency. LLM first, rules mock on failure."""
    chief = (chief or "").strip()
    duration = duration or ""
    body_part = body_part or ""
    severity = severity or ""
    extra = extra or ""
    blob = _blob(chief, duration, body_part, severity, extra)

    if llm_client.is_configured():
        try:
            user = (
                f"主诉：{chief}\n时长：{duration or '未提供'}\n部位：{body_part or '未提供'}\n"
                f"严重度：{severity or '未提供'}\n年龄：{age if age is not None else '未提供'}\n"
                f"性别：{gender or '未提供'}\n补充：{extra or '无'}\n\n"
                "返回 JSON："
                '{"chiefComplaint":"...","accompanying":["..."],'
                '"departments":[{"id":"dept-gi","name":"消化内科","reason":"...","rank":1}],'
                '"urgency":"emergency|urgent|routine","suggestOnline":true,'
                '"nextSteps":["..."],"summary":"一句话病情摘要"}。'
                "departments 1～3 个；不诊断、不开药。"
                "无危险信号的反复轻中度腹痛/上腹痛优先 routine，不要标 emergency；仅急危症状才 emergency。"
            )
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE + "任务：症状导诊推荐科室与急诊分级，并给出结构化小结。",
                user,
            )
            result = _normalize_triage(data, blob, chief)
            return {**result, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 导诊失败，已降级规则：{llm_client.sanitize_error(exc)}"
            logger.warning("recommend_triage fallback: %s", reason)
            mock = ai_mock.recommend(
                chief=chief,
                duration=duration,
                body_part=body_part,
                severity=severity or None,
                age=age,
                gender=gender,
                extra=extra or None,
            )
            return {**mock, "disclaimer": DISCLAIMER, **_meta_mock(reason)}

    mock = ai_mock.recommend(
        chief=chief,
        duration=duration,
        body_part=body_part,
        severity=severity or None,
        age=age,
        gender=gender,
        extra=extra or None,
    )
    return {
        **mock,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def recommend(payload: dict[str, Any]) -> dict[str, Any]:
    """Route-facing entry: accepts TriageRecommendRequest.model_dump()."""
    return recommend_triage(
        chief=str(payload.get("chief") or ""),
        duration=str(payload.get("duration") or ""),
        body_part=str(payload.get("bodyPart") or payload.get("body_part") or ""),
        severity=payload.get("severity"),
        age=payload.get("age"),
        gender=payload.get("gender"),
        extra=payload.get("extra"),
    )


def _accumulate_facts(session: dict[str, Any], content: str) -> tuple[int, dict[str, Any], str]:
    """Bump turn counter and merge free-text into facts. Returns (turns, facts, blob)."""
    facts: dict[str, Any] = session.setdefault("facts", {})
    turns = int(session.get("turns") or 0) + 1
    session["turns"] = turns
    blob_preview = (str(facts.get("blob") or "") + " " + content).strip()
    facts["blob"] = blob_preview

    if turns == 1 or not facts.get("chief"):
        facts["chief"] = content[:80]
    elif ai_mock.symptom_shifted(facts, content):
        # A changed complaint must replace the first-turn chief, not sit in extra.
        facts["chief"] = content[:80]
        for stale in ("bodyPart", "duration", "severity"):
            facts.pop(stale, None)
        facts["extra"] = content[:200]
    else:
        facts["extra"] = ((facts.get("extra") or "") + " " + content).strip()

    # Lightweight slot fill (same heuristics as mock; does not overwrite)
    if not facts.get("duration") and any(
        k in content for k in ("天", "周", "月", "小时", "分钟", "反复", "偶尔")
    ):
        facts["duration"] = content[:40]
    if not facts.get("bodyPart") and any(
        k in content for k in ("头", "胸", "腹", "腰", "背", "腿", "喉", "鼻", "皮肤", "胃")
    ):
        facts["bodyPart"] = content[:40]
    if not facts.get("severity"):
        if any(k in content for k in ("重", "剧", "严重", "难以忍受")):
            facts["severity"] = "严重"
        elif any(k in content for k in ("中等", "一般", "还能忍", "中度")):
            facts["severity"] = "中等"
        elif any(k in content for k in ("轻", "稍微", "一点", "轻度")):
            facts["severity"] = "轻"

    acc = list(facts.get("accompanying") or [])
    for item in ai_mock._extract_accompanying(content):
        if item not in acc:
            acc.append(item)
    if acc:
        facts["accompanying"] = acc

    if re.search(r"(没有|无|否认|不伴).{0,6}(胸痛|呼吸困难|大汗|意识)", content):
        facts["redFlags"] = "否认急危症状"
    elif _has_emergency(content):
        facts["redFlags"] = "存在警示症状"

    return turns, facts, blob_preview


MAX_CONSULT_TURNS = 6

_EMERGENCY_NOTICE = (
    "根据您刚才描述的症状，可能存在需要紧急处理的情况。"
    "请立即前往急诊或拨打 120，不要等待线上回复。"
)

CONSULT_SYSTEM = (
    SYSTEM_PREAMBLE
    + "任务：多轮症状问诊。下面的 messages 是完整对话，必须逐条阅读。"
    "最后一条 user 是患者本轮最新输入，优先级最高；它和较早主诉矛盾、加重、减轻、转移部位或新增症状时，"
    "reply 必须先点明这一变化，再只针对最新症状追问或给建议。"
    "禁止复读与当前症状无关的固定问句，禁止把已被患者更正的旧症状继续当作主诉。"
    "每次最多追问 1～2 个问题。信息已经够形成导诊建议时 done=true。"
    "出现急危症状时 done=true，reply 必须写明立即急诊或拨打 120，triage.urgency=emergency，"
    "且 chiefComplaint 写当前这一轮的主要不适。"
    "返回 JSON："
    '{"reply":"...","done":false,"askedSlots":[],"triage":null} 或 '
    '{"reply":"...","done":true,"askedSlots":[],'
    '"triage":{"chiefComplaint":"...","accompanying":["..."],'
    '"departments":[{"id":"dept-gi","name":"消化内科","reason":"...","rank":1}],'
    '"urgency":"emergency|urgent|routine","suggestOnline":false,'
    '"nextSteps":["..."],"summary":"..."}}。'
    "不诊断、不开药。"
)


def log_consult_llm(
    *,
    llm_called: bool,
    llm_status: str,
    fallback: bool,
    turns: int,
    history_count: int,
    error_code: str = "-",
) -> None:
    """Grep-friendly consult trace. No utterance text, keys, or tokens."""
    configure_app_logging()
    code = error_code or "-"
    if code not in ("-", "llm_fallback", "llm_not_configured", "guardrail"):
        code = "llm_error"
    logger.info(
        "consult_llm llm_called=%s llm_status=%s fallback=%s turns=%s history_count=%s error_code=%s",
        "true" if llm_called else "false",
        llm_status,
        "true" if fallback else "false",
        int(turns or 0),
        int(history_count or 0),
        code,
    )


def _consult_messages(session: dict[str, Any], content: str) -> list[dict[str, str]]:
    """Full user/assistant history, with the latest user text as the last turn."""
    out: list[dict[str, str]] = []
    for raw in session.get("messages") or []:
        role = str(raw.get("role") or "")
        text = str(raw.get("content") or "").strip()
        if role not in ("user", "assistant") or not text:
            continue
        if out and out[-1]["role"] == role and out[-1]["content"] == text:
            continue
        out.append({"role": role, "content": text})
    content = (content or "").strip()
    if content and (not out or out[-1]["role"] != "user" or out[-1]["content"] != content):
        out.append({"role": "user", "content": content})
    if len(out) > 16:
        out = out[-16:]
    while out and out[0]["role"] != "user":
        out = out[1:]
    return out


def _with_emergency_notice(reply: str, text: str) -> str:
    if not _has_emergency(text):
        return reply
    if "急诊" in reply or "120" in reply:
        return reply
    return _EMERGENCY_NOTICE + "\n\n" + (reply or "")


def _llm_turn_flags(*, called: bool, status: str, fallback: bool) -> dict[str, Any]:
    return {"llmCalled": called, "llmStatus": status, "fallback": fallback}


def _pack_mock_turn(
    session: dict[str, Any],
    mock: dict[str, Any],
    *,
    reason: str,
    code: str,
    called: bool,
    status: str,
) -> dict[str, Any]:
    meta = _meta_mock(reason, code)
    triage = mock.get("triage")
    if isinstance(triage, dict):
        triage = {**triage, **meta}
    return {
        "reply": mock["reply"],
        "status": mock.get("status") or session.get("status") or "active",
        "triage": triage,
        "disclaimer": DISCLAIMER,
        **meta,
        **_llm_turn_flags(called=called, status=status, fallback=True),
    }


def _finalize_done(
    session: dict[str, Any],
    *,
    reply: str,
    raw_triage: Any,
    blob_preview: str,
    facts: dict[str, Any],
    content: str,
    source_meta: dict[str, Optional[str]],
) -> dict[str, Any]:
    if isinstance(raw_triage, dict) and raw_triage.get("departments"):
        triage = _normalize_triage(raw_triage, blob_preview, str(facts.get("chief") or content))
        triage = {**triage, **source_meta}
    else:
        triage = recommend_triage(
            chief=str(facts.get("chief") or content),
            duration=str(facts.get("duration") or ""),
            body_part=str(facts.get("bodyPart") or ""),
            severity=facts.get("severity"),
            age=facts.get("age"),
            gender=facts.get("gender"),
            extra=str(facts.get("extra") or blob_preview),
        )
    # Prefer session-known accompanying if model omitted
    if not triage.get("accompanying") and facts.get("accompanying"):
        triage["accompanying"] = list(facts["accompanying"])
    latest_chief = str(facts.get("chief") or content or "").strip()
    model_chief = str(triage.get("chiefComplaint") or "")
    fresh_keys = [k for k in ai_mock._SYMPTOM_KEYS if k in (content or "")]
    if latest_chief and fresh_keys and not any(k in model_chief for k in fresh_keys):
        triage["chiefComplaint"] = latest_chief[:80]
    if _has_emergency(blob_preview):
        triage["urgency"] = "emergency"
        triage["suggestOnline"] = False
        if "急诊" not in reply:
            reply = (
                "根据您描述，可能存在需要紧急处理的情况。"
                "请立即前往急诊或拨打急救电话。\n\n" + reply
            )
    session["status"] = "completed"
    session["triage"] = triage
    return {
        "reply": reply,
        "status": "completed",
        "triage": triage,
        "disclaimer": DISCLAIMER,
        **source_meta,
    }


def consult_turn(session: dict[str, Any], user_content: str) -> dict[str, Any]:
    """
    One user turn. Mutates session turns/facts/status/triage (like ai_mock.consult_reply).
    Does NOT append to session["messages"] — routes own message list.

    The model sees the full user/assistant history, with this turn's text last.
    Slot completeness no longer forces an early summary, so a changed complaint
    can still change the next question. Emergency wording still ends the turn
    with an ER notice.
    """
    content = (user_content or "").strip()
    if not content:
        raise ValueError("消息不能为空")

    history = _consult_messages(session, content)
    history_count = len(history)
    flags_ok = _llm_turn_flags(called=True, status="ok", fallback=False)

    if not llm_client.is_configured():
        mock = ai_mock.consult_reply(session, content)
        log_consult_llm(
            llm_called=False,
            llm_status="skipped",
            fallback=True,
            turns=int(session.get("turns") or 0),
            history_count=history_count,
            error_code="llm_not_configured",
        )
        return _pack_mock_turn(
            session,
            mock,
            reason="未配置 LLM_API_KEY，使用规则模板",
            code="llm_not_configured",
            called=False,
            status="skipped",
        )

    accumulated = False
    try:
        data = llm_client.chat_json_messages(CONSULT_SYSTEM, history)
        reply = str(data.get("reply") or "").strip()
        if not reply:
            raise ValueError("澄清回复为空")
        turns, facts, blob_preview = _accumulate_facts(session, content)
        accumulated = True
        asked = list(facts.get("askedSlots") or [])
        for slot in data.get("askedSlots") or []:
            slot = str(slot).strip()
            if slot and slot not in asked:
                asked.append(slot)
        facts["askedSlots"] = asked

        reply = _with_emergency_notice(reply, blob_preview)
        urgent = _has_emergency(content) or _has_emergency(blob_preview)
        done = bool(data.get("done")) or turns >= MAX_CONSULT_TURNS or urgent
        if done:
            result = _finalize_done(
                session,
                reply=reply,
                raw_triage=data.get("triage"),
                blob_preview=blob_preview,
                facts=facts,
                content=content,
                source_meta=_meta_llm(),
            )
            result.update(flags_ok)
            log_consult_llm(
                llm_called=True,
                llm_status="ok",
                fallback=False,
                turns=turns,
                history_count=history_count,
            )
            return result

        session["status"] = "active"
        log_consult_llm(
            llm_called=True,
            llm_status="ok",
            fallback=False,
            turns=turns,
            history_count=history_count,
        )
        return {
            "reply": reply,
            "status": "active",
            "triage": None,
            "disclaimer": DISCLAIMER,
            **_meta_llm(),
            **flags_ok,
        }
    except Exception as exc:
        reason = f"LLM 问诊失败，已降级规则：{llm_client.sanitize_error(exc)}"
        if accumulated:
            session["turns"] = max(0, int(session.get("turns") or 1) - 1)
            facts = session.setdefault("facts", {})
            blob = str(facts.get("blob") or "")
            if content and blob.endswith(content):
                facts["blob"] = blob[: -len(content)].strip()
        mock = ai_mock.consult_reply(session, content)
        log_consult_llm(
            llm_called=True,
            llm_status="error",
            fallback=True,
            turns=int(session.get("turns") or 0),
            history_count=history_count,
            error_code="llm_fallback",
        )
        return _pack_mock_turn(
            session,
            mock,
            reason=reason,
            code="llm_fallback",
            called=True,
            status="error",
        )


def _chunk_text(text: str, size: int = 8) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def consult_turn_stream(session: dict[str, Any], user_content: str) -> Iterator[dict[str, Any]]:
    """
    Streaming consult turn. Yields event dicts:
      {"type":"token","text":"..."}
      {"type":"final","reply":...,"status":...,"triage":...,"disclaimer":...,"source":...}
    Same decision as consult_turn (one model call), then chunks the reply.
    """
    final = consult_turn(session, user_content)
    reply = str(final.get("reply") or "")
    for piece in _chunk_text(reply, 12):
        yield {"type": "token", "text": piece}
    yield {"type": "final", **final}


def force_summary(session: dict[str, Any]) -> dict[str, Any]:
    """Build triage summary from session facts/messages."""
    facts = session.get("facts") or {}
    messages = session.get("messages") or []
    blob = str(facts.get("blob") or "")
    if not blob:
        blob = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    chief = str(facts.get("chief") or blob[:80])
    triage = recommend_triage(
        chief=chief,
        duration=str(facts.get("duration") or ""),
        body_part=str(facts.get("bodyPart") or ""),
        severity=facts.get("severity"),
        age=facts.get("age"),
        gender=facts.get("gender"),
        extra=str(facts.get("extra") or blob),
    )
    if facts.get("accompanying") and not triage.get("accompanying"):
        triage["accompanying"] = list(facts["accompanying"])
    session["triage"] = triage
    if session.get("status") != "completed":
        session["status"] = "completed"
    return triage


# ---------- Previsit report & lab/imaging interpretation ----------
PREVISIT_DISCLAIMER = ai_mock.PREVISIT_DISCLAIMER
REPORT_INTERPRET_DISCLAIMER = ai_mock.REPORT_INTERPRET_DISCLAIMER


def _gather_previsit_input(
    *,
    session: Optional[dict[str, Any]] = None,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Merge completed consult session + explicit request fields into one input dict."""
    payload = payload or {}
    facts: dict[str, Any] = {}
    triage: dict[str, Any] = {}
    user_messages: list[str] = []
    session_id = payload.get("sessionId")

    if session:
        session_id = session.get("id") or session_id
        facts = dict(session.get("facts") or {})
        triage = dict(session.get("triage") or {})
        user_messages = [
            str(m.get("content") or "")
            for m in (session.get("messages") or [])
            if m.get("role") == "user" and m.get("content")
        ]
        # If session not completed but has enough facts, synthesize triage
        if not triage and (facts.get("chief") or user_messages):
            try:
                triage = force_summary(session) or {}
            except Exception as exc:
                logger.warning("force_summary for previsit failed: %s", exc)
                triage = {}

    chief = (
        payload.get("chiefComplaint")
        or facts.get("chief")
        or triage.get("chiefComplaint")
        or (user_messages[0][:80] if user_messages else "")
        or ""
    )
    duration = payload.get("duration") or facts.get("duration") or ""
    body_part = payload.get("bodyPart") or facts.get("bodyPart") or ""
    accompanying = payload.get("accompanying")
    if accompanying is None:
        accompanying = facts.get("accompanying") or triage.get("accompanying") or []
    past_history = payload.get("pastHistory") or facts.get("pastHistory") or ""
    allergies = payload.get("allergies") or facts.get("allergies") or ""
    medications = payload.get("medications") or facts.get("medications") or ""
    patient_notes = payload.get("patientNotes") or ""
    urgency = payload.get("urgency") or triage.get("urgency")
    departments = payload.get("departments")
    if departments is None:
        departments = triage.get("departments")
    age = payload.get("age") if payload.get("age") is not None else facts.get("age")
    gender = payload.get("gender") or facts.get("gender")
    extra = payload.get("extra") or facts.get("extra") or facts.get("blob") or ""

    return {
        "sessionId": session_id,
        "chief": str(chief or "").strip(),
        "duration": str(duration or ""),
        "body_part": str(body_part or ""),
        "accompanying": list(accompanying or []),
        "past_history": str(past_history or ""),
        "allergies": str(allergies or ""),
        "medications": str(medications or ""),
        "patient_notes": str(patient_notes or ""),
        "urgency": urgency,
        "departments": departments,
        "age": age,
        "gender": gender,
        "extra": str(extra or ""),
        "user_messages": user_messages,
        "triage": triage,
    }


def _normalize_previsit(
    data: dict[str, Any],
    fallback: dict[str, Any],
    *,
    patient_blob: str = "",
) -> dict[str, Any]:
    depts = _normalize_departments(data.get("suggestedDepartments") or data.get("departments"))
    if not depts:
        depts = _normalize_departments(
            fallback.get("suggestedDepartments") or fallback.get("departments")
        )
    urg = str(data.get("urgency") or fallback.get("urgency") or "routine").strip().lower()
    if urg not in ("emergency", "urgent", "routine"):
        urg = "routine"
    # Patient-affirmed text only for emergency override (ignore AI differential lists)
    check_blob = patient_blob or _blob(
        fallback.get("chiefComplaint"),
        fallback.get("patientNarrative"),
    )
    if _has_emergency(check_blob):
        urg = "emergency"
    elif urg == "emergency" and not _has_emergency(check_blob):
        urg = str(fallback.get("urgency") or "routine")
        if urg not in ("emergency", "urgent", "routine"):
            urg = "routine"
    blob = _blob(
        data.get("chiefComplaint") or fallback.get("chiefComplaint"),
        data.get("presentIllness") or fallback.get("presentIllness"),
        data.get("patientNarrative") or fallback.get("patientNarrative"),
        check_blob,
    )
    accompanying = _normalize_accompanying(
        data.get("accompanying") or fallback.get("accompanying"), blob
    )
    red = data.get("redFlags") or fallback.get("redFlags") or []
    if not isinstance(red, list):
        red = [str(red)]
    red = [str(x).strip() for x in red if str(x).strip()][:10]
    hints = data.get("doctorHints") or fallback.get("doctorHints") or []
    if not isinstance(hints, list):
        hints = [str(hints)]
    hints = [str(x).strip() for x in hints if str(x).strip()][:8]
    return {
        "chiefComplaint": str(
            data.get("chiefComplaint") or fallback.get("chiefComplaint") or "未明确"
        ).strip(),
        "presentIllness": str(
            data.get("presentIllness") or fallback.get("presentIllness") or ""
        ).strip(),
        "accompanying": accompanying,
        "relevantHistory": str(
            data.get("relevantHistory") or fallback.get("relevantHistory") or ""
        ).strip(),
        "urgency": urg,
        "suggestedDepartments": depts,
        "patientNarrative": str(
            data.get("patientNarrative") or fallback.get("patientNarrative") or ""
        ).strip(),
        "redFlags": red,
        "doctorHints": hints,
        "summaryText": str(
            data.get("summaryText") or fallback.get("summaryText") or ""
        ).strip(),
        "disclaimer": PREVISIT_DISCLAIMER,
    }


def generate_previsit_report(
    *,
    session: Optional[dict[str, Any]] = None,
    payload: Optional[dict[str, Any]] = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Doctor-facing structured previsit summary. LLM first, mock on failure.

    use_llm=False (S2 guardrail redflag) → rules only, no LLM call."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    inp = _gather_previsit_input(session=session, payload=payload)
    if not inp["chief"] and not inp["user_messages"] and not (inp.get("triage") or {}).get("departments"):
        raise ValueError("缺少主诉或会话内容，无法生成预问诊报告")

    mock = ai_mock.build_previsit_report(
        chief=inp["chief"],
        duration=inp["duration"],
        body_part=inp["body_part"],
        accompanying=inp["accompanying"],
        past_history=inp["past_history"],
        allergies=inp["allergies"],
        medications=inp["medications"],
        patient_notes=inp["patient_notes"],
        urgency=inp["urgency"],
        departments=inp["departments"],
        age=inp["age"],
        gender=inp["gender"],
        extra=inp["extra"],
        user_messages=inp["user_messages"],
        triage=inp["triage"],
    )

    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    base_meta = {"sessionId": inp.get("sessionId"), "generatedAt": generated_at}

    if not use_llm:
        return {
            **mock,
            "disclaimer": PREVISIT_DISCLAIMER,
            **base_meta,
            "source": "guardrail",
            "error": None,
            "message": "命中急危红旗，预问诊报告由规则生成（未调用 LLM）",
        }

    if llm_client.is_configured():
        try:
            system = (
                "你是临床预问诊报告助手，为接诊医生生成结构化摘要。"
                "不诊断、不开处方、不给出具体用药剂量。"
                "必须标明内容由 AI 根据患者自述生成，仅供参考，不能替代面诊与病历。"
                "急诊分级宁严勿松。严格返回 JSON 对象。"
            )
            user = (
                f"输入：{json.dumps({k: v for k, v in inp.items() if k != 'triage' or v}, ensure_ascii=False)}\n"
                f"已有导诊 triage：{json.dumps(inp.get('triage') or {}, ensure_ascii=False)}\n"
                "返回 JSON："
                '{"chiefComplaint":"...","presentIllness":"现病史要点段落",'
                '"accompanying":["..."],"relevantHistory":"既往/过敏/用药",'
                '"urgency":"emergency|urgent|routine",'
                '"suggestedDepartments":[{"id":"dept-gi","name":"消化内科","reason":"...","rank":1}],'
                '"patientNarrative":"患者自述要点","redFlags":["..."],'
                '"doctorHints":["给医生的提醒"],"summaryText":"一段给医生的摘要"}。'
            )
            data = llm_client.chat_json(system, user)
            patient_blob = _blob(
                inp["chief"],
                inp["duration"],
                inp["body_part"],
                inp["extra"],
                inp["patient_notes"],
                " ".join(inp.get("user_messages") or []),
            )
            result = _normalize_previsit(data, mock, patient_blob=patient_blob)
            if not result.get("suggestedDepartments"):
                result["suggestedDepartments"] = list(
                    mock.get("suggestedDepartments") or mock.get("departments") or []
                )
            if not result.get("suggestedDepartments"):
                rec = recommend_triage(
                    chief=inp["chief"] or patient_blob[:40],
                    duration=inp["duration"],
                    body_part=inp["body_part"],
                    age=inp["age"],
                    gender=inp["gender"],
                    extra=inp["extra"] or patient_blob,
                )
                result["suggestedDepartments"] = rec.get("departments") or []
                if result.get("urgency") in (None, "routine") and rec.get("urgency"):
                    result["urgency"] = rec["urgency"]
            return {**result, **base_meta, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 预问诊报告失败，已降级规则：{llm_client.sanitize_error(exc)}"
            logger.warning("generate_previsit_report fallback: %s", reason)
            return {
                **mock,
                "disclaimer": PREVISIT_DISCLAIMER,
                **base_meta,
                **_meta_mock(reason),
            }

    return {
        **mock,
        "disclaimer": PREVISIT_DISCLAIMER,
        **base_meta,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def _normalize_interpret(data: dict[str, Any], fallback: dict[str, Any], report_type: Optional[str]) -> dict[str, Any]:
    interpretation = str(
        data.get("interpretation") or fallback.get("interpretation") or ""
    ).strip()
    if not interpretation:
        raise ValueError("解读内容为空")
    abn_raw = data.get("abnormalities")
    if not isinstance(abn_raw, list):
        abn_raw = fallback.get("abnormalities") or []
    abnormalities: list[dict[str, str]] = []
    for it in abn_raw[:20]:
        if not isinstance(it, dict):
            continue
        item = str(it.get("item") or "").strip()
        finding = str(it.get("finding") or "").strip()
        sev = str(it.get("severity") or "info").strip().lower()
        if sev not in ("high", "moderate", "low", "info"):
            sev = "info"
        if item or finding:
            abnormalities.append(
                {"item": item or "指标", "finding": finding or item, "severity": sev}
            )
    advice = data.get("advice") or fallback.get("advice") or []
    if not isinstance(advice, list):
        advice = [str(advice)]
    advice = [str(x).strip() for x in advice if str(x).strip()][:8]
    if not advice:
        advice = list(fallback.get("advice") or [])
    rtype = data.get("reportType") or report_type or fallback.get("reportType") or "other"
    return {
        "interpretation": interpretation,
        "abnormalities": abnormalities,
        "advice": advice,
        "disclaimer": REPORT_INTERPRET_DISCLAIMER,
        "reportType": rtype,
    }


def interpret_report(*, text: str, report_type: Optional[str] = None) -> dict[str, Any]:
    """Lab/imaging report → plain-language interpretation. Strong disclaimer always."""
    text = (text or "").strip()
    if not text:
        raise ValueError("报告文本不能为空")
    if len(text) > 20000:
        text = text[:20000]

    mock = ai_mock.interpret_report(text=text, report_type=report_type)

    if llm_client.is_configured():
        try:
            system = (
                "你是患者端报告解读助手。根据检验/检查报告文本给出通俗解读、异常提示与就医建议。"
                "严禁给出确定诊断或处方；必须强调：非诊断、不能替代医生与正式报告。"
                "急危提示宁严勿松。严格返回 JSON。"
            )
            user = (
                f"报告类型提示：{report_type or '未指定'}\n"
                f"报告文本：\n{text}\n\n"
                "返回 JSON："
                '{"interpretation":"通俗解读段落",'
                '"abnormalities":[{"item":"项目","finding":"所见","severity":"high|moderate|low|info"}],'
                '"advice":["就医建议1","..."],'
                '"reportType":"lab|imaging|other"}。'
                "severity：明显危急/显著异常用 high，轻度异常 moderate，需关注 low，说明性 info。"
            )
            data = llm_client.chat_json(system, user)
            result = _normalize_interpret(data, mock, report_type)
            return {**result, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 报告解读失败，已降级规则：{llm_client.sanitize_error(exc)}"
            logger.warning("interpret_report fallback: %s", reason)
            return {
                **mock,
                "disclaimer": REPORT_INTERPRET_DISCLAIMER,
                **_meta_mock(reason),
            }

    return {
        **mock,
        "disclaimer": REPORT_INTERPRET_DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }
