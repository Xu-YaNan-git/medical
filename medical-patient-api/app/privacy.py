"""Sensitive-field masking and log redaction.

Use redact_for_log / scrub_audit_detail before writing audit details or logging
request bodies. Never log full phone numbers or id cards.

Env (see app.settings):
  MASK_SENSITIVE=1          default on — force mask in identity API
  ALLOW_FULL_SENSITIVE=1    dangerous; disables force-mask in non-prod only
  APP_ENV / PROFILE         dev|prod
"""

from __future__ import annotations

import re
from typing import Any

from app import settings

# Mainland mobile: 11 digits starting with 1[3-9]
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
# 18-digit id (last may be X) or 15-digit legacy
_ID18_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
_ID15_RE = re.compile(r"(?<!\d)(\d{15})(?!\d)")


def mask_phone(phone: str) -> str:
    s = (phone or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 11:
        d = digits[-11:]
        return f"{d[:3]}****{d[-4:]}"
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "****" + s[-2:]


def mask_id_card(id_number: str) -> str:
    s = (id_number or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def mask_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    if len(name) == 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)


def redact_for_log(text: Any) -> str:
    """Replace 11-digit phones and 15/18 id patterns with masked forms."""
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    s = _PHONE_RE.sub(lambda m: mask_phone(m.group(1)), s)
    s = _ID18_RE.sub(lambda m: mask_id_card(m.group(1)), s)
    s = _ID15_RE.sub(lambda m: mask_id_card(m.group(1)), s)
    return s


def scrub_audit_detail(detail: str) -> str:
    return redact_for_log(detail or "")


def scrub_audit_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    if "detail" in out:
        out["detail"] = scrub_audit_detail(str(out.get("detail") or ""))
    return out
