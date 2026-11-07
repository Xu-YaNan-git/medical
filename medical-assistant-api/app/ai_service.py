"""AI capabilities: prefer real LLM, fall back to ai_mock with explicit source/error."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app import ai_mock
from app import llm as llm_client

logger = logging.getLogger(__name__)

DISCLAIMER = ai_mock.DISCLAIMER

SYSTEM_PREAMBLE = (
    "你是一名临床辅助决策助手，结果仅供参考，须医生确认；辅助决策，不替代执业医师。"
    "请严格按用户要求返回可解析的 JSON 对象，不要输出 Markdown 说明或代码围栏以外的多余文字。"
)


def _meta_llm() -> dict[str, Optional[str]]:
    return {"source": "llm", "error": None, "message": None}


def _meta_mock(reason: str, err_code: str = "llm_fallback") -> dict[str, Optional[str]]:
    return {"source": "mock", "error": err_code, "message": reason}


def parse_text(raw: str) -> dict[str, Any]:
    """Parse unstructured clinical text into chart fields."""
    raw = (raw or "").strip()
    if llm_client.is_configured():
        try:
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE
                + "任务：从医生粘贴的非结构化病情文本中抽取病历字段。"
                "返回 JSON 键：chief,hpi,pmh,allergy,pe,labs（均为字符串，中文）。"
                "缺失字段用简短提示如「未提供」或「待补充」，勿编造检查结果。",
                f"病情文本：\n{raw}",
            )
            fields = {
                "chief": str(data.get("chief") or "").strip(),
                "hpi": str(data.get("hpi") or "").strip(),
                "pmh": str(data.get("pmh") or "").strip(),
                "allergy": str(data.get("allergy") or "").strip(),
                "pe": str(data.get("pe") or "").strip(),
                "labs": str(data.get("labs") or "").strip(),
            }
            if not fields["chief"] and not fields["hpi"]:
                raise ValueError("解析结果缺少主诉与现病史")
            for k, default in (
                ("chief", raw[:30] + ("…" if len(raw) > 30 else "")),
                ("hpi", raw),
                ("pmh", "未提供"),
                ("allergy", "未提供，需进一步询问"),
                ("pe", "待补充"),
                ("labs", "暂无"),
            ):
                if not fields[k]:
                    fields[k] = default
            return {**fields, "disclaimer": DISCLAIMER, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 解析失败，已降级 Mock：{llm_client.sanitize_error(exc)}"
            logger.warning("parse_text fallback: %s", reason)
            fields = ai_mock.parse_unstructured(raw)
            return {**fields, "disclaimer": DISCLAIMER, **_meta_mock(reason)}

    fields = ai_mock.parse_unstructured(raw)
    return {
        **fields,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def generate_differential(visit: dict[str, Any]) -> dict[str, Any]:
    """Generate 3–5 differential diagnosis items."""
    if llm_client.is_configured():
        try:
            specialty = (visit.get("specialty") or "").strip() or "全科"
            context = {
                "name": visit.get("name"),
                "gender": visit.get("gender"),
                "age": visit.get("age"),
                "specialty": specialty,
                "chief": visit.get("chief"),
                "hpi": visit.get("hpi"),
                "pmh": visit.get("pmh"),
                "allergy": visit.get("allergy"),
                "pe": visit.get("pe"),
                "labs": visit.get("labs"),
            }
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE
                + "任务：根据病历给出 3～5 条鉴别诊断。"
                "必须结合当前专科视角（specialty）排序与侧重点，同主诉在不同专科下鉴别应有可观察差异。"
                '返回 JSON：{"items":[{"id":"dx1","name":"...","rationale":"...","rank":1,"prob":"较高|中等|较低","decision":"pending"},...]}。'
                "id 用 dx1..dxN；rank 从 1 起；decision 必须为 pending；rationale 用中文简述依据，可点明专科考量。",
                f"专科={specialty}\n病历：{context}",
            )
            raw_items = data.get("items") or data.get("differential") or []
            if not isinstance(raw_items, list) or len(raw_items) < 3:
                raise ValueError("鉴别诊断条目不足 3 条")
            items: list[dict[str, Any]] = []
            for i, it in enumerate(raw_items[:5]):
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or "").strip()
                if not name:
                    continue
                items.append(
                    {
                        "id": str(it.get("id") or f"dx{i + 1}"),
                        "name": name,
                        "rationale": str(it.get("rationale") or it.get("reason") or "").strip()
                        or "依据现有病史与体征的初步鉴别",
                        "rank": int(it.get("rank") or (i + 1)),
                        "prob": str(it.get("prob") or "中等"),
                        "decision": "pending",
                    }
                )
            if len(items) < 3:
                raise ValueError("有效鉴别诊断不足 3 条")
            return {"items": items, "disclaimer": DISCLAIMER, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 鉴别诊断失败，已降级 Mock：{llm_client.sanitize_error(exc)}"
            logger.warning("differential fallback: %s", reason)
            items = ai_mock.generate_differential(visit)
            return {"items": items, "disclaimer": DISCLAIMER, **_meta_mock(reason)}

    items = ai_mock.generate_differential(visit)
    return {
        "items": items,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def _tag_drugs(drugs: list[dict[str, Any]], allergy: str) -> list[dict[str, Any]]:
    out = []
    for d in drugs:
        text = str(d.get("text") or "").strip()
        if not text:
            continue
        warn = ai_mock.has_allergy_conflict(allergy, text)
        out.append(
            {
                "type": "药品",
                "text": text,
                "conflict": bool(warn),
                "warn": warn,
            }
        )
    return out


def suggest_orders(visit: dict[str, Any]) -> dict[str, Any]:
    """Suggest exams + drugs; always allergy-tag drugs via ai_mock."""
    allergy = visit.get("allergy") or ""
    if llm_client.is_configured():
        try:
            adopted = [
                d.get("name")
                for d in (visit.get("differential") or [])
                if d.get("decision") == "accept"
            ]
            pending = [d.get("name") for d in (visit.get("differential") or [])]
            specialty = (visit.get("specialty") or "").strip() or "全科"
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE
                + "任务：根据病历与鉴别诊断建议检查与药品。"
                "必须结合当前专科（specialty）给出更贴合该专科的检查与用药建议，不同专科应有可观察差异。"
                '返回 JSON：{"exams":[{"type":"检查","text":"..."}],"drugs":[{"type":"药品","text":"..."}]}。'
                "药品写通用名+剂量用法示例；勿忽略过敏史提示（过敏史由服务端再校验）。",
                f"专科={specialty}; 病历摘要：主诉={visit.get('chief')}; 现病史={visit.get('hpi')}; "
                f"既往={visit.get('pmh')}; 过敏={allergy}; 查体={visit.get('pe')}; "
                f"检查={visit.get('labs')}; 已采纳诊断={adopted or pending[:1]}",
            )
            exams_raw = data.get("exams") or []
            drugs_raw = data.get("drugs") or []
            if not isinstance(exams_raw, list) or not isinstance(drugs_raw, list):
                raise ValueError("exams/drugs 须为数组")
            exams = []
            for e in exams_raw:
                if isinstance(e, str):
                    text = e.strip()
                elif isinstance(e, dict):
                    text = str(e.get("text") or "").strip()
                else:
                    continue
                if text:
                    exams.append({"type": "检查", "text": text, "conflict": False, "warn": None})
            drugs_in = []
            for d in drugs_raw:
                if isinstance(d, str):
                    drugs_in.append({"text": d})
                elif isinstance(d, dict):
                    drugs_in.append(d)
            drugs = _tag_drugs(drugs_in, allergy)
            if not exams and not drugs:
                raise ValueError("建议检查与药品均为空")
            return {
                "exams": exams,
                "drugs": drugs,
                "disclaimer": DISCLAIMER,
                **_meta_llm(),
            }
        except Exception as exc:
            reason = f"LLM 医嘱建议失败，已降级 Mock：{llm_client.sanitize_error(exc)}"
            logger.warning("orders_suggest fallback: %s", reason)
            result = ai_mock.suggest_orders(visit)
            return {**result, "disclaimer": DISCLAIMER, **_meta_mock(reason)}

    result = ai_mock.suggest_orders(visit)
    return {
        **result,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def generate_note(visit: dict[str, Any]) -> dict[str, Any]:
    """Generate structured outpatient note."""
    sections = ai_mock.note_sections(visit)
    if llm_client.is_configured():
        try:
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE
                + "任务：根据病历生成结构化门诊病历全文。"
                '返回 JSON：{"fullText":"..."}。全文须含主诉/现病史/既往史/过敏史/查体/辅助检查/初步诊断/医嘱，'
                "文末注明仅供参考、须医生确认、不替代执业医师。",
                f"病历结构化数据：{sections}",
            )
            full = str(data.get("fullText") or data.get("text") or "").strip()
            if len(full) < 20:
                raise ValueError("病历全文过短")
            if "仅供参考" not in full and "不替代" not in full:
                full += f"\n\n——\n{DISCLAIMER}"
            return {
                "sections": sections,
                "fullText": full,
                "disclaimer": DISCLAIMER,
                **_meta_llm(),
            }
        except Exception as exc:
            reason = f"LLM 病历生成失败，已降级 Mock：{llm_client.sanitize_error(exc)}"
            logger.warning("note_generate fallback: %s", reason)
            full = ai_mock.build_note(visit, style="structured")
            return {
                "sections": sections,
                "fullText": full,
                "disclaimer": DISCLAIMER,
                **_meta_mock(reason),
            }

    full = ai_mock.build_note(visit, style="structured")
    return {
        "sections": sections,
        "fullText": full,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }


def polish_note(
    content: str,
    style: str,
    visit: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Polish note text to concise or formal style."""
    if llm_client.is_configured():
        try:
            style_hint = "简洁版，压缩冗余" if style in ("concise", "simple") else "正式规范门诊病历体例"
            data = llm_client.chat_json(
                SYSTEM_PREAMBLE
                + f"任务：将门诊病历润色为{style_hint}。"
                '返回 JSON：{"text":"..."}。保留关键临床信息，文末含仅供参考、须医生确认、不替代执业医师。',
                f"风格={style}\n原文：\n{content or '(空，请根据上下文生成)'}\n"
                f"上下文患者：{(visit or {}).get('name')} {(visit or {}).get('gender')} {(visit or {}).get('age')}",
            )
            text = str(data.get("text") or data.get("fullText") or "").strip()
            if len(text) < 10:
                raise ValueError("润色结果过短")
            if "仅供参考" not in text and "不替代" not in text:
                text += f"\n\n※ {DISCLAIMER}"
            return {"text": text, "disclaimer": DISCLAIMER, **_meta_llm()}
        except Exception as exc:
            reason = f"LLM 病历润色失败，已降级 Mock：{llm_client.sanitize_error(exc)}"
            logger.warning("note_polish fallback: %s", reason)
            text = ai_mock.polish_note(content, style, visit=visit)
            return {"text": text, "disclaimer": DISCLAIMER, **_meta_mock(reason)}

    text = ai_mock.polish_note(content, style, visit=visit)
    return {
        "text": text,
        "disclaimer": DISCLAIMER,
        **_meta_mock("未配置 LLM_API_KEY，使用规则 Mock", "llm_not_configured"),
    }
