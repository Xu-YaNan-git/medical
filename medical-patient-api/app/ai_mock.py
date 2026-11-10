"""Rule-based mock for patient triage and multi-turn consult."""

from __future__ import annotations

import re
from typing import Any, Optional

DISCLAIMER = "辅助导诊，不替代面诊。急危重症请立即前往急诊或拨打急救电话。"

DEPT = {
    "er": ("dept-er", "急诊科"),
    "gi": ("dept-gi", "消化内科"),
    "resp": ("dept-resp", "呼吸内科"),
    "cardio": ("dept-cardio", "心内科"),
    "neuro": ("dept-neuro", "神经内科"),
    "uro": ("dept-uro", "泌尿外科"),
    "gyn": ("dept-gyn", "妇科"),
    "ortho": ("dept-ortho", "骨科"),
    "gp": ("dept-gp", "全科医学"),
    "ent": ("dept-ent", "耳鼻喉科"),
    "derm": ("dept-derm", "皮肤科"),
}

_EMERGENCY_KEYWORDS = [
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
    "黑便伴晕厥",
    "突然剧痛",
    "重度头痛",
    "剧烈头痛",
    "爆炸样头痛",
    "一侧肢体无力",
    "口角歪斜",
    "言语不清",
    "自杀",
    "中毒",
    "大汗",
]

_CHANGE_RE = re.compile(
    r"(现在|变成|改为|改成|其实|不是.{0,16}(?:是|了)|转成|开始出现|新出现|又出现|加重|减轻|不再)"
)
_PARTS = ("头", "胸", "腹", "肚", "腰", "背", "腿", "喉", "鼻", "皮肤", "胃", "眼", "关节")
_SYMPTOM_KEYS = (
    "头痛", "头疼", "头晕", "胸痛", "胸口", "胸闷", "腹痛", "肚子疼", "胃痛",
    "腹泻", "拉肚子", "咳嗽", "咳痰", "皮疹", "瘙痒", "发热", "发烧",
    "恶心", "呕吐", "关节痛", "腰痛", "尿频", "尿痛",
)


def symptom_shifted(facts: dict[str, Any], content: str) -> bool:
    """True when the latest utterance changes the complaint already on file."""
    text = content or ""
    if _CHANGE_RE.search(text):
        return True
    old = "".join(str(facts.get(k) or "") for k in ("chief", "bodyPart", "extra"))
    if any(part in text and part not in old for part in _PARTS):
        return True
    return any(key in text and key not in old for key in _SYMPTOM_KEYS)


# Clarifying slots: ask only what is still missing
_SLOT_QUESTIONS: list[tuple[str, str]] = [
    ("bodyPart", "请问主要不舒服的部位在哪里？"),
    ("duration", "症状大概持续多久了？"),
    ("accompanying", "有没有发热、恶心、呕吐、腹泻、头晕等伴随症状？"),
    ("redFlags", "有没有胸痛、呼吸困难、大汗、意识改变等？"),
    ("severity", "不适程度如何（轻/中/重）？"),
]


def _strip_negated_emergency(text: str) -> str:
    """Drop spans like 没有胸痛 / 否认胸痛、呼吸困难 so negation does not trip red flags."""
    t = text or ""
    t = re.sub(r"(?:没有|无|否|未见|不伴有?|否认)[^。；;\n]{0,40}", " ", t)
    neg = (
        r"(?:没有|无|否|未见|不伴有?|否认)[^，。；,.\n]{0,10}("
        + "|".join(map(re.escape, _EMERGENCY_KEYWORDS))
        + r")"
    )
    return re.sub(neg, " ", t)

def _has_emergency_signal(text: str) -> bool:
    return any(k in _strip_negated_emergency(text) for k in _EMERGENCY_KEYWORDS)


def _dept(key: str, reason: str, rank: int) -> dict[str, Any]:
    did, name = DEPT[key]
    return {"id": did, "name": name, "reason": reason, "rank": rank}


def _text_blob(chief: str, duration: str, body_part: str, extra: str, severity: str) -> str:
    return " ".join(
        x for x in [chief or "", duration or "", body_part or "", extra or "", severity or ""] if x
    )


