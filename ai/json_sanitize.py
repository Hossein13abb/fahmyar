"""استخراج و پارسِ مقاومِ JSON از خروجی مدل‌های هوش مصنوعی (با پشتیبانی کامل از بک‌اسلش‌های LaTeX).

در پایتون، کاراکترهایی مانند `\\f` (در `\\frac`)، `\\t` (در `\\theta`) و `\\b` (در `\\begin`)
در صورتی که تک‌بک‌اسلشی باشند توسط `json.loads()` بلعیده می‌شوند.
همچنین گاهی مدل‌ها علامت دلار را به‌صورت `$\\$` یا `\\$` می‌نویسند که رندر KaTeX را مختل می‌کند.
این ماژول تمام این موارد را پیش از `json.loads` به‌صورت قطعی اصلاح می‌کند.
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
_GREEDY_ARR_RE = re.compile(r"\[.*\]", re.DOTALL)

# دستورات LaTeX که اگر بدون بک‌اسلش تولید شده باشند (مثلاً sqrt{7} یا vec{a} یا begin{bmatrix}) باید بک‌اسلش بگیرند
_BARE_LATEX_CMD_RE = re.compile(
    r"(?<![\\a-zA-Z])(sqrt|vec|frac|dfrac|tfrac|theta|alpha|beta|pi|cos|sin|tan|deg|circ)\b"
)
_BARE_ENV_RE = re.compile(
    r"(?<![\\a-zA-Z])(begin|end)\s*\{([a-zA-Z]*matrix|array|aligned|cases)\}"
)


def _extract_json_span(raw_text: str) -> str:
    text = str(raw_text or "").strip().lstrip("\ufeff")
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    text = _LEADING_FENCE_RE.sub("", text)
    text = _TRAILING_FENCE_RE.sub("", text)

    first_arr = text.find("[")
    first_obj = text.find("{")
    if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            return m.group(0)
    elif first_obj != -1:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
    return text


def _clean_dollar_noise(text: str) -> str:
    """اصلاح علامت‌های دلار تکراری یا اسکیپ‌شده مانند `$\\$`، `\\$` و `$$$` به `$`."""
    s = re.sub(r"\$\\+\$|\$\\\$|\$\$\$", "$", text)
    s = re.sub(r"\\+\$", "$", s)
    return s


def restore_latex_commands(obj: Any) -> Any:
    """پس‌پردازندهٔ امن پس از `json.loads` برای تضمین سلامت دستورات LaTeX و علامت‌های `$`."""
    if isinstance(obj, str):
        if "<svg" in obj.lower():
            return obj
        s = obj
        # احیای کاراکترهای کنترلی احتمالی
        s = s.replace("\x08", "\\b").replace("\x0c", "\\f")
        s = re.sub(r"\t(?=(?:imes|an|anh|heta|au|ext|op|riangle|o|ilde|frac)\b)", r"\\t", s)
        s = re.sub(r"\r(?=(?:ight|ho|angle|ceil|floor)\b)", r"\\r", s)

        # پاک‌سازی نویز دلار ($\$ یا \$)
        s = _clean_dollar_noise(s)

        # احیای بک‌اسلش برای دستورات ریاضی که بک‌اسلش آن‌ها افتاده است
        s = _BARE_ENV_RE.sub(r"\\\1{\2}", s)
        s = _BARE_LATEX_CMD_RE.sub(r"\\\1", s)

        # درون محیط‌های ماتریسی، جداکنندهٔ سطر باید دو بک‌اسلش (\\) در رشتهٔ نهایی باشد
        def _fix_mat_rows(m: re.Match) -> str:
            head, body, tail = m.group(1), m.group(2), m.group(3)
            body = re.sub(r"(?<!\\)\\(?![\\a-zA-Z])", r"\\\\", body)
            return f"{head}{body}{tail}"

        s = re.sub(
            r"(\\begin\{[bpvBV]?matrix\})([\s\S]*?)(\\end\{[bpvBV]?matrix\})",
            _fix_mat_rows,
            s,
        )

        # اطمینان از وجود آکولاد دور توان‌های منفی مانند ^-1 یا ^-۱
        s = re.sub(r"\^\s*(-[0-9۰-۹]+)", r"^{\1}", s)
        return s
    if isinstance(obj, list):
        return [restore_latex_commands(item) for item in obj]
    if isinstance(obj, dict):
        return {k: restore_latex_commands(v) for k, v in obj.items()}
    return obj


def sanitize_json_string(raw_text: str) -> Any:
    """پاک‌سازی بک‌اسلش‌های LaTeX و پارس مستقیم JSON به دیکشنری/لیست پایتون."""
    if not raw_text or not str(raw_text).strip():
        raise ValueError("Empty response from AI model")

    # 1. Extract JSON array or object (with priority to whichever starts first)
    extracted = _extract_json_span(raw_text)
    extracted = _TRAILING_COMMA_RE.sub(r"\1", extracted)

    # 2. Fix duplicate or broken dollar signs (e.g. $\$ -> $)
    extracted = re.sub(r"\$\\+\$|\$\\\$|\$\$\$", "$", extracted)
    extracted = re.sub(r"\\+\$", "$", extracted)

    # 3. Escape single backslashes so JSON parsing does NOT eat \f, \t, \b, \v, \s, \c
    # Replace \ with \\ EXCEPT if it is already \\ or escaping a double quote \"
    cleaned = re.sub(r'(?<!\\)\\(?!"|\\)', r"\\\\", extracted)

    try:
        return restore_latex_commands(json.loads(cleaned))
    except Exception as e:
        # Fallback: strict double-escape
        try:
            cleaned_fallback = extracted.replace("\\", "\\\\").replace('\\\\"', '\\"')
            return restore_latex_commands(json.loads(cleaned_fallback))
        except Exception:
            raise ValueError(f"JSON Sanitization Failed: {str(e)}")


def safe_parse_json(raw_text: str) -> Any:
    """نام مستعار سازگار برای پارس امن JSON حاوی دستورات LaTeX."""
    return sanitize_json_string(raw_text)


def _balanced_objects(text: str) -> list[str]:
    """اسکن عمق/گیومه‌آگاه — همهٔ شیءهای سطح‌اولِ {…} با تعادل پرانتز را برمی‌گرداند."""
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
                    spans.append(text[start : i + 1])
                    start = None
    return spans


def _try_dict(candidate: str) -> Optional[dict[str, Any]]:
    try:
        obj = sanitize_json_string(candidate)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """اولین شیء JSON معتبر را از متن برمی‌گرداند (یا None)."""
    if not text or not text.strip():
        return None

    base = text.strip().lstrip("\ufeff")
    obj = _try_dict(base)
    if isinstance(obj, dict):
        return obj

    m = _GREEDY_OBJ_RE.search(base)
    if m:
        obj = _try_dict(m.group(0))
        if isinstance(obj, dict):
            return obj

    for span in sorted(set(_balanced_objects(base)), key=len, reverse=True)[:6]:
        obj = _try_dict(span)
        if isinstance(obj, dict):
            return obj
    return None


def extract_json_array(text: str) -> list[Any]:
    """استخراج آرایهٔ JSON از خروجی مدل (با پشتیبانی از LaTeX و شیءِ حاوی کلید questions)."""
    parsed = sanitize_json_string(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        return parsed["questions"]
    m = _GREEDY_ARR_RE.search(text or "")
    if m:
        arr = sanitize_json_string(m.group(0))
        if isinstance(arr, list):
            return arr
    raise ValueError("خروجی مدل آرایهٔ JSON معتبری نیست.")
