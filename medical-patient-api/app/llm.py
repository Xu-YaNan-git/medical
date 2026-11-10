"""OpenAI-compatible LLM client. Credentials only from environment variables."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator, Optional

from openai import OpenAI

DEFAULT_BASE_URL = "https://sub.apixu.top/v1"
DEFAULT_MODEL = "gpt-5.6-sol"


def _normalize_base_url(url: str) -> str:
    u = (url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not u.endswith("/v1"):
        u = u + "/v1"
    return u


def get_api_key() -> Optional[str]:
    key = os.environ.get("LLM_API_KEY")
    if key is None:
        return None
    key = key.strip()
    return key or None


def is_configured() -> bool:
    return bool(get_api_key())


def get_base_url() -> str:
    return _normalize_base_url(os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL)


def get_model() -> str:
    return (os.environ.get("LLM_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def sanitize_error(exc: BaseException) -> str:
    """Human-readable error without credentials or bearer tokens."""
    msg = str(exc) or type(exc).__name__
    key = get_api_key()
    if key:
        msg = msg.replace(key, "[REDACTED]")
    msg = re.sub(r"\bsk-[A-Za-z0-9_\-]{6,}\b", "[REDACTED]", msg)
    msg = re.sub(r"(Bearer\s+)\S+", r"\1[REDACTED]", msg, flags=re.I)
    msg = re.sub(r"(api[_-]?key[\"'=:\s]+)[^\s\"']+", r"\1[REDACTED]", msg, flags=re.I)
    msg = re.sub(r"(?i)((?:access[_-]?)?token[\"'=:\s]+)[^\s\"']+", r"\1[REDACTED]", msg)
    if len(msg) > 400:
        msg = msg[:400] + "…"
    return msg


def create_client() -> OpenAI:
    key = get_api_key()
    if not key:
        raise RuntimeError("LLM_API_KEY 未配置")
    return OpenAI(api_key=key, base_url=get_base_url(), timeout=60.0)


def _parse_json_object(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if not content:
        raise ValueError("模型返回空内容")
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", content)
        if not m:
            raise ValueError(f"模型返回非 JSON：{e}") from e
        data = json.loads(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("模型 JSON 根节点须为对象")
    return data


def _completion_messages(
    system: str,
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """System prompt plus user/assistant turns. Drops empty or unknown roles."""
    payload: list[dict[str, str]] = [{"role": "system", "content": system}]
    for raw in messages or []:
        role = str(raw.get("role") or "")
        content = str(raw.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        payload.append({"role": role, "content": content})
    if len(payload) < 2:
        raise ValueError("问诊消息为空")
    return payload


def chat_json_messages(
    system: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Chat completions with a real multi-turn history; parse a JSON object."""
    client = create_client()
    kwargs: dict[str, Any] = {
        "model": get_model(),
        "messages": _completion_messages(system, messages),
        "temperature": temperature,
    }
    try:
        resp = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(**kwargs)

    content = (resp.choices[0].message.content or "").strip()
    return _parse_json_object(content)


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Single-turn JSON call. Prefer chat_json_messages when history exists."""
    return chat_json_messages(
        system,
        [{"role": "user", "content": user}],
        temperature=temperature,
    )


def chat_text(
    system: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
) -> str:
    """Multi-turn chat; returns assistant text."""
    client = create_client()
    payload = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=get_model(),
        messages=payload,
        temperature=temperature,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("模型返回空内容")
    return content


def chat_text_stream(
    system: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
) -> Iterator[str]:
    """Stream assistant text tokens from chat completions."""
    client = create_client()
    payload = [{"role": "system", "content": system}] + messages
    stream = client.chat.completions.create(
        model=get_model(),
        messages=payload,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None) or ""
        except Exception:
            piece = ""
        if piece:
            yield piece