def _extract_accompanying(blob: str) -> list[str]:
    mapping = [
        ("发热", ("发热", "发烧", "高热")),
        ("恶心", ("恶心",)),
        ("呕吐", ("呕吐", "吐了")),
        ("腹泻", ("腹泻", "拉肚子")),
        ("反酸", ("反酸", "烧心")),
        ("腹胀", ("腹胀", "胃胀")),
        ("头晕", ("头晕", "眩晕")),
        ("咳嗽", ("咳嗽", "咳痰")),
        ("乏力", ("乏力", "没力气")),
        ("大汗", ("大汗", "冷汗")),
        ("呼吸困难", ("呼吸困难", "气促", "喘不过气")),
    ]
    cleaned = _strip_negated_emergency(blob)
    found: list[str] = []
    for label, keys in mapping:
        if any(k in cleaned for k in keys):
            found.append(label)
    return found


def _enrich_structured(
    triage: dict[str, Any],
    *,
    chief: str,
    blob: str,
    accompanying: Optional[list[str]] = None,
) -> dict[str, Any]:
    acc = accompanying if accompanying is not None else _extract_accompanying(blob)
    triage = dict(triage)
    triage["chiefComplaint"] = (chief or triage.get("chiefComplaint") or "").strip() or (
        (blob or "")[:80]
    )
    triage["accompanying"] = acc
    triage["disclaimer"] = DISCLAIMER
    return triage


