"""استخراج و پارسِ مقاومِ JSON از خروجی مدل‌های هوش مصنوعی (با پشتیبانی کامل از بک‌اسلش‌های LaTeX).

مدل‌ها گاهی:
  - خروجی را در بلوک مارک‌داون (```json … ```) می‌پیچانند
  - متن توضیحی قبل یا بعد از JSON اضافه می‌کنند
  - درون رشته‌های JSON فرمول‌های LaTeX را با یک بک‌اسلش می‌نویسند (مانند `\\begin{bmatrix}`،
    `\\frac{a}{b}`، `\\sqrt{x}`، `\\times`، `\\cdot`) که در `json.loads` استاندارد پایتون
    باعث خطای `Invalid \\escape` یا تبدیل `\\b`/`\\f`/`\\t`/`\\r`/`\\n` به کاراکترهای کنترلی می‌شود.

این ماژول با `sanitize_json_string` و `safe_parse_json` تمام این موارد را به شکل امن اصلاح و پارس می‌کند.
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

# دستورات LaTeX که با حروف معتبر escape در JSON (b, f, n, r, t) شروع می‌شوند
# و اگر با یک بک‌اسلش نوشته شوند، json.loads آن‌ها را به کاراکتر کنترلی (\x08, \x0c, \n, \r, \t) تبدیل می‌کند.
_LATEX_BFNRT_CMDS = re.compile(
    r"(?<!\\)\\("
    r"begin|beta|binom|bar|textbf|bigcup|bigcap|bigoplus|bigotimes|bot|bullet|"
    r"frac|forall|flat|frown|"
    r"neq|nabla|nu|not|natural|neg|ni|nmid|nparallel|nsubseteq|"
    r"right|rightarrow|Rightarrow|rho|rangle|rceil|rfloor|rhd|rtimes|"
    r"times|tan|tanh|theta|tau|text|textbf|textit|textrm|top|triangle|to|tilde"
    r")(?![a-zA-Z])"
)

# درون محیط‌های ماتریسی (\begin{...} ... \end{...})، جداکنندهٔ سطر در LaTeX باید دو بک‌اسلش (\\) در رشتهٔ نهایی باشد
# یعنی در متن خام JSON باید چهار بک‌اسلش (\\\\) باشد.
_MATRIX_ENV_RE = re.compile(
    r"(\\\\begin\{(?:[a-zA-Z]*matrix|array|aligned|cases)\})([\s\S]*?)(\\\\end\{(?:[a-zA-Z]*matrix|array|aligned|cases)\})"
)


def _fix_matrix_row_breaks(match: re.Match) -> str:
    open_tag, body, close_tag = match.group(1), match.group(2), match.group(3)
    # اگر جداکنندهٔ سطر با دو بک‌اسلش نوشته شده (و نه چهار بک‌اسلش) و بعدش دستور LaTeX نیست، چهار بک‌اسلش کن
    fixed_body = re.sub(r"(?<!\\)\\\\(?![\\a-zA-Z\"])", r"\\\\\\\\", body)
    return f"{open_tag}{fixed_body}{close_tag}"


def sanitize_json_string(raw_text: str) -> str:
    """پاک‌سازی بلوک مارک‌داون، ویرگول‌های اضافه و ایمن‌سازی بک‌اسلش‌های LaTeX در JSON."""
    t = (raw_text or "").strip().lstrip("\ufeff")
    fence = _FENCE_RE.search(t)
    if fence:
        t = fence.group(1).strip()
    t = _LEADING_FENCE_RE.sub("", t)
    t = _TRAILING_FENCE_RE.sub("", t)
    t = _TRAILING_COMMA_RE.sub(r"\1", t)

    # ۱) دستورات LaTeX که با b/f/n/r/t شروع می‌شوند (مانند \begin, \frac, \right, \times, \tan, \neq, \to)
    t = _LATEX_BFNRT_CMDS.sub(r"\\\\\1", t)

    # ۲) هر بک‌اسلش تکی که دنبالهٔ آن یک escape معتبر JSON نیست (\sqrt, \cdot, \alpha, \lim, \sin, \log, \ge, \le, ...)
    t = re.sub(r'(?<!\\)\\(?![\\"/bfnrtu]|u[0-9a-fA-F]{4})', r"\\\\", t)

    # ۳) اصلاح جداکنندهٔ سطر (\\) در محیط‌های ماتریسی LaTeX
    t = _MATRIX_ENV_RE.sub(_fix_matrix_row_breaks, t)
    return t


# نام مستعار برای سازگاری با کدهای قبلی
sanitize_json_text = sanitize_json_string


def safe_parse_json(raw_text: str) -> Any:
    """پارس مقاوم JSON (آرایه یا شیء) با پشتیبانی از بک‌اسلش‌های فرمول‌های LaTeX."""
    if not raw_text or not str(raw_text).strip():
        raise ValueError("متن ورودی JSON خالی است.")

    text = str(raw_text).strip().lstrip("\ufeff")
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    text = _LEADING_FENCE_RE.sub("", text)
    text = _TRAILING_FENCE_RE.sub("", text)

    # استخراج بلوک JSON (با اولویتِ اولین کاراکتر بازکننده در متن: [ یا {)
    first_arr = text.find("[")
    first_obj = text.find("{")
    if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            text = m.group(0)
    elif first_obj != -1:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)

    # تلاش ۱: پاک‌سازی هوشمند بک‌اسلش‌های LaTeX و ویرگول‌های انتهایی
    cleaned = sanitize_json_string(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # تلاش ۲: جایگزینی مستقیم بک‌اسلش‌های غیرمعتبر طبق الگوی استاندارد
    cleaned_regex = re.sub(r'\\(?![\\"/bfnrtu])', r"\\\\", _TRAILING_COMMA_RE.sub(r"\1", text))
    try:
        return json.loads(cleaned_regex)
    except Exception:
        pass

    # تلاش ۳: تبدیل تمام بک‌اسلش‌ها به دو بک‌اسلش با حفظ گیومه‌های escapeشده
    cleaned2 = _TRAILING_COMMA_RE.sub(r"\1", text).replace("\\", "\\\\")
    cleaned2 = re.sub(r'\\\\"', r'\"', cleaned2)
    return json.loads(cleaned2)


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
                    spans.append(text[start: i + 1])
                    start = None
    return spans


def _try_dict(candidate: str) -> Optional[dict[str, Any]]:
    try:
        obj = safe_parse_json(candidate)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """اولین شیء JSON معتبر را از متن برمی‌گرداند (یا None)."""
    if not text or not text.strip():
        return None

    base = text.strip().lstrip("\ufeff")
    sanitized = sanitize_json_string(base)

    for cand in (sanitized, base):
        obj = _try_dict(cand)
        if obj is not None:
            return obj
        m = _GREEDY_OBJ_RE.search(cand)
        if m:
            obj = _try_dict(m.group(0))
            if obj is not None:
                return obj

    spans = _balanced_objects(sanitized) or _balanced_objects(base)
    for span in sorted(set(spans), key=len, reverse=True)[:6]:
        obj = _try_dict(span)
        if obj is not None:
            return obj
    return None


def extract_json_array(text: str) -> list[Any]:
    """استخراج آرایهٔ JSON از خروجی مدل (با پشتیبانی از LaTeX و شیءِ حاوی کلید questions)."""
    parsed = safe_parse_json(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        return parsed["questions"]
    m = _GREEDY_ARR_RE.search(text or "")
    if m:
        arr = safe_parse_json(m.group(0))
        if isinstance(arr, list):
            return arr
    raise ValueError("خروجی مدل آرایهٔ JSON معتبری نیست.")
