r"""تزریقِ درون‌خطیِ ریاضی به‌صورت ``<img/>`` داخل ``Paragraph`` گزارش‌لب.

مسئلهٔ اصلی
===========
ReportLab نه LaTeX می‌فهمد و نه BiDi دارد. راهِ طبیعی این است که فرمول را با
matplotlib به PNG تبدیل کنیم و با تگِ ``<img/>`` داخلِ پاراگراف بگذاریم تا خودِ
ReportLab شکستنِ خط و ترازبندی را انجام دهد.

دامِ اصلی
=========
اگر **کلِ** پاراگراف فارسی را یک‌جا از ``arabic_reshaper`` + ``get_display``
بگذرانیم و بعد به ``Paragraph`` بدهیم، رشته‌ای که می‌گیریم از قبل «معکوس» شده
است. ReportLab آن را چپ‌به‌راست می‌شکند، بنابراین:

* خطِ اولِ خروجی با **آخرِ** جمله شروع می‌شود،
* و ترتیبِ خطوط عملاً از پایین به بالا می‌شود.

پس هر پیاده‌سازیِ درستی **باید خطوط را پیش از BiDi بشکند**. این ماژول همین کار
را می‌کند: با همان موتورِ اندازه‌گیریِ :class:`reports.pdf_text_flow.MathRichBlock`
خطوط را می‌شکند، سپس هر خط را به HTMLِ آمادهٔ ``Paragraph`` تبدیل می‌کند که
فرمول‌هایش ``<img/>`` واقعی و نسبت‌ابعادشان دقیق است.

API
===
* :func:`render_math_to_file` — رندر به فایلِ PNGِ موقت (قراردادِ درخواستی).
* :func:`build_mixed_math_text` — یک رشتهٔ HTML با ``<img/>`` و ``<br/>``.
* :func:`build_mixed_math_paragraphs` — همان، به‌صورت ``list[Paragraph]``.
"""
from __future__ import annotations

import atexit
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph

from reports.math_renderer import (
    DEFAULT_COLOR,
    DEFAULT_DPI,
    RenderedMath,
    render_math_png,
)

DEFAULT_FONT_SIZE = 10.5

#: کشِ تصاویر تا یک فرمولِ تکراری (مثلِ گزینه‌های یکسان) دوباره رندر نشود.
_RENDER_CACHE: Dict[Tuple[str, float, int, str], Dict[str, Any]] = {}
_CACHE_LIMIT = 512
_TEMP_FILES: List[str] = []


# ---------------------------------------------------------------------------
# پاک‌سازیِ فایل‌های موقت در پایانِ فرایند
# ---------------------------------------------------------------------------
def _cleanup_temp_files() -> None:
    for path in list(_TEMP_FILES):
        try:
            os.unlink(path)
        except OSError:
            pass
    _TEMP_FILES.clear()


atexit.register(_cleanup_temp_files)


def release_temp_files() -> None:
    """آزادسازیِ دستیِ فایل‌های موقت (برای تست‌ها و فرایندهای طولانی)."""
    _cleanup_temp_files()
    _RENDER_CACHE.clear()


# ---------------------------------------------------------------------------
# گام A — رندرِ LaTeX به فایلِ PNGِ موقت
# ---------------------------------------------------------------------------
def render_math_to_file(
    latex_str: Any,
    font_size: float = DEFAULT_FONT_SIZE,
    color: str = DEFAULT_COLOR,
    dpi: int = DEFAULT_DPI,
) -> Optional[Dict[str, Any]]:
    r"""LaTeX را به یک فایلِ PNGِ شفافِ موقت رندر می‌کند.

    برخلافِ نسخهٔ ساده که با ``plt.text`` کار می‌کند، این تابع از موتورِ
    :mod:`reports.math_renderer` استفاده می‌کند؛ بنابراین:

    * ماتریس‌ها (``\begin{bmatrix}``) هم رندر می‌شوند — ``mathtext`` در ``plt.text``
      از ``\begin`` پشتیبانی نمی‌کند و استثنا می‌دهد،
    * ابعادِ برگشتی **دقیق و برحسب پوینت** هستند (نه تخمینِ ثابتِ ۶۰×۲۰).

    خروجی: ``{"path", "width", "height", "depth"}`` یا ``None`` در صورتِ شکست.
    """
    key = (str(latex_str or ""), float(font_size), int(dpi), str(color))
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        return cached

    rendered: Optional[RenderedMath] = render_math_png(
        latex_str, font_size=font_size, dpi=dpi, color=color
    )
    if rendered is None or not rendered.png:
        return None

    fd, path = tempfile.mkstemp(prefix="fahmyar-math-", suffix=".png")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(rendered.png)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None

    info = {
        "path": path,
        "width": float(rendered.width or 0.0),
        "height": float(rendered.height or 0.0),
        "depth": float(rendered.depth or 0.0),
    }
    _TEMP_FILES.append(path)
    if len(_RENDER_CACHE) >= _CACHE_LIMIT:
        _RENDER_CACHE.clear()
    _RENDER_CACHE[key] = info
    return info


