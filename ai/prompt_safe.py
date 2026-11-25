"""جایگذاریِ امنِ متغیر در پرامپت — بدونِ `.format()`.

**باگی که این ماژول برای همیشه می‌بندد:**

پرامپت‌های این پروژه آکولادِ LaTeX دارند (`\\frac{4}{9}`، `\\cos^{-1}`,
`\\begin{bmatrix}`، `T^{-1}`). متدِ `str.format` هر آکولاد را یک فیلدِ
جایگذاری می‌بیند؛ پس `\\cos^{-1}` به `KeyError: '-1'` می‌رسد و کلِ تولیدِ
دفترچه می‌شکند. خطای واقعی که در لاگ دیده شد:

    [start-test-attach] booklet generation failed: '-1'

راه‌حل‌ها و دلیلِ رد شدنشان:

* **دوبرابر کردن آکولادها** (`{{` → `{`) — کار می‌کند ولی شکننده است: هر
  ویرایشِ متنِ پرامپت باید دوباره بازبینی شود و یک آکولادِ جامانده همان
  باگ را برمی‌گرداند.
* **`string.Template`** — `$` را به‌عنوان جداکننده می‌گیرد، ولی این
  پرامپت‌ها پر از `$...$` ریاضی‌اند. بدتر می‌شود.
* **f-string** — در زمانِ *تعریف* ارزیابی می‌شود، پس متغیرهای زمانِ اجرا
  (concept، grade) را نمی‌پذیرد.

پس تنها راهِ درست `.replace()` است: آکولاد پرامپت هرگز تفسیر نمی‌شود.
این ماژول آن را به یک تابعِ کمکیِ قابلِ آزمون تبدیل می‌کند تا همهٔ ماژول‌ها
یک الگو داشته باشند و کسی دوباره `.format` ننویسد.
"""
from __future__ import annotations

import re
from typing import Any, Mapping


class TemplateError(KeyError):
    """جای‌نگهدارِ لازم در پرامپت پیدا نشد."""


def fill(template: str, **values: Any) -> str:
    """جای‌نگهدارهای ``{name}`` را با مقادیر جایگزین می‌کند.

    فقط الگوی دقیقِ ``{name}`` (حروف، عدد، زیرخط) جایگزین می‌شود. آکولادهای
    LaTeX مثل ``{-1}`` یا ``{bmatrix}`` هرگز مطابقِ این الگو نیستند، پس
    دست‌نخورده می‌مانند.

    اگر جای‌نگهدارِ ``{name}`` در متن باشد ولی مقدارش نده نشود، خطا می‌دهد —
    چون پرامپتِ نیمه‌کاره که ``{concept}`` در آن چاپ شود، سؤالِ بی‌معنی تولید
    می‌کند و پیدا کردنش از یک استثنای صریح سخت‌تر است.
    """
    return fill_map(template, values)


def fill_map(template: str, values: Mapping[str, Any]) -> str:
    """همان ``fill`` با یک دیکشنری به‌جای آرگومان‌های نام‌دار."""
    if not isinstance(template, str):
        raise TypeError("قالبِ پرامپت باید رشته باشد")

    out = template
    for key, value in values.items():
        out = out.replace("{" + str(key) + "}", "" if value is None else str(value))

    _assert_no_leftovers(out)
    return out


_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]{0,40})\}")
_LATEX_CMD_BEFORE_RE = re.compile(r"\\[A-Za-z]+$")


def _is_latex_argument(text: str, start: int) -> bool:
    """آیا آکولادِ بازشده در ``start`` آرگومانِ یک دستورِ LaTeX است؟

    سه حالت — هر سه در پرامپت‌های واقعیِ این پروژه دیده می‌شوند:

    * ``\\vec{n}``      → آکولاد بلافاصله پس از نامِ دستور
    * ``\\frac{a}{b}``  → آکولادِ دوم پس از ``}`` (زنجیرهٔ آرگومان‌ها)
    * ``\\begin{bmatrix}`` → نامِ محیطِ LaTeX
    """
    if start > 0 and text[start - 1] == "\\":
        return True
    if _LATEX_CMD_BEFORE_RE.search(text[max(0, start - 24):start]):
        return True
    if start > 0 and text[start - 1] == "}":
        return True
    return False


def _assert_no_leftovers(text: str) -> None:
    """اگر جای‌نگهدارِ واقعی (نه LaTeX) باقی مانده باشد، صریح خطا بده."""
    for match in _PLACEHOLDER_RE.finditer(text):
        name = match.group(1)
        if _is_latex_argument(text, match.start()):
            continue
        if name.lower() in _LATEX_ENV_NAMES:
            continue
        raise TemplateError(
            f"جای‌نگهدارِ «{{{name}}}» در پرامپت پر نشد — مقدارش به fill() داده نشده است."
        )



#: نام‌هایی که بخشی از دستورِ LaTeX اند، نه جای‌نگهدار
_LATEX_ENV_NAMES = {
    "bmatrix", "pmatrix", "matrix", "vmatrix", "Vmatrix", "array", "aligned",
    "cases", "frac", "sqrt", "vec", "bar", "hat", "text", "mathrm", "left",
    "right", "begin", "end", "quad", "qquad", "cdot", "times", "delta",
    "theta", "alpha", "beta", "gamma", "lambda", "mu", "pi", "sigma", "phi",
    "omega", "sum", "int", "lim", "log", "ln", "sin", "cos", "tan", "cot",
}


def assert_no_format_calls(module_source: str, module_name: str = "") -> None:
    """تست: مطمئن شو در فایل، ``.format(`` روی پرامپت وجود ندارد.

    این تابع در تست‌ها استفاده می‌شود تا اگر روزی کسی دوباره
    ``PROMPT.format(...)`` نوشت، تست قرمز شود — نه اینکه در تولید پاتک بزند.
    """
    import re

    # .format( روی متغیرها مجاز است؟ خیر — همهٔ .format روی رشته‌ها ممنوع شد،
    # چون همین الگو باگ را ساخت. استثنا: خودِ این ماژول.
    #
    # فقط کدِ واقعی بررسی می‌شود، نه متنِ توضیحی: پیامِ خودِ این گارد هم
    # عبارت `.format()` را در یک رشته دارد و نباید خودش را قرمز کند.
    hits = []
    in_docstring = False
    for line in module_source.splitlines():
        stripped = line.strip()
        if stripped.count('"""') == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        if re.search(r"\.format\s*\(", line):
            hits.append(stripped)
    if hits:
        where = f" در {module_name}" if module_name else ""
        raise AssertionError(
            f"استفاده از .format(){where} ممنوع است؛ از ai.prompt_safe.fill استفاده کنید:\n  "
            + "\n  ".join(hits[:5])
        )