def recommend(
    *,
    chief: str = "",
    duration: str = "",
    body_part: str = "",
    severity: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    extra: Optional[str] = None,
) -> dict[str, Any]:
    """Keyword/rules triage → 1–3 departments + urgency."""
    blob = _text_blob(chief, duration, body_part or "", extra or "", severity or "")
    sev = (severity or "").lower()
    accompanying = _extract_accompanying(blob)

    flagged = _strip_negated_emergency(blob)
    # Only treat severity as emergency when paired with red-flag language,
    # not bare 「严重」 alone (e.g. recurrent mild-moderate abdominal pain).
    is_emergency = _has_emergency_signal(blob) or sev in ("emergency",)

    chest = any(k in flagged for k in ("胸痛", "胸口", "心慌", "心悸"))
    sob = any(k in flagged for k in ("呼吸困难", "气促", "喘", "气短"))
    severe_headache = any(k in flagged for k in ("剧烈头痛", "爆炸样", "最痛", "突然头痛"))

    if is_emergency or (chest and sob) or severe_headache or (chest and "大汗" in flagged):
        depts = [
            _dept("er", "存在急危重症警示症状，建议优先急诊评估", 1),
        ]
        if chest or sob:
            depts.append(_dept("cardio", "胸痛/呼吸困难需心内科鉴别心源性疾病", 2))
        if severe_headache or any(k in blob for k in ("肢体无力", "口角", "言语")):
            depts.append(
                _dept("neuro", "突发神经系统症状需神经内科评估", 2 if len(depts) == 1 else 3)
            )
        depts = depts[:3]
        for i, d in enumerate(depts, 1):
            d["rank"] = i
        return _enrich_structured(
            {
                "departments": depts,
                "urgency": "emergency",
                "suggestOnline": False,
                "nextSteps": [
                    "请立即前往就近医院急诊科，或拨打 120",
                    "尽量有人陪同，避免自行驾车",
                    "携带既往病历与用药清单",
                ],
                "disclaimer": DISCLAIMER,
                "source": "mock",
                "summary": f"根据「{chief or '所述症状'}」判断存在急诊警示，优先急诊。",
            },
            chief=chief,
            blob=blob,
            accompanying=accompanying,
        )

    departments: list[dict[str, Any]] = []
    urgency = "routine"
    suggest_online = True
    next_steps: list[str] = []

    fever = any(k in blob for k in ("发热", "发烧", "高热", "体温"))
    cough = any(k in blob for k in ("咳嗽", "咳痰", "干咳", "咽痛"))
    abd = any(
        k in blob
        for k in (
            "腹痛", "肚子疼", "上腹", "下腹", "反酸", "烧心", "腹泻", "恶心", "呕吐",
            "拉肚子", "拉稀", "水样便", "稀便", "闹肚子",
        )
    )
    dizzy = any(k in blob for k in ("头晕", "眩晕", "头昏"))
    headache = any(k in blob for k in ("头痛", "头疼", "偏头痛"))
    urine = any(k in blob for k in ("尿频", "尿急", "尿痛", "血尿", "排尿"))
    joint = any(
        k in blob
        for k in (
            "膝关节", "腰痛", "颈椎", "肩膀", "扭伤", "骨折", "关节痛",
            "膝盖", "扭到", "崴", "脚踝", "韧带", "半月板",
        )
    )
    gyn_sym = bool(
        re.search(r"月经|例假|经期|大姨妈|痛经|白带|闭经|经量", blob)
        and not any(k in blob for k in ("腹泻", "拉肚子", "水样便"))
    )
    skin = any(k in blob for k in ("皮疹", "瘙痒", "荨麻疹", "湿疹", "皮肤"))
    ent = any(k in blob for k in ("鼻塞", "流鼻涕", "耳鸣", "听力", "嗓子痛", "咽喉"))
    bp = any(k in blob for k in ("血压", "高血压"))

    if fever and cough:
        departments.append(_dept("resp", "发热伴咳嗽，优先呼吸内科评估感染", 1))
        departments.append(_dept("gp", "症状轻时可先全科初诊与分诊", 2))
        urgency = "urgent" if fever else "routine"
        suggest_online = not fever or "高热" not in blob
        next_steps = ["监测体温与呼吸情况", "多饮水休息；持续高热或气促请急诊", "可预约呼吸内科或全科"]
    elif gyn_sym:
        departments.append(_dept("gyn", "月经/经期相关异常，建议妇科评估", 1))
        departments.append(_dept("gp", "可先全科初诊", 2))
        next_steps = ["记录末次月经与周期变化", "可预约妇科；有性生活者可先自测是否怀孕", "大量出血或剧烈腹痛请急诊"]
    elif abd:
        departments.append(_dept("gi", "腹痛/消化道症状，建议消化内科", 1))
        if any(k in blob for k in ("右下腹", "转移性", "剧痛")):
            urgency = "urgent"
            departments.insert(0, _dept("er", "急性腹痛需警惕急腹症，建议尽快面诊", 1))
            departments = departments[:3]
            suggest_online = False
            next_steps = ["避免自行强止痛掩盖病情", "尽快门诊或急诊评估", "记录疼痛部位与伴随症状"]
        else:
            next_steps = ["记录进食与症状关系", "可预约消化内科", "出现黑便、呕血或剧痛请急诊"]
    elif urine:
        if gender and ("女" in gender or gender.lower() in ("f", "female")):
            departments.append(_dept("uro", "尿路刺激症状，泌尿外科常见", 1))
            departments.append(_dept("gyn", "女性需鉴别妇科相关刺激症状", 2))
        else:
            departments.append(_dept("uro", "尿路刺激症状，建议泌尿外科", 1))
            departments.append(_dept("gp", "症状轻时可先全科评估", 2))
        urgency = "urgent" if any(k in blob for k in ("发热", "腰痛", "血尿")) else "routine"
        next_steps = ["多饮水", "避免憋尿", "可预约泌尿外科；伴发热腰痛请尽快面诊"]
    elif dizzy or (headache and bp):
        departments.append(_dept("neuro", "头晕/头痛需神经内科评估", 1))
        departments.append(_dept("cardio", "伴血压异常时需心内科协同", 2))
        urgency = "urgent" if age and age >= 60 else "routine"
        suggest_online = urgency == "routine"
        next_steps = ["测量血压并记录", "避免突然改变体位", "可预约神经内科或心内科"]
    elif headache:
        departments.append(_dept("neuro", "头痛建议神经内科评估", 1))
        departments.append(_dept("gp", "常见头痛可先全科初诊", 2))
        next_steps = ["记录头痛诱因与频率", "剧烈突发头痛请急诊", "可预约神经内科"]
    elif joint:
        departments.append(_dept("ortho", "骨关节/脊柱相关不适，建议骨科", 1))
        departments.append(_dept("gp", "轻症可先全科评估与康复指导", 2))
        next_steps = ["制动休息，避免负重", "可预约骨科", "外伤后畸形/不能负重请急诊"]
    elif skin:
        departments.append(_dept("derm", "皮肤症状建议皮肤科", 1))
        departments.append(_dept("gp", "轻症可先全科处理", 2))
        next_steps = ["避免搔抓与自行激素滥用", "可预约皮肤科"]
        suggest_online = True
    elif ent:
        departments.append(_dept("ent", "耳鼻喉相关症状，建议耳鼻喉科", 1))
        departments.append(_dept("gp", "轻症可先全科", 2))
        next_steps = ["保持鼻腔湿润，避免自行挖耳", "可预约耳鼻喉科"]
    elif cough:
        departments.append(_dept("resp", "咳嗽为主，建议呼吸内科", 1))
        departments.append(_dept("gp", "可先全科初诊", 2))
        next_steps = ["观察痰色与气促", "可预约呼吸内科或全科"]
    elif chest:
        departments.append(_dept("cardio", "胸部不适建议心内科评估", 1))
        departments.append(_dept("gp", "症状轻且短暂可先全科", 2))
        urgency = "urgent"
        suggest_online = False
        next_steps = ["出现压榨样胸痛或气促请急诊", "可尽快预约心内科", "记录发作诱因与时长"]
    else:
        departments.append(_dept("gp", "依据现有描述，建议先全科医学初诊分诊", 1))
        if body_part and any(k in body_part for k in ("腹", "胃")):
            departments.append(_dept("gi", "部位提示腹部，可同步考虑消化内科", 2))
        next_steps = ["补充症状细节后可再导诊", "可预约全科或对症专科", "急危症状请立即急诊"]

    if sev in ("moderate", "中", "中等") and urgency == "routine":
        urgency = "urgent"
        suggest_online = False

    departments = departments[:3]
    for i, d in enumerate(departments, 1):
        d["rank"] = i

    if not next_steps:
        next_steps = ["查看推荐科室与号源", "可进入智能问诊补充信息", "急危重症请急诊"]

    return _enrich_structured(
        {
            "departments": departments,
            "urgency": urgency,
            "suggestOnline": suggest_online and urgency != "emergency",
            "nextSteps": next_steps,
            "disclaimer": DISCLAIMER,
            "source": "mock",
            "summary": f"根据主诉「{chief or '未填写'}」等，推荐相关科室（规则 Mock）。",
        },
        chief=chief,
        blob=blob,
        accompanying=accompanying,
    )


