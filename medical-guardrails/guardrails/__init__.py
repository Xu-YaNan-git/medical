"""Shared offline guardrails for the medical assistant APIs.

Public API (frozen, do not rename fields):
    check_input(text, role) -> {action, reason, category, advice, masked_text,
                                caution, caution_category}   # last two optional, None unless boundary band
    check_output(output, role, schema=None, fallback=None)
        -> {output, source, modified, flags, needs_doctor_confirm}
    mask_pii(text) -> str
    DISCLAIMER
"""

from .constants import (
    AI_NOTICE,
    CAUTION_ADVICE,
    CAUTION_CATEGORIES,
    CAUTION_MOOD_ADVICE,
    INPUT_CATEGORIES,
    REDFLAG_CATEGORIES,
    REFUSE_CATEGORIES,
    DISCLAIMER,
    REDFLAG_ADVICE,
    SUICIDE_ADVICE,
)
from .input_rules import check_input
from .output_rules import check_output
from .pii import mask_pii, mask_sensitive_enabled

__all__ = [
    "check_input",
    "check_output",
    "mask_pii",
    "mask_sensitive_enabled",
    "DISCLAIMER",
    "AI_NOTICE",
    "REDFLAG_ADVICE",
    "SUICIDE_ADVICE",
    "CAUTION_ADVICE",
    "CAUTION_MOOD_ADVICE",
    "INPUT_CATEGORIES",
    "REDFLAG_CATEGORIES",
    "REFUSE_CATEGORIES",
    "CAUTION_CATEGORIES",
]
__version__ = "0.2.0"
