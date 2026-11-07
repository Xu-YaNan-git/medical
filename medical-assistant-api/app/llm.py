"""OpenAI-compatible LLM client. Credentials only from environment variables."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

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
    """Human-readable error without credentials."""
    msg = str(exc) or type(exc).__name__
    key = get_api_key()
    if key:
        msg = msg.replace(key, "[REDACTED]")
    # Common auth header patterns
    msg = re.sub(r"(Bearer\s+)\S+", r"\1[REDACTED]", msg, flags=re.I)
    msg = re.sub(r"(api[_-]?key[\"'=:\s]+)[^\s\"']+", r"\1[REDACTED]", msg, flags=re.I)
    # Truncate very long bodies
    if len(msg) > 400:
        msg = msg[:400] + "…"
    return msg


def create_client() -> OpenAI:
    key = get_api_key()
    if not key:
        raise RuntimeError("LLM_API_KEY 未配置")
    return OpenAI(api_key=key, base_url=get_base_url(), timeout=60.0)


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Call chat completions and parse a JSON object from the assistant message."""
    client = create_client()
    kwargs: dict[str, Any] = {
        "model": get_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    # Prefer JSON mode when the gateway supports it; fall back without it on error.
    try:
        resp = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(**kwargs)

    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("模型返回空内容")

    # Strip optional markdown fences
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        # Try to extract first JSON object/array
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", content)
        if not m:
            raise ValueError(f"模型返回非 JSON：{e}") from e
        data = json.loads(m.group(1))

    if not isinstance(data, dict):
        raise ValueError("模型 JSON 根节点须为对象")
    return data
