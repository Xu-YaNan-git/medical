"""Text normalization shared by input/output rules."""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_WS = re.compile(r"[^\S\n]+")
_NL = re.compile(r"\r\n?|[\u2028\u2029\x0b\x0c\x85]")
_NON_WORD = re.compile(r"[^0-9a-z\u4e00-\u9fff\n]+")


def compact(text: str) -> str:
    """NFKC (full-width → half-width), lower-case, drop whitespace & zero-width chars.

    Punctuation is kept so clause boundaries survive (needed for negation scope).
    Newlines are kept: callers separate record fields with "\n" and no rule may match across them.
    """
    s = unicodedata.normalize("NFKC", text or "")
    s = _ZERO_WIDTH.sub("", s)
    s = s.lower()
    s = _NL.sub("\n", s)
    return _WS.sub("", s)


def bare(text: str) -> str:
    """compact() and also drop every non letter/digit/CJK char except "\n" (defeats 忽-略/忽.略 tricks)."""
    return _NON_WORD.sub("", compact(text))