def _infer_facts_from_text(facts: dict[str, Any], content: str) -> None:
    """Fill missing slots from free text without overwriting known values."""
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
    for item in _extract_accompanying(content):
        if item not in acc:
            acc.append(item)
    # Explicit negation of red flags counts as answered
    if re.search(r"(没有|无|否认|不伴).{0,6}(胸痛|呼吸困难|大汗|意识)", content):
        facts["redFlags"] = "否认急危症状"
    elif _has_emergency_signal(content):
        facts["redFlags"] = "存在警示症状"
    if acc:
        facts["accompanying"] = acc
    if acc or "伴随" in content or "还有" in content:
        facts.setdefault("accompanyingAsked", True)


def _missing_slots(facts: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not facts.get("bodyPart"):
        missing.append("bodyPart")
    if not facts.get("duration"):
        missing.append("duration")
    if not facts.get("accompanying") and not facts.get("accompanyingAsked"):
        missing.append("accompanying")
    if not facts.get("redFlags"):
        missing.append("redFlags")
    if not facts.get("severity"):
        missing.append("severity")
    return missing


def _enough_for_summary(facts: dict[str, Any]) -> bool:
    """Chief + (body or duration) + (severity or accompanying or redFlags answered)."""
    if not facts.get("chief"):
        return False
    if not (facts.get("bodyPart") or facts.get("duration")):
        return False
    return bool(
        facts.get("severity")
        or facts.get("accompanying")
        or facts.get("redFlags")
        or facts.get("accompanyingAsked")
    )


def consult_reply(session: dict[str, Any], user_content: str) -> dict[str, Any]:
    """
    Multi-turn mock: ask only missing slots (no repeats), then complete with structured triage.
    Mutates session in place. Does not append to session['messages'].
    """
    content = (user_content or "").strip()
    facts: dict[str, Any] = session.setdefault("facts", {})
    asked: list[str] = list(facts.get("askedSlots") or [])
    turns = int(session.get("turns") or 0) + 1
    session["turns"] = turns

    history_text = facts.get("blob", "")
    facts["blob"] = (history_text + " " + content).strip()

    if turns == 1 or not facts.get("chief"):
        facts["chief"] = content[:80]
    elif symptom_shifted(facts, content):
        # Latest complaint replaces the frozen first-turn chief used for triage.
        facts["chief"] = content[:80]
        for stale in ("bodyPart", "duration", "severity"):
            facts.pop(stale, None)
        facts["extra"] = content[:200]
    else:
        facts["extra"] = ((facts.get("extra") or "") + " " + content).strip()

    _infer_facts_from_text(facts, content)

    early_blob = str(facts.get("blob") or "")
    emergency_early = _has_emergency_signal(early_blob)

    # Complete: emergency after ≥1 turn with enough context, or enough slots, or turn≥4
    should_complete = (
        (emergency_early and turns >= 1 and (facts.get("chief") and (turns >= 2 or len(content) > 8)))
        or (turns >= 2 and _enough_for_summary(facts))
        or turns >= 4
    )
    # On first turn alone with emergency keywords still ask one safety Q unless message is rich
    if turns == 1 and emergency_early and not (
        facts.get("duration") or facts.get("severity") or "大汗" in early_blob
    ):
        should_complete = False
    if turns == 1 and emergency_early and ("大汗" in early_blob or "呼吸困难" in early_blob):
        should_complete = True

    if should_complete:
        triage = recommend(
            chief=str(facts.get("chief") or content),
            duration=str(facts.get("duration") or ""),
            body_part=str(facts.get("bodyPart") or ""),
            severity=facts.get("severity"),
            age=facts.get("age"),
            gender=facts.get("gender"),
            extra=str(facts.get("extra") or facts.get("blob") or ""),
        )
        if emergency_early:
            triage["urgency"] = "emergency"
            triage["suggestOnline"] = False
        session["status"] = "completed"
        session["triage"] = triage
        depts = "、".join(d["name"] for d in triage["departments"])
        acc = triage.get("accompanying") or []
        acc_txt = "、".join(acc) if acc else "无明显记录"
        reply = (
            f"已根据您描述做了初步导诊小结：\n"
            f"- 主诉：{triage.get('chiefComplaint') or facts.get('chief')}\n"
            f"- 伴随：{acc_txt}\n"
            f"- 紧急程度：{triage['urgency']}\n"
            f"- 建议科室：{depts}\n"
            f"- 下一步：{'；'.join(triage['nextSteps'][:2])}\n\n"
            f"{DISCLAIMER}"
        )
        return {
            "reply": reply,
            "status": "completed",
            "triage": triage,
            "source": "mock",
            "disclaimer": DISCLAIMER,
        }

    # Ask next unasked missing slot only
    missing = [s for s in _missing_slots(facts) if s not in asked]
    if not missing:
        # Nothing left to ask → complete next path; ask soft wrap-up once
        if "wrapup" not in asked:
            asked.append("wrapup")
            facts["askedSlots"] = asked
            return {
                "reply": "谢谢补充。还有其他想说明的吗？没有的话我可以给出导诊建议。",
                "status": "active",
                "triage": None,
                "source": "mock",
                "disclaimer": DISCLAIMER,
            }
        # Force complete
        triage = recommend(
            chief=str(facts.get("chief") or content),
            duration=str(facts.get("duration") or ""),
            body_part=str(facts.get("bodyPart") or ""),
            severity=facts.get("severity"),
            age=facts.get("age"),
            gender=facts.get("gender"),
            extra=str(facts.get("extra") or facts.get("blob") or ""),
        )
        session["status"] = "completed"
        session["triage"] = triage
        depts = "、".join(d["name"] for d in triage["departments"])
        reply = (
            f"已根据您描述做了初步导诊小结：\n"
            f"- 主诉：{triage.get('chiefComplaint')}\n"
            f"- 紧急程度：{triage['urgency']}\n"
            f"- 建议科室：{depts}\n\n{DISCLAIMER}"
        )
        return {
            "reply": reply,
            "status": "completed",
            "triage": triage,
            "source": "mock",
            "disclaimer": DISCLAIMER,
        }

    slot = missing[0]
    q_map = dict(_SLOT_QUESTIONS)
    question = q_map.get(slot, "还有其他补充吗？")
    asked.append(slot)
    facts["askedSlots"] = asked
    if slot == "accompanying":
        facts["accompanyingAsked"] = True

    snippet = content[:48] + ("…" if len(content) > 48 else "")
    reply = f"收到您刚说的「{snippet}」。{question}"

    return {
        "reply": reply,
        "status": "active",
        "triage": None,
        "source": "mock",
        "disclaimer": DISCLAIMER,
    }


# ---------- Previsit report (doctor-facing) ----------
PREVISIT_DISCLAIMER = (
    "本预问诊报告由 AI 根据患者自述自动生成，仅供接诊医生参考，不构成诊断或治疗建议，"
    "不能替代面诊与病历书写。急危重症请立即急诊或拨打急救电话。"
)

REPORT_INTERPRET_DISCLAIMER = (
    "【重要】本解读由 AI 根据报告文本生成，仅供健康科普与就医参考，"
    "不是诊断、不是医学证明，不能替代执业医师面诊与正式报告解读。"
    "请勿据此自行用药或延误就医。异常指标请尽快咨询开单医生或相关专科；"
    "如有胸痛、呼吸困难、大出血、意识障碍等急危症状，请立即急诊或拨打 120。"
)


def build_previsit_report(
    *,
    chief: str = "",
    duration: str = "",
    body_part: str = "",
    accompanying: Optional[list[str]] = None,
    past_history: str = "",
    allergies: str = "",
    medications: str = "",
    patient_notes: str = "",
    urgency: Optional[str] = None,
    departments: Optional[list[dict[str, Any]]] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    extra: str = "",
    user_messages: Optional[list[str]] = None,
    triage: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Rule-based doctor-facing previsit summary."""
    triage = triage or {}
    chief = (chief or triage.get("chiefComplaint") or "").strip()
    blob = " ".join(
        x
        for x in [
            chief,
            duration,
            body_part,
            extra,
            patient_notes,
            " ".join(user_messages or []),
        ]
        if x
    )
    acc = list(accompanying or triage.get("accompanying") or _extract_accompanying(blob))
    seen: set[str] = set()
    deduped: list[str] = []
    for x in acc:
        if x and x not in seen:
            seen.add(x)
            deduped.append(x)
    acc = deduped

    if not departments:
        departments = list(triage.get("departments") or [])
    if not departments:
        rec = recommend(
            chief=chief or blob[:40],
            duration=duration,
            body_part=body_part,
            age=age,
            gender=gender,
            extra=extra or patient_notes,
        )
        departments = rec.get("departments") or []
        if not urgency:
            urgency = rec.get("urgency")

    urg = (urgency or triage.get("urgency") or "routine").strip().lower()
    if urg not in ("emergency", "urgent", "routine"):
        urg = "routine"
    if _has_emergency_signal(blob):
        urg = "emergency"

    red_flags: list[str] = []
    for kw in ("胸痛", "呼吸困难", "大汗", "意识不清", "大出血", "呕血", "剧烈头痛", "一侧肢体无力"):
        if kw in _strip_negated_emergency(blob):
            red_flags.append(kw)

    present_parts: list[str] = []
    if chief:
        present_parts.append(f"患者主诉「{chief}」")
    if duration:
        present_parts.append(f"病程约 {duration}")
    if body_part:
        present_parts.append(f"部位：{body_part}")
    if acc:
        present_parts.append("伴随：" + "、".join(acc))
    if extra:
        present_parts.append(f"补充：{extra[:120]}")
    present_illness = "；".join(present_parts) or "现病史信息不足，建议接诊时补充。"

    hist_bits = []
    if past_history:
        hist_bits.append(f"既往：{past_history}")
    if allergies:
        hist_bits.append(f"过敏：{allergies}")
    if medications:
        hist_bits.append(f"用药：{medications}")
    relevant_history = "；".join(hist_bits) or "未提供明确既往/过敏/用药信息。"

    narrative = ""
    if user_messages:
        narrative = " / ".join(m.strip() for m in user_messages if m.strip())[:400]
    elif patient_notes:
        narrative = patient_notes[:400]
    else:
        narrative = blob[:400] or chief

    doctor_hints = [
        "接诊时核对主诉、病程与伴随症状，完善体格检查",
        "核对过敏史与正在使用的药物",
    ]
    if urg == "emergency":
        doctor_hints.insert(0, "存在急危警示描述：请优先按急诊流程评估生命体征")
    if red_flags:
        doctor_hints.append("关注警示症状：" + "、".join(red_flags))

    dept_names = "、".join(d.get("name", "") for d in departments[:3] if d.get("name"))
    summary_text = (
        f"【预问诊摘要】主诉：{chief or '未明确'}；紧急程度：{urg}；"
        f"建议科室：{dept_names or '待分诊'}。"
        f"现病史要点：{present_illness}"
    )

    return {
        "chiefComplaint": chief or (blob[:80] if blob else "未明确"),
        "presentIllness": present_illness,
        "accompanying": acc[:12],
        "relevantHistory": relevant_history,
        "urgency": urg,
        "suggestedDepartments": departments[:3],
        "patientNarrative": narrative,
        "redFlags": red_flags,
        "doctorHints": doctor_hints[:6],
        "summaryText": summary_text,
        "disclaimer": PREVISIT_DISCLAIMER,
        "source": "mock",
    }


def interpret_report(
    *,
    text: str,
    report_type: Optional[str] = None,
) -> dict[str, Any]:
    """Rule-based mock interpretation of lab/imaging report text."""
    raw = (text or "").strip()
    rtype = (report_type or "").strip().lower() or None
    if not rtype:
        if any(k in raw for k in ("CT", "MRI", "X线", "超声", "影像", "片见", "所见")):
            rtype = "imaging"
        elif any(k in raw for k in ("白细胞", "血红蛋白", "ALT", "AST", "血糖", "肌酐", "检验", "血常规")):
            rtype = "lab"
        else:
            rtype = "other"

    abnormalities: list[dict[str, str]] = []
    advice: list[str] = []
    plain_bits: list[str] = []

    def _add(item: str, finding: str, severity: str) -> None:
        abnormalities.append({"item": item, "finding": finding, "severity": severity})

    # --- CBC heuristics ---
    if re.search(r"白细胞|WBC", raw, re.I):
        m = re.search(r"(?:白细胞|WBC)[^\d]{0,8}(\d+\.?\d*)", raw, re.I)
        if m:
            v = float(m.group(1))
            # assume 10^9/L scale if value looks like CBC
            if v >= 100:  # likely absolute count in other unit; skip numeric
                pass
            elif v > 10:
                _add("白细胞(WBC)", f"约 {v}，偏高", "moderate")
                plain_bits.append(f"白细胞约 {v}，偏高，常见于感染或炎症等，需结合症状判断。")
            elif v < 3.5:
                _add("白细胞(WBC)", f"约 {v}，偏低", "moderate")
                plain_bits.append(f"白细胞约 {v}，偏低，需结合临床警惕感染风险或骨髓相关问题。")
            else:
                plain_bits.append(f"白细胞约 {v}，大致在常见参考范围内（规则粗判）。")

    if re.search(r"血红蛋白|Hb|HGB", raw, re.I):
        m = re.search(r"(?:血红蛋白|HGB|Hb)[^\d]{0,8}(\d+\.?\d*)", raw, re.I)
        if m:
            v = float(m.group(1))
            if 30 < v < 200:  # g/L
                if v < 110:
                    _add("血红蛋白", f"约 {v} g/L，偏低", "moderate" if v >= 90 else "high")
                    plain_bits.append(f"血红蛋白约 {v} g/L，偏低，可能提示贫血，建议专科评估原因。")
                elif v > 175:
                    _add("血红蛋白", f"约 {v} g/L，偏高", "low")
                    plain_bits.append(f"血红蛋白约 {v} g/L，偏高，需结合红细胞压积等综合判断。")
                else:
                    plain_bits.append(f"血红蛋白约 {v} g/L，粗看大致正常。")

    if re.search(r"血小板|PLT", raw, re.I):
        m = re.search(r"(?:血小板|PLT)[^\d]{0,8}(\d+\.?\d*)", raw, re.I)
        if m:
            v = float(m.group(1))
            if v < 100:
                _add("血小板(PLT)", f"约 {v}，偏低", "high" if v < 50 else "moderate")
                plain_bits.append(f"血小板约 {v}，偏低，出血风险可能升高，请尽快就医复核。")
            elif v > 450:
                _add("血小板(PLT)", f"约 {v}，偏高", "moderate")
                plain_bits.append(f"血小板约 {v}，偏高，需结合炎症或其他血液指标。")

    # --- Liver ---
    for label, keys, hi in (
        ("ALT", ("ALT", "谷丙", "丙氨酸"), 40),
        ("AST", ("AST", "谷草", "天门冬"), 40),
    ):
        if any(k in raw for k in keys):
            m = re.search(rf"(?:{'|'.join(map(re.escape, keys))})[^\d]{{0,10}}(\d+\.?\d*)", raw, re.I)
            if m:
                v = float(m.group(1))
                if v > hi * 3:
                    _add(label, f"约 {v}，明显升高", "high")
                    plain_bits.append(f"{label} 约 {v}，明显升高，提示肝细胞损伤可能，请尽快面诊。")
                elif v > hi:
                    _add(label, f"约 {v}，轻度升高", "moderate")
                    plain_bits.append(f"{label} 约 {v}，轻度升高，常见于脂肪肝、药物或轻度肝损伤等，需医生结合判断。")
                else:
                    plain_bits.append(f"{label} 约 {v}，粗看大致正常。")

    # --- Imaging keywords ---
    if rtype == "imaging" or any(k in raw for k in ("结节", "占位", "积液", "骨折", "炎症", "渗出")):
        if "未见明显异常" in raw or "未见异常" in raw:
            plain_bits.append("影像描述未见明显异常（以正式报告为准）。")
        if "结节" in raw:
            _add("影像所见", "提到结节", "moderate")
            plain_bits.append("报告提到结节，需结合大小、形态与随访建议，由影像科/临床医生解读。")
        if "积液" in raw:
            _add("影像所见", "提到积液", "moderate")
            plain_bits.append("报告提到积液，请尽快由临床医生评估原因与处理。")
        if "骨折" in raw:
            _add("影像所见", "提到骨折", "high")
            plain_bits.append("报告提示骨折相关描述，请骨科或急诊进一步处理。")
        if any(k in raw for k in ("炎症", "渗出", "感染")):
            _add("影像所见", "提示炎症/渗出可能", "moderate")
            plain_bits.append("影像提示炎症或渗出可能，需结合症状与化验综合判断。")

    if not plain_bits:
        plain_bits.append(
            "已收到报告文本。规则引擎未能精确拆解全部指标，建议将完整报告交给开单医生解读。"
        )
        if len(raw) > 20:
            plain_bits.append(f"报告原文摘录：{raw[:160]}{'…' if len(raw) > 160 else ''}")

    if abnormalities:
        advice.append("对标记为偏高/偏低的项目，请携带完整报告尽快复诊或咨询开单医生")
        if any(a["severity"] == "high" for a in abnormalities):
            advice.append("存在较明显异常提示，勿自行用药，必要时急诊评估")
    else:
        advice.append("暂未识别出明确数值异常，仍建议由医生结合临床表现确认")

    advice.extend(
        [
            "本解读不能替代正式检验/影像报告与医生诊断",
            "急危症状（胸痛、呼吸困难、大出血、意识障碍等）请立即急诊或拨打 120",
        ]
    )

    interpretation = " ".join(plain_bits)
    if rtype == "lab":
        interpretation = "【检验报告通俗解读】" + interpretation
    elif rtype == "imaging":
        interpretation = "【影像报告通俗解读】" + interpretation
    else:
        interpretation = "【报告通俗解读】" + interpretation

    return {
        "interpretation": interpretation,
        "abnormalities": abnormalities,
        "advice": advice[:8],
        "disclaimer": REPORT_INTERPRET_DISCLAIMER,
        "reportType": rtype,
        "source": "mock",
    }
