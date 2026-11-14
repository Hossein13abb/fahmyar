# -*- coding: utf-8 -*-
"""Typography layer — Persian shaping, BiDi, and direction-safe line breaking.

This module is the single place where text direction is decided.  Nothing else
in ``reports/`` may call ``arabic_reshaper`` or ``bidi`` directly.

Design rules (learned from ANALYSIS.md):

1.  BiDi is applied **per line**, never to a whole multi-line paragraph.
    Running ``get_display`` over text containing ``\\n`` reorders across the
    newline and produces scrambled output.

2.  Pure-Latin text is returned unchanged.  Calling ``get_display`` on
    ``"Which option is correct?"`` happens to be a no-op today, but relying on
    that is fragile — an isolated Latin run inside an RTL paragraph must be
    kept together.

3.  Shaping must happen **before** BiDi.  ``arabic_reshaper`` maps each Arabic
    letter to its positional presentation form; ``bidi`` then only reorders,
    never substitutes, so the two steps cannot be swapped.

4.  Numbers get their own guard: Latin digits inside Persian text are
    re-mapped to Persian digits by the caller (``to_persian_numbers``), not
    here, so this module stays direction-only.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

import arabic_reshaper
from bidi.algorithm import get_display

__all__ = [
    "RTL_RANGES",
    "has_rtl",
    "has_latin",
    "shape",
    "visual",
    "visual_lines",
    "direction_of",
    "is_neutral_only",
]

# ---------------------------------------------------------------------------
# Character classes
# ---------------------------------------------------------------------------

#: Arabic + Persian + Arabic Presentation Forms + Hebrew.
#: We only need Arabic/Persian but including the presentation forms matters
#: because ``arabic_reshaper`` output must still be recognised as RTL when it
#: comes back through the pipeline.
RTL_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)

_LATIN_RE = re.compile(r"[A-Za-z]")

# Persian/Arabic punctuation that must survive shaping untouched
_PERSIAN_PUNCT = "\u060C\u061B\u061F\u0640\u066A\u066B\u066C\u200C\u200F\u200E"


def _in_ranges(ch: str) -> bool:
    """True if ``ch`` is an RTL *letter*.

    Persian/Arabic **digits** (U+06F0-U+06F9, U+0660-U+0669) live inside the
    Arabic block but are direction-neutral, exactly like Latin digits.  Treating
    them as RTL letters makes ``"۲+۲"`` look like RTL text, which then triggers
    reshaping and a needless BiDi pass over a pure-number expression.
    """
    cp = ord(ch)
    if 0x0660 <= cp <= 0x0669 or 0x06F0 <= cp <= 0x06F9:  # Arabic-Indic / Persian digits
        return False
    return any(lo <= cp <= hi for lo, hi in RTL_RANGES)


def has_rtl(text: str) -> bool:
    """True if ``text`` contains at least one RTL letter."""
    return any(_in_ranges(ch) for ch in str(text or ""))


def has_latin(text: str) -> bool:
    """True if ``text`` contains at least one Latin letter."""
    return bool(_LATIN_RE.search(str(text or "")))


def is_neutral_only(text: str) -> bool:
    """True for strings made only of spaces / digits / punctuation."""
    s = str(text or "")
    if not s.strip():
        return True
    for ch in s:
        if ch.isspace() or ch.isdigit() or ch in _PERSIAN_PUNCT:
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        return False
    return True


def direction_of(text: str) -> str:
    """Return ``"rtl"``, ``"ltr"`` or ``"neutral"`` for a whole string."""
    s = str(text or "")
    if has_rtl(s):
        return "rtl"
    if has_latin(s):
        return "ltr"
    return "neutral"


# ---------------------------------------------------------------------------
# Shaping + reordering
# ---------------------------------------------------------------------------

def shape(text: str) -> str:
    """Apply Arabic/Persian contextual shaping. Idempotent for Latin text.

    ``arabic_reshaper`` with ``delete_harakat=False`` keeps diacritics, which
    matters for Quranic / vocalised content.
    """
    s = str(text or "")
    if not s:
        return ""
    if not has_rtl(s):
        # nothing to join -- avoid the (small) cost and any surprising edits
        return s
    return arabic_reshaper.reshape(s)


def visual(text: str) -> str:
    """Return the visual (left-to-right drawable) form of a single logical line.

    **Never pass a string containing ``\\n``** — use :func:`visual_lines` for
    that.  BiDi across a newline reorders unrelated lines.
    """
    s = str(text or "")
    if not s:
        return ""
    if "\n" in s or "\r" in s:
        raise ValueError("visual() received a multi-line string; use visual_lines()")
    shaped = shape(s)
    if not has_rtl(shaped) and not _LATIN_RE.search(shaped):
        # digits / punctuation only: BiDi would leave it alone anyway
        return shaped
    return get_display(shaped)


def visual_lines(text: str) -> List[str]:
    """Split on newlines first, then shape+bidi each line independently."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [visual(line) for line in raw.split("\n")]


# ---------------------------------------------------------------------------
# ASCII-only safety net used by the PDF writer
# ---------------------------------------------------------------------------

_INVISIBLES = dict.fromkeys(
    map(
        ord,
        (
            "\u200b\u200c\u200d\u200e\u200f"  # ZWSP ZWNJ ZWJ LRM RLM
            "\u202a\u202b\u202c\u202d\u202e"  # LRE RLE PDF LRO RLO
            "\u2066\u2067\u2068\u2069"        # LRI RLI FSI PDI
            "\ufeff"                          # BOM
        ),
    ),
    None,
)


def strip_invisibles(text: str, keep_zwnj: bool = True) -> str:
    """Remove bidi control characters that would leak into the PDF stream.

    ZWNJ is kept by default: in Persian it carries meaning (``می‌رود``).
    """
    s = str(text or "")
    if keep_zwnj:
        table = dict(_INVISIBLES)
        table.pop(0x200C, None)
        return s.translate(table)
    return s.translate(_INVISIBLES)  # type: ignore[arg-type]
