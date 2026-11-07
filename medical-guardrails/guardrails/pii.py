"""PII masking before text is sent to an LLM.

Aligned with medical-patient-api / medical-assistant-api ``app.privacy.redact_for_log``
(phone -> 138****5678, id card -> ************1234) and ``MASK_SENSITIVE`` semantics
from ``app.settings.mask_sensitive_default_on`` (default on; 0/false/no/off disables).
"""

from __future__ import annotations

import os
import re

_PHONE_RE = re.compile(r"(?<!\d)((?:\+?86[- ]?)?)(1[3-9]\d)[- ]?(\d{4})[- ]?(\d{4})(?!\d)")
_ID18_RE = re.compile(r"(?<![\dA-Za-z])(\d{17}[\dXx])(?![\dA-Za-z])")
_ID15_RE = re.compile(r"(?<!\d)(\d{15})(?!\d)")


def mask_sensitive_enabled() -> bool:
    raw = os.environ.get("MASK_SENSITIVE")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _mask_id(s: str) -> str:
    return "*" * (len(s) - 4) + s[-4:]


def mask_pii(text) -> str:
    """Mask mainland mobile numbers and 15/18-digit id numbers.

    Honors MASK_SENSITIVE (default on). Non-str input is coerced with str(); None -> "".
    """
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    if not mask_sensitive_enabled():
        return s
    # ids first so an 18-digit id is never partially treated as a phone
    s = _ID18_RE.sub(lambda m: _mask_id(m.group(1)), s)
    s = _ID15_RE.sub(lambda m: _mask_id(m.group(1)), s)
    s = _PHONE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}****{m.group(4)}", s)
    return s