# ---------------------------------------------------------------------------
# گام B — ساختِ HTMLِ پاراگراف با <img/> (خط‌شکنی پیش از BiDi)
# ---------------------------------------------------------------------------
def _esc_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _img_tag(info: Dict[str, Any]) -> str:
    r"""تگِ ``<img/>`` با نسبتِ ابعادِ واقعی و تراز روی خطِ کرسی.

    چهار نکته:

    * ``width``/``height`` هر دو عددی‌اند؛ مقدارِ ``"auto"`` در ReportLab پشتیبانی
      **نمی‌شود** و ``ValueError: could not convert string to float`` می‌دهد.
    * اگر فقط یکی داده شود، ReportLab تصویر را کشیده/فشرده می‌کند؛ بنابراین هر دو
      از :class:`RenderedMath` گرفته می‌شوند تا نسبت حفظ شود.
    * ``valign`` جابه‌جاییِ عمودیِ تصویر نسبت به خطِ کرسی است (مثبت = بالاتر).
      برای این‌که «تهِ» فرمول روی خطِ کرسی بنشیند، به اندازهٔ ``depth`` پایین می‌آید.
    * مسیرِ فایل در ویندوز می‌تواند بک‌اسلش داشته باشد؛ ``src`` را با کوتیشن امن
      می‌کنیم.
    """
    width = max(1.0, float(info["width"]))
    height = max(1.0, float(info["height"]))
    depth = float(info.get("depth") or 0.0)
    src = str(info["path"]).replace('"', "%22")
    return (
        f'<img src="{src}" width="{width:.2f}" height="{height:.2f}" '
        f'valign="{-depth:.2f}"/>'
    )


def _lines_to_html(block) -> List[str]:
    """خطوطِ یک :class:`MathRichBlock` را به HTMLِ چپ‌به‌راست تبدیل می‌کند.

    ``block.lines`` هر خط را به ترتیبِ **منطقی** نگه می‌دارد (راست‌به‌چپ برای فارسی)
    و ReportLab چپ‌به‌راست می‌نویسد؛ پس اتم‌ها باید برعکس شوند.

    .. warning::
       فاصله‌ها به «اتمِ راستِ خود» تعلق ندارند بلکه به **فاصلهٔ میان دو اتم** تعلق
       دارند: ``gap(i-1, i) == atoms[i].space_before``. هنگامِ برعکس‌کردن، فاصلهٔ
       میان ``atoms[i]`` و ``atoms[i+1]`` باید به ``atoms[i+1].space_before`` نگاه
       کند، نه به ``atoms[i].space_before``. اشتباه در این یک واحد، کلمات را به هم
       می‌چسباند و ReportLab دوباره پاراگراف را می‌شکند.
    """
    out: List[str] = []
    for line in getattr(block, "lines", []):
        if line.is_empty:
            out.append("")
            continue
        atoms = list(line.atoms)
        parts: List[str] = []
        # از راست‌ترین اتم به چپ‌ترین؛ فاصله از اتمِ همسایهٔ سمتِ راست می‌آید
        for idx in range(len(atoms) - 1, -1, -1):
            atom = atoms[idx]
            if parts and idx + 1 < len(atoms) and atoms[idx + 1].space_before:
                parts.append(" ")
            if atom.kind == "word":
                parts.append(_esc_html(atom.visual))
                continue
            if atom.rendered is None:
                # رندر شکست خورده و متنِ جایگزین هم نبوده است
                continue
            info = _ensure_file_for_atom(atom)
            if info is None:
                continue
            parts.append(_img_tag(info))
        out.append("".join(parts))
    # حذفِ خطوطِ کاملاً خالیِ لبه‌ای
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _ensure_file_for_atom(atom) -> Optional[Dict[str, Any]]:
    """PNGِ یک اتم را (اگر فقط بایت داشت) روی دیسک می‌نویسد و اطلاعات را برمی‌گرداند."""
    rendered: Optional[RenderedMath] = getattr(atom, "rendered", None)
    if rendered is None or not rendered.png:
        return None
    cached = _RENDER_CACHE.get(("__atom__", id(rendered), 0, ""))
    if cached is not None:
        return cached
    fd, path = tempfile.mkstemp(prefix="fahmyar-atom-", suffix=".png")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(rendered.png)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    info = {
        "path": path,
        "width": float(rendered.width),
        "height": float(rendered.height),
        "depth": float(rendered.depth or 0.0),
    }
    _TEMP_FILES.append(path)
    _RENDER_CACHE[("__atom__", id(rendered), 0, "")] = info
    return info


def _build_block(raw_text: Any, style: ParagraphStyle, max_width: float):
    """یک :class:`MathRichBlock` ساخته و آمادهٔ استخراجِ خطوط می‌کند."""
    from reports.pdf_text_flow import MathRichBlock, repair_control_chars

    fallback = None
    try:  # استخراجِ سبکِ لوکال برای پرهیز از وابستگیِ حلقه‌ای
        from reports.exam_pdf import final_pdf_cleanup

        fallback = final_pdf_cleanup
    except Exception:
        fallback = None

    block = MathRichBlock(
        repair_control_chars(str(raw_text or "")),
        style=style,
        max_width=float(max_width),
        fallback=fallback,
    )
    block.wrap(float(max_width), 10000.0)
    return block


