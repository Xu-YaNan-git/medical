import json

from guardrails import AI_NOTICE, DISCLAIMER, check_output
from guardrails.output_rules import has_dosage

KEYS = {"output", "source", "modified", "flags", "needs_doctor_confirm"}

SCHEMA = {
    "type": "object",
    "required": ["departments", "urgency"],
    "properties": {
        "departments": {"type": "array", "minItems": 1},
        "urgency": {"enum": ["emergency", "urgent", "routine"]},
    },
}
MOCK = {"departments": [{"name": "全科医学"}], "urgency": "routine", "source": "mock"}


def test_patient_removes_diagnosis_and_dosage_str():
    r = check_output("你得了胃溃疡，奥美拉唑每次20mg，每日2次，连用两周。", "patient")
    assert set(r) == KEYS
    out = r["output"]
    assert "你得了" not in out
    assert "可能与胃溃疡有关，需医生评估" in out
    assert "20mg" not in out and "每日2次" not in out and not has_dosage(out)
    assert out.endswith(DISCLAIMER)
    assert r["flags"] == ["removed_diagnosis", "removed_dosage", "added_disclaimer"]
    assert r["modified"] is True and r["source"] is None and r["needs_doctor_confirm"] is False


def test_patient_variants():
    for text in ["确诊为高血压", "可以确定是偏头痛", "您患有糖尿病"]:
        out = check_output(text, "patient")["output"]
        assert "需医生评估" in out and "确诊为" not in out and "患有" not in out


def test_hedged_wording_kept():
    r = check_output("可能得了胃炎，建议消化内科就诊。", "patient")
    assert "removed_diagnosis" not in r["flags"]
    assert r["output"].startswith("可能得了胃炎")


def test_dosage_forms():
    for text in ["布洛芬一次2片", "每次500毫克", "一天三次，每次一粒", "10mg/kg", "阿奇霉素 qd", "1-2片"]:
        out = check_output(text, "patient")["output"]
        assert not has_dosage(out), (text, out)


def test_symptom_frequency_not_treated_as_dosage():
    r = check_output("腹泻一天五六次，发热38.5℃持续3天。", "patient")
    assert "removed_dosage" not in r["flags"]
    assert "一天五六次" in r["output"] and "38.5℃" in r["output"]


def test_patient_dict_gets_disclaimer_and_sanitized_nested():
    r = check_output({"summary": "你得了肺炎", "nextSteps": ["阿莫西林每次0.5g"], "id": "dept-1mg"}, "patient")
    o = r["output"]
    assert o["disclaimer"] == DISCLAIMER
    assert "需医生评估" in o["summary"]
    assert not has_dosage(o["nextSteps"][0])
    assert o["id"] == "dept-1mg"  # id-like keys untouched
    assert set(r["flags"]) == {"removed_diagnosis", "removed_dosage", "added_disclaimer"}


def test_patient_existing_disclaimer_kept():
    r = check_output({"summary": "建议消化内科", "disclaimer": "辅助导诊，不替代面诊。"}, "patient")
    assert r["output"]["disclaimer"] == "辅助导诊，不替代面诊。"
    assert r["flags"] == [] and r["modified"] is False


def test_patient_str_disclaimer_not_duplicated():
    r = check_output("建议消化内科。\n\n" + DISCLAIMER, "patient")
    assert r["output"].count(DISCLAIMER) == 1 and r["modified"] is False


def test_doctor_only_marks_confirm():
    text = "确诊为高血压，氨氯地平5mg qd"
    r = check_output(text, "doctor")
    assert r["output"] == text
    assert r["needs_doctor_confirm"] is True
    assert r["modified"] is False
    r2 = check_output({"differentials": ["高血压"], "dose": "5mg qd"}, "doctor")
    assert r2["output"]["aiNotice"] == AI_NOTICE
    assert r2["output"]["dose"] == "5mg qd"
    assert "disclaimer" not in r2["output"]
    assert r2["needs_doctor_confirm"] is True and r2["modified"] is True


def test_schema_valid_str_is_parsed():
    raw = "```json\n" + json.dumps({"departments": [{"name": "消化内科"}], "urgency": "routine"}) + "\n```"
    r = check_output(raw, "patient", schema=SCHEMA)
    assert isinstance(r["output"], dict)
    assert "schema_invalid" not in r["flags"] and r["source"] is None


def test_schema_invalid_with_callable_fallback():
    calls = []

    def fb():
        calls.append(1)
        return dict(MOCK)

    r = check_output({"departments": [], "urgency": "soon"}, "patient", schema=SCHEMA, fallback=fb)
    assert calls == [1]
    assert r["source"] == "mock_fallback"
    assert "schema_invalid" in r["flags"]
    assert r["output"]["departments"] == MOCK["departments"]
    assert r["output"]["disclaimer"] == DISCLAIMER
    assert r["modified"] is True


def test_schema_invalid_dict_fallback_doctor():
    r = check_output("not json at all", "doctor", schema=SCHEMA, fallback=MOCK)
    assert r["source"] == "mock_fallback"
    assert r["output"]["aiNotice"] == AI_NOTICE
    assert MOCK.get("aiNotice") is None  # fallback dict not mutated
    assert r["needs_doctor_confirm"] is True


def test_schema_invalid_without_fallback_keeps_output():
    r = check_output("{bad json", "doctor", schema=SCHEMA)
    assert r["output"] == "{bad json"
    assert "schema_invalid" in r["flags"]
    assert r["source"] is None


def test_input_not_mutated():
    src = {"summary": "你得了肺炎"}
    check_output(src, "patient")
    assert src == {"summary": "你得了肺炎"}


def test_ni_zhe_shi_wording():
    out = check_output("你这是高血压，氨氯地平5mg qd 长期吃。", "patient")["output"]
    assert "你这是" not in out and "可能与高血压有关，需医生评估" in out and not has_dosage(out)
