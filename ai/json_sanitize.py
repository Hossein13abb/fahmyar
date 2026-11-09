"""استخراجِ مقاومِ شیء JSON از خروجی مدل‌های هوش مصنوعی.

مدل‌ها گاهی خروجی را در بلوک مارک‌داون (```json … ```) می‌پیچانند یا متنِ توضیحی
قبل/بعد از JSON اضافه می‌کنند، ویرگول‌های اضافه می‌گذارند یا گیومه‌های نامتوازن تولید می‌کنند.
این ماژول سعی می‌کند «خودِ شیء JSON» را با کمترین دست‌کاری استخراج کند.

نکات:
  - \u200c (نیم‌فاصلهٔ فارسی) عمداً حذف/تغییر نمی‌شود.
  - فقط BOM و کاراکترهای جانبیِ نامرئی حذف می‌شوند.
  - اگر خروجی کاملاً غیرقابل‌پارس باشد، None برگردانده می‌شود (تصمیم با فراخواننده است).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE_RE = re.compile(r"```(?:json|JSON|Json)?\s*(.*?)```", re.DOTALL)
_LEADING_FENCE_RE = re.compile(r"^```(?:json|JSON|Json)?\s*")
_TRAILING_FENCE_RE = re.compile(r"\s*```\s*$")
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_GREEDY_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def sanitize_json_text(text: str) -> str:
    """بلوک‌های مارک‌داون و ویرگول‌های اضافه را پاک می‌کند."""
    t = text.strip().lstrip("\ufeff")
    fence = _FENCE_RE.search(t)          # بلوک ```json … ``` در هر جای متن
    if fence:
        t = fence.group(1).strip()
    t = _LEADING_FENCE_RE.sub("", t)     # فنس بازِ بدون بستهٔ متناظر
    t = _TRAILING_FENCE_RE.sub("", t)    # فنس بستهٔ اضافه
    t = _TRAILING_COMMA_RE.sub(r"\1", t) # ویرگول اضافه قبل از } یا ]
    return t


def _balanced_objects(text: str) -> list[str]:
    """اسکن عمق/گیومه‌آگاه — همهٔ شیءهای سطح‌اولِ {…} با تعادل پرانتز را برمی‌گرداند.

    گیومه‌ها و escape‌ها رعایت می‌شوند تا آکولادهای داخل رشته JSON را نشکند.
    """
    spans: list[str] = []
    depth = 0
    start: Optional[int] = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append(text[start: i + 1])
                    start = None
    return spans


def _try_dict(candidate: str) -> Optional[dict[str, Any]]:
    try:
        obj = json.loads(candidate)
    except Exception:
        # یک تلاشِ آخر با حذف ویرگول‌های اضافه
        try:
            obj = json.loads(_TRAILING_COMMA_RE.sub(r"\1", candidate))
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """اولین شیء JSON معتبر را از متن برمی‌گرداند (یا None)."""
    if not text or not text.strip():
        return None

    base = text.strip().lstrip("\ufeff")
    sanitized = sanitize_json_text(base)

    # ۱) تلاش مستقیم روی متن اصلی و نسخهٔ تمیزشده
    for cand in (base, sanitized):
        obj = _try_dict(cand)
        if obj is not None:
            return obj
        # ۲) regex حریصانهٔ {.*} (طولانی‌ترین بازهٔ ممکن)
        m = _GREEDY_OBJ_RE.search(cand)
        if m:
            obj = _try_dict(m.group(0))
            if obj is not None:
                return obj

    # ۳) اسکن تعادل پرانتز — از بزرگ‌ترین بازه به کوچک‌ترین
    spans = _balanced_objects(sanitized) or _balanced_objects(base)
    for span in sorted(set(spans), key=len, reverse=True)[:6]:
        obj = _try_dict(span)
        if obj is not None:
            return obj
    return None