def build_mixed_math_flowables(
    raw_text: Any,
    style: Optional[ParagraphStyle] = None,
    max_width: float = 178 * 2.834645669,
) -> List[Paragraph]:
    """متنِ ترکیبی را به ``Paragraph``هایی با ``<img/>`` درون‌خطی تبدیل می‌کند.

    هر خطِ شکسته‌شده یک ``Paragraph`` جداگانه می‌شود؛ از این‌رو:

    * ترتیبِ خطوط هرگز معکوس نمی‌شود (شکستن پیش از BiDi رخ داده است)،
    * هر پاراگراف از ``split()`` بومیِ ReportLab پشتیبانی می‌کند،
    * تراز و فاصلهٔ سطر از خودِ سبک می‌آید.
    """
    if not str(raw_text or "").strip():
        return []
    _ensure_fonts()
    style = style or _default_style()
    block = _build_block(raw_text, style, max_width)
    lines = _lines_to_html(block)
    if not lines:
        return []
    paragraphs: List[Paragraph] = []
    for html_line in lines:
        if not html_line.strip():
            continue
        try:
            paragraphs.append(Paragraph(html_line or "&nbsp;", style))
        except Exception:
            paragraphs.append(Paragraph("&nbsp;", style))
    return paragraphs


def build_mixed_math_text(
    raw_text: Any,
    font_size: float = DEFAULT_FONT_SIZE,
    max_width: float = 178 * 2.834645669,
) -> str:
    r"""متنِ ترکیبی را به **یک** رشتهٔ HTML با تگ‌های ``<img/>`` تبدیل می‌کند.

    پاراگراف‌های منطقی با ``<br/>`` از هم جدا می‌شوند و هر فرمول به تگِ ``<img/>``
    تبدیل می‌شود؛ یعنی خروجی را می‌توان مستقیم به ``Paragraph`` داد.

    .. note::
       برخلافِ نسخهٔ سادهٔ «اول BiDi، بعد تزریق»، این‌جا خطوط **پیش از** BiDi
       شکسته می‌شوند. اگر کلِ پاراگراف یک‌جا BiDi شود، ReportLab آن را چپ‌به‌راست
       می‌شکند و ترتیبِ خطوط برعکس می‌شود.
    """
    if not str(raw_text or "").strip():
        return ""
    _ensure_fonts()
    from reports.pdf_text_flow import repair_control_chars

    # هر پاراگرافِ منطقی جدا شکسته می‌شود تا مرزهای پاراگراف حفظ شوند
    style = _default_style(font_size=float(font_size))
    chunks = re.split(r"\n{2,}", repair_control_chars(str(raw_text)))
    out: List[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        block = _build_block(chunk, style, max_width)
        lines = _lines_to_html(block)
        if lines:
            out.append("<br/>".join(lines))
    return "<br/><br/>".join(out)


def _ensure_fonts() -> None:
    """اطمینان از ثبتِ قلم‌های فارسی، حتی وقتی این ماژول مستقل استفاده شود.

    ``stringWidth`` پیش از ثبتِ قلم، ``KeyError: no afm found`` می‌دهد؛ بنابراین
    هر ورودیِ عمومیِ این ماژول پیش از هر اندازه‌گیری این تابع را صدا می‌زند.
    """
    try:
        from reports.exam_pdf import _register_fonts

        _register_fonts()
    except Exception:
        pass


def _default_style(font_size: float = DEFAULT_FONT_SIZE) -> ParagraphStyle:
    """سبکِ کمینه برای وقتی که فراخوان سبک نمی‌دهد."""
    _ensure_fonts()
    try:
        from reports.exam_pdf import FONT_REG

        font = FONT_REG
    except Exception:
        font = "Helvetica"
    return ParagraphStyle(
        "math-inline-default",
        fontName=font,
        fontSize=float(font_size),
        leading=float(font_size) * 1.9,
        alignment=TA_RIGHT,
    )


# ---------------------------------------------------------------------------
# کمکی‌های مستقل (بدون وابستگی به MathRichBlock)
# ---------------------------------------------------------------------------
def _shape_word(word: str) -> str:
    return get_display(arabic_reshaper.reshape(word))


def _plain_line_html(atoms: List[Tuple[str, Any]]) -> str:
    """ساختِ HTML از فهرستِ سادهٔ ``("text", s)`` / ``("img", info)``."""
    parts: List[str] = []
    for kind, value in atoms:
        if kind == "text":
            parts.append(_esc_html(_shape_word(str(value))))
        elif kind == "img" and value:
            parts.append(_img_tag(value))
    return "".join(parts)


__all__ = [
    "DEFAULT_FONT_SIZE",
    "render_math_to_file",
    "build_mixed_math_text",
    "build_mixed_math_flowables",
    "release_temp_files",
]
