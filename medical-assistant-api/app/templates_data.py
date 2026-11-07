"""M11 specialty chart templates (Mock Chinese clinical placeholders)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "tpl-general",
        "specialty": "general",
        "name": "全科门诊模板",
        "fields": {
            "chief": "（主诉：症状 + 病程）",
            "hpi": "起病缓急、诱因、主要症状演变、伴随症状、诊治经过与用药反应。",
            "pmh": "既往慢性病史、手术外伤史、传染病史；系统回顾有无异常。",
            "allergy": "药物/食物过敏史：有 / 无；具体过敏原与反应。",
            "pe": "一般情况，生命体征，心肺腹查体要点，专科阳性体征。",
            "labs": "已有辅助检查结果摘要；拟完善检查。",
            "diagnosis": "",
            "assessment": "病情评估：急性/慢性；需鉴别及随访计划。",
        },
    },
    {
        "id": "tpl-gi",
        "specialty": "gi",
        "name": "消化内科模板",
        "fields": {
            "chief": "上腹痛 / 反酸烧心 / 腹泻 等（填写具体病程）",
            "hpi": "腹痛部位性质、与进食关系、反酸烧心、恶心呕吐、黑便/血便、体重变化；既往胃镜/幽门螺杆菌。",
            "pmh": "慢性胃炎、消化性溃疡、胆囊炎胆石症、肝炎病史；长期 NSAID / 激素使用。",
            "allergy": "药物过敏史（尤其抗生素、造影剂）。",
            "pe": "腹软/压痛部位，反跳痛肌紧张，Murphy 征，肠鸣音，黄疸有无。",
            "labs": "血常规、肝功、淀粉酶/脂肪酶、腹部超声/胃镜结果（如有）。",
            "diagnosis": "",
            "assessment": "消化道症状鉴别：溃疡病、功能性消化不良、胆胰疾病等；注意报警症状。",
        },
    },
    {
        "id": "tpl-resp",
        "specialty": "resp",
        "name": "呼吸内科模板",
        "fields": {
            "chief": "咳嗽 / 咳痰 / 发热 / 气促 等（填写具体病程）",
            "hpi": "咳嗽性质、痰色量、发热峰值与热型、胸痛咯血、呼吸困难；疫区/吸烟/过敏史。",
            "pmh": "哮喘、慢阻肺、肺结核、鼻炎；疫苗接种情况。",
            "allergy": "药物及吸入物过敏史。",
            "pe": "咽部、双肺呼吸音、干湿啰音、哮鸣音；血氧饱和度。",
            "labs": "血常规、CRP、胸片/胸部 CT、病原学（如有）。",
            "diagnosis": "",
            "assessment": "上下呼吸道感染鉴别；评估需不需影像与抗菌药物。",
        },
    },
    {
        "id": "tpl-cardio",
        "specialty": "cardio",
        "name": "心内科模板",
        "fields": {
            "chief": "胸闷 / 胸痛 / 心悸 / 头晕 等（填写具体病程）",
            "hpi": "发作诱因、持续时间、放射部位、伴随出汗恶心、静息/劳力相关；血压血糖血脂史。",
            "pmh": "高血压、冠心病、心律失常、心衰、糖尿病、脑血管病。",
            "allergy": "药物过敏史（抗血小板、造影剂等）。",
            "pe": "血压心率心律，心音杂音，双下肢水肿，颈静脉。",
            "labs": "心电图、心肌酶/肌钙蛋白、血脂血糖、超声心动图（如有）。",
            "diagnosis": "",
            "assessment": "胸痛危险分层；心源性 vs 非心源性鉴别；急症排查。",
        },
    },
]


def list_templates() -> list[dict[str, Any]]:
    return deepcopy(TEMPLATES)


def get_template(template_id: str) -> Optional[dict[str, Any]]:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return deepcopy(t)
    return None


TEMPLATE_FIELD_KEYS = (
    "chief",
    "hpi",
    "pmh",
    "allergy",
    "pe",
    "labs",
    "diagnosis",
    "assessment",
)
