"""Keyword-rule mock AI ported from medical-assistant-prototype/index.html."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")

DISCLAIMER = "辅助决策，不替代执业医师。AI 结果仅供参考，须医生确认。"

DX_SETS: dict[str, list[dict[str, str]]] = {
    "stomach": [
        {"name": "慢性胃炎急性发作", "reason": "餐后上腹痛、反酸烧心，既往胃炎史，体征局限", "prob": "较高"},
        {"name": "消化性溃疡", "reason": "反复上腹痛伴反酸，需排除溃疡活动或并发症", "prob": "中等"},
        {"name": "胃食管反流病（GERD）", "reason": "反酸烧心突出，餐后症状加重", "prob": "中等"},
        {"name": "胆道疾病（胆囊炎/胆石症）", "reason": "上腹痛需鉴别胆系来源，目前 Murphy 阴性降低可能", "prob": "较低"},
        {"name": "功能性消化不良", "reason": "症状轻、无报警征象时需考虑，但需先排除器质性疾病", "prob": "较低"},
    ],
    "cough": [
        {"name": "急性支气管炎", "reason": "咳嗽伴发热，常见病毒/细菌感染后气道炎症", "prob": "较高"},
        {"name": "社区获得性肺炎", "reason": "发热+咳嗽需排除肺部感染，建议影像评估", "prob": "中等"},
        {"name": "上呼吸道感染", "reason": "病程短，若以咽痛/流涕为主更支持", "prob": "中等"},
        {"name": "哮喘急性发作/变异性哮喘", "reason": "若有喘息、夜间加重或过敏体质需考虑", "prob": "较低"},
    ],
    "dizzy": [
        {"name": "原发性高血压（血压控制不佳）", "reason": "头晕伴血压升高，老年常见", "prob": "较高"},
        {"name": "后循环缺血/短暂性脑缺血发作", "reason": "老年头晕需警惕血管事件，注意局灶神经体征", "prob": "中等"},
        {"name": "颈椎病相关眩晕", "reason": "若与体位/转颈相关可考虑", "prob": "中等"},
        {"name": "药物相关低血压/副作用", "reason": "若近期调整降压药需排查", "prob": "较低"},
    ],
    "urine": [
        {"name": "急性膀胱炎", "reason": "尿频尿急，年轻女性多见，多为下尿路感染", "prob": "较高"},
        {"name": "急性肾盂肾炎", "reason": "若伴发热、腰痛、肾区叩痛则需上调可能", "prob": "中等"},
        {"name": "尿道炎", "reason": "尿路刺激征，需结合性生活史与病原学", "prob": "较低"},
        {"name": "阴道炎相关刺激症状", "reason": "女性需鉴别妇科炎症引起的尿道刺激", "prob": "较低"},
    ],
    "cardio": [
        {"name": "冠心病心绞痛", "reason": "胸闷/上腹不适需警惕心源性缺血，专科优先排查", "prob": "较高"},
        {"name": "急性冠脉综合征（需急诊评估）", "reason": "若症状新发、静息发作或伴大汗气促，须紧急评估", "prob": "中等"},
        {"name": "心律失常相关胸闷", "reason": "阵发心悸、脉律不齐时可考虑，需心电图证实", "prob": "中等"},
        {"name": "反流相关非心源性胸痛", "reason": "心内科鉴别中仍需排除胃食管反流等非心源因素", "prob": "较低"},
        {"name": "高血压急症/血压波动相关不适", "reason": "合并血压显著升高时需评估靶器官损害", "prob": "较低"},
    ],
    "default": [
        {"name": "待进一步评估的常见病", "reason": "依据现有主诉与体征的初步鉴别，建议完善问诊与检查", "prob": "中等"},
        {"name": "感染相关疾病", "reason": "若存在发热、局部炎症征象需优先排查", "prob": "中等"},
        {"name": "慢性病急性加重", "reason": "结合既往史评估基础疾病波动可能", "prob": "中等"},
        {"name": "功能性疾病", "reason": "排除器质性疾病后可考虑，目前证据不足", "prob": "较低"},
    ],
}

SUGGEST_MAP: dict[str, dict[str, list[str]]] = {
    "慢性胃炎急性发作": {
        "exams": ["胃镜检查（择期）", "幽门螺杆菌检测（呼气试验/抗原）", "血常规", "肝功能"],
        "drugs": ["奥美拉唑肠溶胶囊 20mg qd", "铝碳酸镁咀嚼片 1g tid", "枸橼酸莫沙必利片 5mg tid"],
    },
    "消化性溃疡": {
        "exams": ["胃镜检查", "粪便隐血试验", "血常规", "幽门螺杆菌检测"],
        "drugs": ["艾司奥美拉唑镁肠溶片 20mg qd", "铝碳酸镁咀嚼片 1g tid", "如 Hp 阳性：标准四联方案（需确认）"],
    },
    "胃食管反流病（GERD）": {
        "exams": ["胃镜检查（如有报警症状）", "必要时食管 pH/阻抗监测（择期）"],
        "drugs": ["雷贝拉唑钠肠溶片 10mg qd", "多潘立酮片 10mg tid"],
    },
    "胆道疾病（胆囊炎/胆石症）": {
        "exams": ["腹部超声（肝胆胰脾）", "血常规", "肝功能 + 胆红素"],
        "drugs": ["对症解痉止痛（评估后）", "必要时抗感染（有炎症证据时）"],
    },
    "功能性消化不良": {
        "exams": ["必要时胃镜排查器质性疾病", "幽门螺杆菌检测"],
        "drugs": ["枸橼酸莫沙必利片 5mg tid", "复方消化酶胶囊 1粒 tid"],
    },
    "急性支气管炎": {
        "exams": ["血常规", "C 反应蛋白", "胸部 X 线（必要时）"],
        "drugs": ["止咳化痰：氨溴索片 30mg tid", "如细菌感染证据：阿莫西林胶囊 0.5g tid"],
    },
    "社区获得性肺炎": {
        "exams": ["胸部 CT 或胸部 X 线", "血常规 + CRP", "痰培养（必要时）"],
        "drugs": ["经验性抗感染：阿莫西林克拉维酸钾（需评估过敏）", "对症退热、止咳"],
    },
    "上呼吸道感染": {
        "exams": ["血常规（必要时）"],
        "drugs": ["对症：复方感冒制剂", "多饮水、休息"],
    },
    "哮喘急性发作/变异性哮喘": {
        "exams": ["肺功能（缓解期）", "血常规嗜酸粒细胞", "过敏原筛查（择期）"],
        "drugs": ["吸入用布地奈德混悬液（雾化）", "沙丁胺醇气雾剂（按需）"],
    },
    "原发性高血压（血压控制不佳）": {
        "exams": ["动态血压监测", "血电解质、肾功能", "心电图", "尿常规"],
        "drugs": ["评估后调整降压方案（如氨氯地平 5mg qd）", "生活方式指导"],
    },
    "后循环缺血/短暂性脑缺血发作": {
        "exams": ["头颅 MRI + MRA / CTA", "颈部血管超声", "血脂、血糖、心电图"],
        "drugs": ["抗血小板：阿司匹林肠溶片 100mg qd（排除禁忌后）", "调脂：阿托伐他汀钙片 20mg qn"],
    },
    "颈椎病相关眩晕": {
        "exams": ["颈椎 X 线 / MRI", "必要时前庭功能评估"],
        "drugs": ["非甾体抗炎（短期）", "颈椎制动与康复指导"],
    },
    "药物相关低血压/副作用": {
        "exams": ["复查血压、心率", "血电解质"],
        "drugs": ["评估并调整相关药物剂量（医生确认）"],
    },
    "急性膀胱炎": {
        "exams": ["尿常规", "尿培养（必要时）"],
        "drugs": ["左氧氟沙星片 0.5g qd（注意禁忌）", "多饮水"],
    },
    "急性肾盂肾炎": {
        "exams": ["尿常规 + 尿培养", "血常规", "肾功能", "泌尿系超声"],
        "drugs": ["经验性抗感染（静脉/口服，据病情）", "退热对症"],
    },
    "尿道炎": {
        "exams": ["尿常规", "病原体核酸检测（必要时）"],
        "drugs": ["针对病原体抗感染（需确认）"],
    },
    "阴道炎相关刺激症状": {
        "exams": ["妇科检查", "阴道分泌物检查"],
        "drugs": ["局部抗真菌/抗滴虫等（据病原）"],
    },
    "冠心病心绞痛": {
        "exams": ["心电图", "心肌酶/肌钙蛋白", "血脂血糖", "必要时冠脉 CT / 运动平板（评估后）"],
        "drugs": ["阿司匹林肠溶片 100mg qd（排除禁忌后）", "单硝酸异山梨酯缓释片 40mg qd", "阿托伐他汀钙片 20mg qn"],
    },
    "急性冠脉综合征（需急诊评估）": {
        "exams": ["急诊心电图", "肌钙蛋白动态监测", "血常规、肾功能、凝血", "心内科急会诊"],
        "drugs": ["按胸痛流程处理（须医生确认）", "阿司匹林负荷（排除禁忌后，医生确认）"],
    },
    "心律失常相关胸闷": {
        "exams": ["心电图", "24 小时动态心电图", "甲状腺功能（必要时）", "心脏超声（必要时）"],
        "drugs": ["对症与抗心律失常方案（据心电图，须医生确认）"],
    },
    "反流相关非心源性胸痛": {
        "exams": ["先完善心电图排除心源性", "必要时消化科协作：胃镜/抑酸试验"],
        "drugs": ["抑酸：奥美拉唑肠溶胶囊 20mg qd（心源排除后）"],
    },
    "高血压急症/血压波动相关不适": {
        "exams": ["复查血压、心电图", "血电解质、肾功能", "眼底/靶器官评估（必要时）"],
        "drugs": ["评估后调整降压方案（医生确认）"],
    },
}

DEFAULT_SUGGEST = {
    "exams": ["血常规", "相关影像或专科检查（据主诉）", "基础生化（必要时）"],
    "drugs": ["对症支持治疗（需医生确认具体方案）"],
}

ALLERGY_RULES = [
    {
        "allergy": ["青霉素", "阿莫西林", "氨苄", "β-内酰胺", "头孢"],
        "drug": ["青霉素", "阿莫西林", "氨苄", "头孢", "克拉维酸"],
    },
    {"allergy": ["磺胺"], "drug": ["磺胺", "复方新诺明", "SMZ"]},
    {"allergy": ["阿司匹林", "水杨酸"], "drug": ["阿司匹林"]},
    {
        "allergy": ["喹诺酮", "左氧氟", "氧氟沙星"],
        "drug": ["左氧氟", "氧氟沙星", "莫西沙星", "环丙沙星"],
    },
]



# Specialty → mock differential set key（与模板 specialty 文案对齐）
SPECIALTY_SET_MAP: dict[str, str] = {
    # template codes (M11 templates_data)
    "gi": "stomach",
    "resp": "cough",
    "cardio": "cardio",
    "general": "",  # empty → keyword detect
    # Chinese labels (visit/UI may set either)
    "消化": "stomach",
    "消化内科": "stomach",
    "呼吸": "cough",
    "呼吸内科": "cough",
    "心内": "cardio",
    "心内科": "cardio",
    "心血管内科": "cardio",
    "全科": "",
}

SPECIALTY_DEFAULT_SUGGEST: dict[str, dict[str, list[str]]] = {
    "stomach": {
        "exams": ["胃镜检查（择期）", "幽门螺杆菌检测", "血常规", "肝功能"],
        "drugs": ["质子泵抑制剂（如奥美拉唑 20mg qd）", "胃黏膜保护剂（医生确认）"],
    },
    "cough": {
        "exams": ["血常规 + CRP", "胸部 X 线或 CT（必要时）"],
        "drugs": ["止咳化痰对症（医生确认）", "必要时抗感染（有细菌感染证据时）"],
    },
    "cardio": {
        "exams": ["心电图", "心肌酶/肌钙蛋白", "血脂", "必要时心脏超声"],
        "drugs": ["抗血小板/调脂等方案须医生按指南确认"],
    },
    "dizzy": {
        "exams": ["血压监测", "心电图", "血电解质、肾功能"],
        "drugs": ["评估后调整降压或对症方案（医生确认）"],
    },
    "urine": {
        "exams": ["尿常规", "尿培养（必要时）"],
        "drugs": ["经验性抗感染（须医生确认）", "多饮水"],
    },
}


def normalize_specialty(specialty: str) -> str:
    s = (specialty or "").strip()
    if not s:
        return ""
    # exact key (case-insensitive for latin codes)
    lower_map = {k.lower(): k for k in SPECIALTY_SET_MAP}
    if s in SPECIALTY_SET_MAP:
        return s
    if s.lower() in lower_map:
        return lower_map[s.lower()]
    # longest alias contains / contained
    aliases = sorted(SPECIALTY_SET_MAP.keys(), key=len, reverse=True)
    for a in aliases:
        if a == s or a in s or s in a:
            return a
    return s


def specialty_set_key(specialty: str) -> str:
    """Map visit/template specialty to DX_SETS key; empty if unknown."""
    norm = normalize_specialty(specialty)
    if not norm:
        return ""
    key = SPECIALTY_SET_MAP.get(norm, "")
    return key or ""


def detect_set(text: str) -> str:
    t = text or ""
    if re.search(r"腹痛|反酸|烧心|胃炎|胃|消化|上腹", t):
        return "stomach"
    if re.search(r"咳嗽|发热|咳痰|咽痛|呼吸道|肺炎", t):
        return "cough"
    if re.search(r"头晕|眩晕|血压|高血压", t):
        return "dizzy"
    if re.search(r"尿频|尿急|尿痛|膀胱|尿路", t):
        return "urine"
    return "default"


def collect_record_text(visit: dict[str, Any]) -> str:
    return " ".join(
        [
            visit.get("chief") or "",
            visit.get("hpi") or "",
            visit.get("pmh") or "",
            visit.get("allergy") or "",
            visit.get("pe") or "",
            visit.get("labs") or "",
            visit.get("rawText") or "",
        ]
    )


def has_allergy_conflict(allergy: str, drug_text: str) -> Optional[str]:
    allergy = (allergy or "").strip()
    if not allergy or re.search(r"否认|无过敏|不详", allergy):
        return None
    for rule in ALLERGY_RULES:
        if not any(k in allergy for k in rule["allergy"]):
            continue
        if any(k in drug_text for k in rule["drug"]):
            return "与过敏史冲突：" + allergy.replace("\n", "；")
    return None


def parse_unstructured(raw: str) -> dict[str, str]:
    """Heuristic field extraction — mirrors frontend parseUnstructured."""
    text = (raw or "").strip()
    chief = hpi = pmh = allergy = pe = labs = ""

    chief_m = re.search(r"主诉[：:]\s*([^\n。]+)", text) or re.search(
        r"((?:反复|持续)?[\u4e00-\u9fa5]{2,12}?(?:痛|咳|热|晕|急|频|胀|闷)[\u4e00-\u9fa5]{0,8}\s*\d+\s*(?:天|日|周|月|年))",
        text,
    )
    if chief_m:
        chief = (chief_m.group(1) or chief_m.group(0)).replace("主诉：", "").replace("主诉:", "").strip()

    hpi_m = re.search(r"现病史[：:]\s*([\s\S]*?)(?=既往史|过敏史|查体|体格|$)", text)
    if hpi_m:
        hpi = hpi_m.group(1).strip()
    else:
        sentences = [s for s in re.split(r"[。；\n]", text) if s]
        hpi = "。".join(sentences[:4]) + ("。" if sentences else "")

    pmh_m = re.search(r"既往[史]?[：:]?\s*([^\n。]*(?:病史|手术)[^\n。]*)", text)
    if pmh_m:
        pmh = re.sub(r"^既往[史]?[：:]?\s*", "", pmh_m.group(0)).strip()
    elif "既往有" in text:
        m = re.search(r"既往有[「「]?([^」。]+)[」」]?", text)
        if m:
            pmh = m.group(0)
    if "否认手术" in text:
        pmh = (pmh + "；" if pmh else "") + "否认手术史"

    all_m = re.search(r"对(.{1,20}?)过敏|过敏史[：:]?\s*([^\n。]+)|否认药物过敏", text)
    if all_m:
        if "否认药物过敏" in text and "过敏（" not in text:
            allergy = "否认药物过敏"
        else:
            allergy = all_m.group(0).strip()

    pe_m = re.search(r"(?:查体|体格检查)[：:]\s*([\s\S]*?)(?=近期|辅助|拟诊|$)", text)
    if pe_m:
        pe = pe_m.group(1).strip()
    else:
        vitals = re.findall(r"T\s*[\d.]+℃[^。]*|腹软[^。]*|Murphy[^。]*", text)
        if vitals:
            pe = "。".join(vitals) + "。"

    if re.search(r"未做胃镜|胃镜", text):
        labs = "近期未行胃镜检查" if "未做胃镜" in text else ""
    lab_m = re.search(r"辅助检查[：:]\s*([^\n]+)", text)
    if lab_m:
        labs = lab_m.group(1).strip()

    if not chief and "腹痛" in text:
        chief = "反复上腹痛数天"
    if not chief:
        chief = text[:30] + ("…" if len(text) > 30 else "")

    return {
        "chief": chief,
        "hpi": hpi or text,
        "pmh": pmh or "未提供",
        "allergy": allergy or "未提供，需进一步询问",
        "pe": pe or "待补充",
        "labs": labs or "暂无",
    }


def resolve_dx_key(visit: dict[str, Any]) -> str:
    """Prefer specialty-mapped set; else keyword detect from chart text."""
    spec_key = specialty_set_key(visit.get("specialty") or "")
    if spec_key and spec_key in DX_SETS:
        return spec_key
    return detect_set(collect_record_text(visit))


def generate_differential(visit: dict[str, Any]) -> list[dict[str, Any]]:
    key = resolve_dx_key(visit)
    items = DX_SETS.get(key) or DX_SETS["default"]
    specialty_raw = normalize_specialty(visit.get("specialty") or "") or "全科"
    specialty_label = {
        "gi": "消化",
        "resp": "呼吸",
        "cardio": "心内",
        "general": "全科",
        "消化": "消化",
        "消化内科": "消化",
        "呼吸": "呼吸",
        "呼吸内科": "呼吸",
        "心内": "心内",
        "心内科": "心内",
        "心血管内科": "心内",
        "全科": "全科",
    }.get(specialty_raw, specialty_raw)
    # Return 3–5 items; annotate rationale lightly with specialty lens
    selected = items[: min(5, max(3, len(items)))]
    out = []
    for i, d in enumerate(selected):
        rationale = d["reason"]
        if specialty_label and specialty_label != "全科" and specialty_label not in rationale:
            rationale = f"【{specialty_label}】{rationale}"
        out.append(
            {
                "id": f"dx{i + 1}",
                "name": d["name"],
                "rationale": rationale,
                "rank": i + 1,
                "prob": d["prob"],
                "decision": "pending",
            }
        )
    return out


def suggest_orders(visit: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    adopted = [
        d
        for d in visit.get("differential") or []
        if d.get("decision") == "accept"
    ]
    exam_set: list[str] = []
    drug_set: list[str] = []
    seen_e: set[str] = set()
    seen_d: set[str] = set()

    sources = adopted if adopted else []
    if not sources:
        # Fall back to top differential, specialty default, or generic default
        diffs = visit.get("differential") or []
        if diffs:
            sources = [diffs[0]]
        else:
            spec_key = specialty_set_key(visit.get("specialty") or "") or resolve_dx_key(visit)
            s = SPECIALTY_DEFAULT_SUGGEST.get(spec_key) or DEFAULT_SUGGEST
            exams = [{"type": "检查", "text": e, "conflict": False, "warn": None} for e in s["exams"]]
            drugs = []
            allergy = visit.get("allergy") or ""
            for g in s["drugs"]:
                warn = has_allergy_conflict(allergy, g)
                drugs.append(
                    {
                        "type": "药品",
                        "text": g,
                        "conflict": bool(warn),
                        "warn": warn,
                    }
                )
            return {"exams": exams, "drugs": drugs}

    for d in sources:
        s = SUGGEST_MAP.get(d["name"], DEFAULT_SUGGEST)
        for e in s["exams"]:
            if e not in seen_e:
                seen_e.add(e)
                exam_set.append(e)
        for g in s["drugs"]:
            if g not in seen_d:
                seen_d.add(g)
                drug_set.append(g)

    allergy = visit.get("allergy") or ""
    exams = [{"type": "检查", "text": e, "conflict": False, "warn": None} for e in exam_set]
    drugs = []
    for g in drug_set:
        warn = has_allergy_conflict(allergy, g)
        drugs.append(
            {
                "type": "药品",
                "text": g,
                "conflict": bool(warn),
                "warn": warn,
            }
        )
    return {"exams": exams, "drugs": drugs}


def build_note(visit: dict[str, Any], style: str = "structured") -> str:
    name = visit.get("name") or ""
    gender = visit.get("gender") or ""
    age = visit.get("age") or ""
    chief = (visit.get("chief") or "").strip() or "（未填）"
    hpi = (visit.get("hpi") or "").strip() or "（未填）"
    pmh = (visit.get("pmh") or "").strip() or "（未填）"
    allergy = (visit.get("allergy") or "").strip() or "（未填）"
    pe = (visit.get("pe") or "").strip() or "（未填）"
    labs = (visit.get("labs") or "").strip() or "暂无"
    diffs = visit.get("differential") or []
    adopted = [d["name"] for d in diffs if d.get("decision") == "accept"]
    excluded = [d["name"] for d in diffs if d.get("decision") == "reject"]
    dx_line = "；".join(adopted) if adopted else "待定"
    orders = visit.get("orders") or []
    order_lines = (
        "\n".join(f"- 【{o['type']}】{o['text']}" for o in orders) if orders else "- （暂无）"
    )

    if style in ("concise", "simple"):
        excluded_line = f"已排除：{'、'.join(excluded)}\n" if excluded else ""
        return (
            f"【门诊病历 · 简洁版】\n"
            f"患者：{name}　{gender}　{age}岁\n"
            f"主诉：{chief}\n"
            f"现病史：{hpi.replace(chr(10), ' ')}\n"
            f"既往/过敏：{pmh} / {allergy}\n"
            f"查体：{pe.replace(chr(10), ' ')}\n"
            f"已有检查：{labs}\n"
            f"初步诊断：{dx_line}\n"
            f"{excluded_line}"
            f"处理：\n{order_lines}\n\n"
            f"※ 辅助决策生成，仅供参考，需医生确认。不替代执业医师。"
        )

    if style == "formal":
        date_str = datetime.now(TZ).strftime("%Y/%m/%d")
        excluded_line = f"　排除：{'；'.join(excluded)}\n" if excluded else ""
        return (
            f"门诊病历记录\n\n"
            f"基本信息\n"
            f"　姓名：{name}　　性别：{gender}　　年龄：{age}岁\n"
            f"　就诊日期：{date_str}\n\n"
            f"一、主诉\n　{chief}\n\n"
            f"二、现病史\n　{hpi}\n\n"
            f"三、既往史\n　{pmh}\n\n"
            f"四、过敏史\n　{allergy}\n\n"
            f"五、体格检查\n　{pe}\n\n"
            f"六、辅助检查\n　{labs}\n\n"
            f"七、初步诊断（鉴别）\n　采纳：{dx_line}\n"
            f"{excluded_line}\n"
            f"八、诊疗计划 / 医嘱草稿\n{order_lines}\n\n"
            f"【声明】本记录由 AI 辅助生成并经医生编辑，仅供参考，需医生确认。辅助决策，不替代执业医师。"
        )

    # structured default
    excluded_block = f"【已排除】\n{'；'.join(excluded)}\n" if excluded else ""
    return (
        f"门诊病历\n\n"
        f"患者：{name}　{gender}　{age}岁\n"
        f"就诊时间：{visit.get('time') or ''}\n\n"
        f"【主诉】\n{chief}\n\n"
        f"【现病史】\n{hpi}\n\n"
        f"【既往史】\n{pmh}\n\n"
        f"【过敏史】\n{allergy}\n\n"
        f"【体格检查】\n{pe}\n\n"
        f"【辅助检查】\n{labs}\n\n"
        f"【初步诊断】\n{dx_line}\n"
        f"{excluded_block}"
        f"【医嘱草稿】\n{order_lines}\n\n"
        f"——\n仅供参考，需医生确认 · 辅助决策，不替代执业医师"
    )


def note_sections(visit: dict[str, Any]) -> dict[str, Any]:
    diffs = visit.get("differential") or []
    adopted = [d["name"] for d in diffs if d.get("decision") == "accept"]
    excluded = [d["name"] for d in diffs if d.get("decision") == "reject"]
    return {
        "patient": f"{visit.get('name')}　{visit.get('gender')}　{visit.get('age')}岁",
        "time": visit.get("time") or "",
        "chief": visit.get("chief") or "",
        "hpi": visit.get("hpi") or "",
        "pmh": visit.get("pmh") or "",
        "allergy": visit.get("allergy") or "",
        "pe": visit.get("pe") or "",
        "labs": visit.get("labs") or "",
        "diagnosis": adopted,
        "excluded": excluded,
        "orders": visit.get("orders") or [],
    }


def polish_note(content: str, style: str, visit: Optional[dict[str, Any]] = None) -> str:
    """Polish: if content given, lightly reformat; else rebuild from visit."""
    if visit is not None and (not content or not content.strip()):
        return build_note(visit, style=style)
    text = (content or "").strip()
    if style in ("concise", "simple"):
        # Compress whitespace / blank lines
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        body = "\n".join(lines)
        footer = "\n\n※ 辅助决策生成，仅供参考，需医生确认。不替代执业医师。"
        if "仅供参考" not in body and "不替代" not in body:
            body += footer
        return f"【门诊病历 · 简洁版】\n{body}" if not body.startswith("【门诊病历") else body
    if style == "formal":
        if text.startswith("门诊病历记录"):
            return text
        return (
            f"门诊病历记录\n\n{text}\n\n"
            f"【声明】本记录由 AI 辅助润色，仅供参考，需医生确认。辅助决策，不替代执业医师。"
        )
    return text


def to_markdown(visit: dict[str, Any]) -> str:
    body = visit.get("note") or build_note(visit, style="structured")
    return (
        f"# 门诊病历导出\n\n"
        f"> 仅供参考，需医生确认 · 辅助决策，不替代执业医师\n\n"
        f"**患者**：{visit.get('name')}　{visit.get('gender')}　{visit.get('age')}岁  \n"
        f"**就诊时间**：{visit.get('time')}  \n"
        f"**状态**：{visit.get('status')}\n\n"
        f"```\n{body}\n```\n"
    )
