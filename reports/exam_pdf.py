"""ساخت PDF آزمون با **ReportLab** (Pure Python — بدون هیچ وابستگی به سیستم‌عامل/GTK/DLL).

چینش متن فارسی (چندخطی): متن به‌صورت دستی به خط‌هایی با عرض ثابت شکسته می‌شود
(`stringWidth` روی متنِ reshape‌شده) و سپس هر خط با `arabic_reshaper.reshape` +
`bidi.get_display` آماده می‌شود؛ هر خط یک پاراگراف مجزا و راست‌چین رندر می‌شود.
قلم: Vazirmatn (فایل‌های TTFِ همراه ریپو در assets/fonts).
خروجی: بایت‌های PDF — کاملاً در حافظه، بدون فایل موقت، روی هر سیستم‌عامل.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    _HAS_SVGLIB = True
except Exception:
    svg2rlg = None  # type: ignore[assignment]
    renderPDF = None  # type: ignore[assignment]
    _HAS_SVGLIB = False

try:
    import matplotlib
    matplotlib.use("Agg")  # Headless backend
    import matplotlib.pyplot as plt
    _HAS_MATPLOTLIB = True
except Exception:
    matplotlib = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    _HAS_MATPLOTLIB = False

import arabic_reshaper
from bidi.algorithm import get_display

from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Flowable,
    Image as RLImage,
    KeepTogether,
)

from models.concept import Concept
from models.question import Question
from reports.math_renderer import render_latex_to_image
from reports.pdf_text_flow import (  # noqa: F401  (بازصادراتِ قراردادی)
    OptionsRow,
    build_mixed_flowables,
    has_math,
    math_paragraph_flowables,
    parse_mixed_text_and_math,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = BASE_DIR / "assets" / "fonts"

SUBJECT_LABELS = {
    "math": "ریاضی",
    "physics": "فیزیک",
    "chemistry": "شیمی",
    "biology": "زیست‌شناسی",
    "literature": "ادبیات فارسی",
    "english": "زبان انگلیسی",
    "arabic": "عربی",
}

DIFFICULTY_LABELS = {
    "easy": "آسان",
    "medium": "متوسط",
    "hard": "سخت",
    "challenging": "کنکوری",
    "konkuri": "کنکوری",
    "آسان": "آسان",
    "متوسط": "متوسط",
    "سخت": "سخت",
    "کنکوری": "کنکوری",
    "چالش‌برانگیز": "چالش‌برانگیز",
}

SOURCE_LABELS = {
    "bank": "بانک سؤالات مؤسسات",
    "ai": "تولید هوش مصنوعی",
    "hybrid": "ترکیبی (بانک مؤسسات + هوش مصنوعی)",
}

MAX_TOTAL_QUESTIONS = 60

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

# رنگ‌های هویت بصری (هم‌خوان با UI)
BRAND_DARK = colors.HexColor("#064E3B")
BRAND = colors.HexColor("#047857")
BRAND_ACCENT = colors.HexColor("#10B981")
BRAND_SOFT = colors.HexColor("#ECFDF5")
BRAND_MINT = colors.HexColor("#F0FDF4")
BRAND_LINE = colors.HexColor("#D1FAE5")
BRAND_LINE_SOFT = colors.HexColor("#A7F3D0")
SLATE_900 = colors.HexColor("#0F172A")
SLATE_600 = colors.HexColor("#475569")
SLATE_400 = colors.HexColor("#94A3B8")
SLATE_500 = colors.HexColor("#64748B")
SLATE_50 = colors.HexColor("#F8FAFC")
EMERALD_TEXT = colors.HexColor("#065F46")
TEAL_TEXT = colors.HexColor("#0F766E")
BROWN_TEXT = colors.HexColor("#7C2D12")
AMBER_DARK = colors.HexColor("#92400E")
RED_TEXT = colors.HexColor("#B91C1C")
RED_SOFT = colors.HexColor("#FEF2F2")
RED_LINE = colors.HexColor("#FECACA")

FONT_REG = "Vazirmatn"
FONT_BOLD = "Vazirmatn-Bold"
FONT_XBOLD = "Vazirmatn-XBold"


def to_persian_numbers(text: Any) -> str:
    return str(text).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def final_pdf_cleanup(text: Any) -> str:
    """پاک‌سازیِ **حداقلیِ** متن برای ReportLab — بدون هیچ ترجمهٔ کلمه‌ای.

    این تابع فقط نویزِ متنی را پاک می‌کند و دیگر هیچ فرمولی را به واژه تبدیل نمی‌کند
    (پیش‌تر ``\\frac`` → «به روی» و ``\\sqrt`` → «رادیکال» تبدیل می‌شد — حذف شد).
    فرمول‌ها همیشه پیش از رسیدن به این تابع، با :mod:`reports.math_renderer` به
    تصویر PNG با DPI بالا تبدیل می‌شوند؛ این تابع صرفاً برای متنِ نهایی و برای
    فرمول‌هایی است که (به‌ندرت) رندر تصویری‌شان شکست بخورد.

    خروجی: متن فارسیِ راست‌چین‌پذیر، با ارقام فارسی و بدون نویزِ دلار/بک‌اسلش.
    """
    if not text:
        return ""

    s = str(text)
    # احیای کاراکترهای کنترلی‌ای که JSON خورده است (\b در \begin و \f در \frac)
    s = s.replace("\x08", r"\b").replace("\x0c", r"\f")

    # 1. ماتریس‌ها: سلول‌ها با « | » و « , » تا ساختار دوبعدی خوانا بماند
    def matrix_sub(m: re.Match) -> str:
        content = m.group(1).replace(r"\\", " | ").replace("&", " , ")
        return f"[ {content} ]"

    s = re.sub(
        r"\\?begin\s*\{(?:[bpvBV]?matrix|array|cases|aligned)\}(.*?)\\?end\s*\{(?:[bpvBV]?matrix|array|cases|aligned)\}",
        matrix_sub,
        s,
        flags=re.DOTALL,
    )

    # 2. حذف کاملِ نشانه‌های LaTeX (نه ترجمهٔ کلمه‌ای)
    s = re.sub(r"\\?sqrt\s*\[([^\[\]]+)\]\s*\{([^}]+)\}", r"\2", s)   # ریشهٔ n‌ام → رادیکاند
    s = re.sub(r"\\?sqrt\s*\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\?(?:vec|overrightarrow|overline|hat)\s*\{([^}]+)\}", r"\1", s)
    for _ in range(4):
        next_s = re.sub(r"\\?(?:d|t)?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"\1/\2", s)
        if next_s == s:
            break
        s = next_s
    s = re.sub(r"\\?(?:left|right)\b", "", s)
    s = re.sub(r"\\?(?:circ|degree)\b", "°", s)
    s = re.sub(r"\\?(?:times|cdot)\b", "×", s)
    s = re.sub(r"\\?(?:neq|ne)\b", "≠", s)
    s = re.sub(r"\\?(?:leq|le)\b", "≤", s)
    s = re.sub(r"\\?(?:geq|ge)\b", "≥", s)
    s = re.sub(r"\\?(?:rightarrow|to)\b", "→", s)
    s = re.sub(r"\\?infty\b", "∞", s)
    s = re.sub(r"\\?(?:alpha|beta|gamma|theta|lambda|mu|pi|sigma|omega)\b", "", s)

    # 3. حذف دستورات و نمادهای باقی‌ماندهٔ LaTeX
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[\$\\\{\}\^_]", " ", s)

    # 4. ارقام فارسی
    s = s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

    # 5. یکدست‌سازی فاصله‌ها
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


# نام‌های مستعار برای سازگاری با سایر بخش‌ها (مسیر متنیِ fallback)
latex_to_persian_text = final_pdf_cleanup

#: دیگر «متنِ بی‌ریاضی» ساخته نمی‌شود — نام قدیمی به موتور رندر تصویری اشاره می‌کند.
clean_latex_for_pdf = final_pdf_cleanup


def get_pdf_safe_text(text: Any) -> str:
    """Prepares text for ReportLab by cleaning, reshaping, and bidi-processing."""
    if not text:
        return ""
    # Step A: Clean LaTeX and symbols FIRST
    cleaned = final_pdf_cleanup(str(text))
    # Step B: Reshape Persian characters
    reshaped_str = arabic_reshaper.reshape(cleaned)
    # Step C: Apply Bidi for RTL direction
    return get_display(reshaped_str)


def _fa(value: Any) -> str:
    return to_persian_numbers(str(value))


def _fa_date() -> str:
    try:
        import jdatetime

        return to_persian_numbers(jdatetime.date.today().strftime("%Y/%m/%d"))
    except Exception:
        from datetime import date

        return to_persian_numbers(date.today().strftime("%Y/%m/%d"))


def prepare_farsi_text(text: str) -> str:
    """متن فارسی را برای رندر در ReportLab با get_pdf_safe_text آماده می‌کند."""
    return get_pdf_safe_text(text)


def reshaped(text: Any) -> str:
    """نام مستعار — همهٔ متون ReportLab از مسیر امن get_pdf_safe_text عبور می‌کنند."""
    return get_pdf_safe_text(str(text or ""))


_COMPLEX_LATEX_RE = re.compile(
    r"(?:\\+)?(?:(?:d|t)?frac\s*\{|sqrt\s*[\[\{]|begin\s*\{[bpvBV]?matrix\})"
)
_MATH_DELIM_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$]+\$")


def latex_to_pdf_image(latex_str: str, dpi: int = 200) -> Optional[RLImage]:
    r"""تبدیل یک عبارت LaTeX (مثل $ \frac{a}{b} $، $ \sqrt{2} $ یا bmatrix) به تصویر ReportLab.

    از موتور mathtext کتابخانهٔ matplotlib استفاده می‌کند (بدون نیاز به نصب LaTeX/TeX Live)
    تا کسرها، رادیکال‌ها و ماتریس‌ها به‌صورت **واقعی** و برداری‌گونه رندر شوند.
    """
    try:
        return render_latex_to_image(latex_str, dpi=max(150, int(dpi)), font_size=11.0)
    except Exception:
        return None


def _extract_complex_math_images(raw_text: Any, max_width_pt: float = 180.0) -> list[RLImage]:
    r"""اگر متن حاوی فرمول پیچیدهٔ LaTeX (\frac, \sqrt, \begin{bmatrix}) باشد، تصاویر RLImage متناظر را می‌سازد."""
    if not raw_text or not _HAS_MATPLOTLIB:
        return []
    s = str(raw_text).replace("\x08", "\\b").replace("\x0c", "\\f")
    if not _COMPLEX_LATEX_RE.search(s):
        return []

    blocks = [m.group(0) for m in _MATH_DELIM_RE.finditer(s) if _COMPLEX_LATEX_RE.search(m.group(0))]
    if not blocks:
        # اگر بدون علامت $ نوشته شده بود، کل عبارت پیچیده را استخراج کن
        m_mat = re.search(
            r"(?:\\+)?begin\s*\{[bpvBV]?matrix\}[\s\S]*?(?:\\+)?end\s*\{[bpvBV]?matrix\}",
            s,
        )
        if m_mat:
            blocks.append(m_mat.group(0))
        else:
            for m_cmd in re.finditer(
                r"(?:\\+)?(?:(?:d|t)?frac\s*\{[^{}]+\}\s*\{[^{}]+\}|sqrt\s*(?:\[[^\[\]]+\])?\s*\{[^{}]+\})",
                s,
            ):
                blocks.append(m_cmd.group(0))

    images: list[RLImage] = []
    for blk in blocks[:4]:
        img = latex_to_pdf_image(blk)
        if img is not None:
            if float(img.drawWidth) > max_width_pt and float(img.drawWidth) > 0:
                ratio = max_width_pt / float(img.drawWidth)
                img.drawWidth = float(img.drawWidth) * ratio
                img.drawHeight = float(img.drawHeight) * ratio
            images.append(img)
    return images



def _esc_xml(visual: str) -> str:
    return visual.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_rtl_lines(text: Any, font: str, size: float, max_width: float) -> list[str]:
    """شکستن دستیِ متن به خط‌هایی که در max_width (واحد: پوینت) جا می‌شوند.

    اندازه‌گیری عرض روی متنِ reshape‌شده انجام می‌شود تا حروف پیوسته درست سنجیده شوند.
    """
    words = str(text or "").split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if not current or stringWidth(reshaped(trial), font, size) <= max_width:
            current = trial
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def rtl_flowables(
    text: Any,
    style: ParagraphStyle,
    max_width_mm: float,
    render_math: bool = True,
) -> list[Flowable]:
    """متن فارسی (به‌همراه فرمول‌های ریاضیِ تصویری) را به Flowableهای راست‌چین تبدیل می‌کند.

    اگر متن شامل ``$...$`` یا ``$$...$$`` یا دستور LaTeXِ بدون دلار باشد، هر فرمول با
    matplotlib به تصویر شفاف رندر و در جریان متن جای‌گذاری می‌شود (کسر و رادیکال واقعی).
    در غیر این صورت همان مسیر متنیِ سبک انتخاب می‌شود.
    """
    if render_math and has_math(text):
        return math_paragraph_flowables(
            str(text),
            style=style,
            max_width=max_width_mm * mm - 18,
            fallback=final_pdf_cleanup,
        )
    text = final_pdf_cleanup(text)
    font = style.fontName or FONT_REG
    size = style.fontSize
    # حاشیهٔ اطمینان: اندازه‌گیری ما با اندکی خطا نسبت به چینش داخلی ReportLab انجام می‌شود؛
    # کوچک‌تر گرفتن عرض، شکستن‌های تصادفیِ خط آخر را جلوگیری می‌کند.
    max_width = max_width_mm * mm - 18
    out: list[Paragraph] = []
    for line in _split_rtl_lines(text, font, size, max_width):
        out.append(Paragraph(_esc_xml(reshaped(line)), style))
    return out


# ---------------------------------------------------------------------------
# ثبت قلم‌ها (یک‌بار)
# ---------------------------------------------------------------------------
_FONTS_READY = False


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular = FONT_DIR / "Vazirmatn-Regular.ttf"
    bold = FONT_DIR / "Vazirmatn-Bold.ttf"
    xbold = FONT_DIR / "Vazirmatn-ExtraBold.ttf"
    for path in (regular, bold, xbold):
        if not path.exists():
            raise RuntimeError(f"فایل فونت یافت نشد: {path}")
    pdfmetrics.registerFont(TTFont(FONT_REG, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    pdfmetrics.registerFont(TTFont(FONT_XBOLD, str(xbold)))
    pdfmetrics.registerFontFamily(FONT_REG, normal=FONT_REG, bold=FONT_BOLD, italic=FONT_REG, boldItalic=FONT_BOLD)
    _FONTS_READY = True


def _style(name: str, **kwargs) -> ParagraphStyle:
    base = dict(fontName=FONT_REG, fontSize=10.5, leading=22, alignment=TA_RIGHT, textColor=SLATE_900)
    base.update(kwargs)
    return ParagraphStyle(name, **base)


# ---------------------------------------------------------------------------
# Flowableهای سفارشی
# ---------------------------------------------------------------------------
class RoundedBanner(Flowable):
    """عنوان اصلی روی پس‌زمینهٔ سبز روشن با گوشه‌های گرد (اندازهٔ قلم تطبیقی)."""

    def __init__(self, text: str, height: float = 20 * mm):
        super().__init__()
        self.text = text
        self.height = height

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(BRAND_SOFT)
        c.setStrokeColor(colors.HexColor("#059669"))
        c.setLineWidth(2.2)
        c.roundRect(0, 0, self.width, self.height, 7 * mm, fill=1, stroke=1)
        c.setFillColor(BRAND_DARK)
        size = 17.5
        visual = reshaped(self.text)
        while size > 9 and stringWidth(visual, FONT_XBOLD, size) > self.width - 18 * mm:
            size -= 1
        c.setFont(FONT_XBOLD, size)
        c.drawCentredString(self.width / 2, self.height / 2 - size * 0.37, visual)
        c.restoreState()


class DottedLine(Flowable):
    """خطِ چین‌دارِ پاسخ‌نویسی."""

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, 8.2 * mm

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(SLATE_400)
        c.setLineWidth(0.8)
        c.setDash(1, 2.6)
        c.line(0, 5.5 * mm, self.width, 5.5 * mm)
        c.restoreState()


class SvgDiagramFlowable(Flowable):
    """رندر ایمنِ نمودار SVG روی کانواس PDF با استفاده از svglib + renderPDF."""

    def __init__(self, drawing: Any, pad_mm: float = 2.0):
        super().__init__()
        self.drawing = drawing
        self.pad = pad_mm * mm
        self.width = float(getattr(drawing, "width", 100.0))
        self.height = float(getattr(drawing, "height", 60.0)) + 2 * self.pad

    def wrap(self, availWidth, availHeight):
        self.avail_width = availWidth
        return availWidth, self.height

    def draw(self):
        if not _HAS_SVGLIB or renderPDF is None or self.drawing is None:
            return
        try:
            c = self.canv
            c.saveState()
            avail_w = getattr(self, "avail_width", self.width)
            x_offset = max(0.0, (avail_w - float(self.drawing.width)) / 2.0)
            renderPDF.draw(self.drawing, c, x_offset, self.pad)
            c.restoreState()
        except Exception:
            pass


def _svg_flowable(
    svg_text: Optional[str],
    max_width_mm: float = 110.0,
    max_height_mm: float = 52.0,
) -> Optional[Flowable]:
    """در صورت وجود SVG معتبر و نصب بودن svglib، آن را در فایل موقت ذخیره کرده، مقیاس می‌دهد و Flowable برمی‌گرداند."""
    if not svg_text or not isinstance(svg_text, str) or "<svg" not in svg_text.lower():
        return None
    if not _HAS_SVGLIB or svg2rlg is None or renderPDF is None:
        return None

    tmp_path: Optional[str] = None
    try:
        # آماده‌سازی متن‌های فارسی داخل تگ <text> برای نمایش درست در svglib
        def _reshape_svg_text(m: re.Match) -> str:
            open_t, inner, close_t = m.group(1), m.group(2), m.group(3)
            if re.search(r"[\u0600-\u06FF]", inner):
                inner = prepare_farsi_text(inner)
            open_t = re.sub(r"font-family\s*=\s*['\"][^'\"]*['\"]", 'font-family="Vazirmatn"', open_t)
            return f"{open_t}{inner}{close_t}"

        prepared_svg = re.sub(
            r"(<text\b[^>]*>)([^<]*)(</text>)",
            _reshape_svg_text,
            svg_text.strip(),
            flags=re.IGNORECASE,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", encoding="utf-8", delete=False) as tmp:
            tmp.write(prepared_svg)
            tmp.flush()
            tmp_path = tmp.name

        drawing = svg2rlg(tmp_path)
        if drawing is None:
            return None
        dw = float(getattr(drawing, "width", 0.0) or 0.0)
        dh = float(getattr(drawing, "height", 0.0) or 0.0)
        if dw <= 0 or dh <= 0:
            return None

        max_w = max_width_mm * mm
        max_h = max_height_mm * mm
        scale = min(max_w / dw, max_h / dh, 1.0)
        drawing.width = dw * scale
        drawing.height = dh * scale
        drawing.scale(scale, scale)
        return SvgDiagramFlowable(drawing)
    except Exception:
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass



class NumberedCanvas(canvas.Canvas):
    """کانواس دوگذری برای نوشتن «صفحه X از Y» در پاورقی همهٔ صفحات."""

    footer_label = "آزمون کنکوری"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):  # noqa: N802 (نام API مربوط به reportlab)
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        self.saveState()
        self.setFont(FONT_REG, 8)
        self.setFillColor(SLATE_500)
        text = reshaped(f"فهم‌یار · {self.footer_label} — صفحهٔ {_fa(self._pageNumber)} از {_fa(total)}")
        self.drawCentredString(A4[0] / 2, 8 * mm, text)
        self.restoreState()



GRADE_FA = {"10": "دهم", "11": "یازدهم", "12": "دوازدهم", "comprehensive": "جامع (دهم تا دوازدهم)"}
OPTION_LETTERS = ["الف", "ب", "ج", "د"]


def _grade_label(grade: Any) -> str:
    if grade is None:
        return "—"
    key = str(grade).strip()
    if key in GRADE_FA:
        return f"پایهٔ {GRADE_FA[key]}"
    return f"پایهٔ {_fa(key)}" if key else "—"


def _question_header(item: dict[str, Any], tag: str = "سؤال") -> Paragraph:
    """خطِ سربرگِ سؤال — پاراگرافِ تکی با پس‌زمینه و کادرِ نرم (بدون جدول)."""
    style = _style(
        "q-head",
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=19,
        textColor=TEAL_TEXT,
        alignment=TA_RIGHT,
        backColor=SLATE_50,
        borderWidth=0.6,
        borderColor=BRAND_LINE,
        borderPadding=5,
        borderRadius=3,
    )
    head_parts = [f"{tag} {_fa(item['order'])}"]
    if tag == "سؤال":
        subj = str(item.get("subject") or "").strip()
        diff = str(item.get("difficulty") or "").strip()
        if subj:
            head_parts.append(subj)
        if diff:
            head_parts.append(f"سطح: {DIFFICULTY_LABELS.get(diff, diff)}")
    return Paragraph(_esc_xml(reshaped(" · ".join(head_parts))), style)

# ---------------------------------------------------------------------------
# انتخاب سؤال‌ها
# ---------------------------------------------------------------------------
def _as_str_list(value: Any, limit: int = 4) -> list[str]:
    if isinstance(value, dict):
        items = list(value.keys())
    elif isinstance(value, list):
        items = value
    elif isinstance(value, str) and value.strip():
        items = [value]
    else:
        items = []
    return [str(v) for v in items[:limit]]


def _question_dict(q: Question, subject: str, origin: str) -> dict[str, Any]:
    rubric = q.rubric if isinstance(q.rubric, dict) else {}
    mism = q.mapped_misconceptions if isinstance(q.mapped_misconceptions, list) else []
    return {
        "subject": subject,
        "text": (q.text or "").strip(),
        "difficulty": q.difficulty or "medium",
        "question_type": q.question_type or "conceptual",
        "correct_reasoning": (rubric.get("correct_reasoning") or "").strip()
        or "پاسخ‌نامه برای این سؤال ثبت نشده است؛ معلم محترم پاسخ مرجع را تکمیل کند.",
        "misconception_indicators": _as_str_list(rubric.get("misconception_indicators"), 3),
        "partial_credit_signs": _as_str_list(rubric.get("partial_credit_signs"), 3),
        "mapped_misconceptions": [str(m) for m in mism[:3]],
        "origin": origin,
        "question_id": q.id,
    }


def _bank_questions(db: Session, subject: str, wanted_difficulty: str, limit: int) -> list[Question]:
    if limit <= 0:
        return []
    concepts = db.query(Concept.id).filter(Concept.subject == subject).all()
    concept_ids = [c[0] for c in concepts]
    if not concept_ids:
        return []

    from sqlalchemy import case

    base = db.query(Question).filter(Question.concept_id.in_(concept_ids))
    approved_first = case((Question.approval_status == "approved", 0), else_=1)

    picked: list[Question] = []
    exact = (
        base.filter(Question.difficulty == wanted_difficulty)
        .order_by(approved_first, Question.created_at.desc())
        .limit(limit)
        .all()
    )
    picked.extend(exact)
    if len(picked) < limit:
        excluded = [q.id for q in picked] or [-1]
        rest = (
            base.filter(Question.id.notin_(excluded))
            .order_by(approved_first, Question.created_at.desc())
            .limit(limit - len(picked))
            .all()
        )
        picked.extend(rest)
    return picked


def _ai_question(subject: str, wanted_difficulty: str) -> Optional[dict[str, Any]]:
    """یک سؤال تشخیصی از مدل فعال (در این محیط: Mock آفلاین) می‌سازد؛ در خطا None."""
    try:
        import asyncio
        import json

        from ai.model_abstraction import ModelRouter

        prompt = (
            f"PROPOSITION: گزارهٔ کلیدیِ درس {SUBJECT_LABELS.get(subject, subject)} (پایه و کنکوری)\n"
            f"MISCONCEPTION: رایج‌ترین بدفهمیِ دانش‌آموزان در {SUBJECT_LABELS.get(subject, subject)}\n"
            f"CONCEPT: {SUBJECT_LABELS.get(subject, subject)} — سطح {DIFFICULTY_LABELS.get(wanted_difficulty, wanted_difficulty)}\n"
            "یک سؤال عمیقِ تشریحیِ مدرسه‌ای با زیرمتن مفهومی (نه حفظی) طرح کن. فقط JSON برگردان."
        )

        provider = ModelRouter().get_provider("generate_question")
        response = asyncio.run(provider.generate(prompt, "generate_question", temperature=0.8))
        raw = (response.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            payload = json.loads(match.group(0)) if match else None
        if not isinstance(payload, dict):
            return None
        text = (payload.get("question_text") or "").strip()
        if not text:
            return None
        rubric = payload.get("rubric") if isinstance(payload.get("rubric"), dict) else {}
        return {
            "subject": subject,
            "text": text,
            "difficulty": wanted_difficulty,
            "question_type": payload.get("question_type") or "conceptual",
            "correct_reasoning": (rubric.get("correct_reasoning") or "").strip()
            or "پاسخ مرجع برای این سؤال ثبت نشده است؛ معلم محترم پاسخ تشریحی را تکمیل کند.",
            "misconception_indicators": _as_str_list(rubric.get("misconception_indicators"), 3),
            "partial_credit_signs": _as_str_list(rubric.get("partial_credit_signs"), 3),
            "mapped_misconceptions": [str(m) for m in (payload.get("mapped_misconceptions") or [])[:3]],
            "origin": "ai",
            "question_id": None,
        }
    except Exception:
        return None


def gather_questions(
    db: Session,
    subjects: list[str],
    counts: dict[str, int],
    difficulty: str,
    source: str,
    bank_share: int = 60,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """سؤال‌های دفترچه را جمع می‌کند. خروجی: (لیست سؤال‌های مرتب‌شده، متادیتای صادقانه)."""
    wanted = {"challenging": "hard"}.get(difficulty, difficulty if difficulty in ("easy", "medium", "hard") else "medium")
    selected: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"per_subject": {}, "shortfalls": {}, "ai_used": 0, "bank_used": 0}

    for subject in subjects:
        want = max(0, min(30, int(counts.get(subject) or 0)))
        if want <= 0:
            continue

        bank_take = 0
        if source == "bank":
            bank_take = want
        elif source == "hybrid":
            bank_take = max(1, round(want * (max(10, min(90, bank_share)) / 100))) if want > 1 else 1

        bank = _bank_questions(db, subject, wanted, bank_take)
        picked = [_question_dict(q, subject, "bank") for q in bank]

        ai_needed = want - len(picked)
        ai_made = 0
        while len(picked) < want and ai_made < ai_needed:
            item = _ai_question(subject, wanted)
            if item is None:
                break
            picked.append(item)
            ai_made += 1

        if len(picked) < want:
            meta["shortfalls"][subject] = want - len(picked)
        meta["per_subject"][subject] = len(picked)
        meta["ai_used"] += ai_made
        meta["bank_used"] += len(bank)
        selected.extend(picked)

    selected = selected[:MAX_TOTAL_QUESTIONS]
    for i, item in enumerate(selected, start=1):
        item["order"] = i
    return selected, meta


# ---------------------------------------------------------------------------
# ساخت اجزای سند
# ---------------------------------------------------------------------------
PAGE_W = 178 * mm  # عرض محتوا (A4 - حاشیه‌ها)


def _section_banner(text: str, accent=BRAND_ACCENT, bg=BRAND_SOFT, fg=BRAND_DARK) -> Table:
    p = Paragraph(_esc_xml(reshaped(text)), _style("banner", fontName=FONT_XBOLD, fontSize=12.5, textColor=fg, alignment=TA_RIGHT, leading=20))
    t = Table([[p]], colWidths=[PAGE_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), bg),
                ("LINEAFTER", (0, 0), (0, 0), 4.5, accent),
                ("TOPPADDING", (0, 0), (0, 0), 6),
                ("BOTTOMPADDING", (0, 0), (0, 0), 6),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
            ]
        )
    )
    return t


def _meta_table(rows: list[tuple[str, str]]) -> Table:
    data = []
    for label, value in rows:
        # ستون‌های ReportLab چپ→راست چیده می‌شوند؛ برای چیدمان راست‌به‌چپ، برچسب سمتِ راست قرار می‌گیرد
        value_flow: list[Flowable]
        if value:
            value_flow = rtl_flowables(value, _style("meta-v", alignment=TA_RIGHT, leading=19), 124 - 18)
        else:
            value_flow = [Paragraph("&nbsp;", _style("meta-v-empty"))]
        label_flow = rtl_flowables(label, _style("meta-k", fontName=FONT_BOLD, textColor=EMERALD_TEXT, alignment=TA_RIGHT, leading=19), 54 - 14)
        data.append([value_flow, label_flow])
    t = Table(data, colWidths=[124 * mm, 54 * mm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, BRAND_LINE_SOFT),
                ("BACKGROUND", (1, 0), (1, -1), BRAND_SOFT),
                ("BACKGROUND", (0, 0), (0, -1), SLATE_50),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def _instruction_box() -> Table:
    items: list[Flowable] = rtl_flowables("دستورالعمل آزمون:", _style("ins-t", fontName=FONT_XBOLD, textColor=EMERALD_TEXT, leading=20), 178 - 20)
    bullets = [
        "هر سؤال فقط یک گزینهٔ صحیح دارد؛ بیش از یک گزینه علامت نزنید.",
        "پاسخ‌ها را فقط با علامت ضربدر (×) در گزیدهٔ پاسخنامه علامت بزنید و از خط‌خوردگیِ زیاد خودداری کنید.",
        "همراه داشتن جزوه، کتاب و هرگونه ابزار هوشمند ممنوع است.",
        "حتماً پاسخنامه را مطابق با شمارهٔ سؤال پر کنید؛ ابهام در گزیدهٔ پاسخنامه به سودِ شما نیست.",
    ]
    for b in bullets:
        items += rtl_flowables(f"• {b}", _style("ins-b", fontSize=9.5, leading=19, textColor=colors.HexColor("#1F2937")), 178 - 20)
    t = Table([[items]], colWidths=[PAGE_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), BRAND_MINT),
                ("BOX", (0, 0), (0, 0), 1.0, BRAND_ACCENT),
                ("TOPPADDING", (0, 0), (0, 0), 7),
                ("BOTTOMPADDING", (0, 0), (0, 0), 7),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
            ]
        )
    )
    return t


def _option_text(text: str, index: int) -> str:
    """متن گزینه با برچسب فارسی (الف/ب/ج/د)."""
    label = OPTION_LETTERS[index]
    return f"{label}) {str(text or '').strip()}"


def _option_style(index: int) -> ParagraphStyle:
    return _style(f"opt-{index}", fontSize=9.5, leading=18)


def _options_table(item: dict[str, Any]) -> "OptionsRow":
    """گزینه‌های چهارگانه در یک ردیفِ تمام‌عرض، از راست به چپ (الف → د).

    هر گزینه یک بلوکِ ریاضی‌فهم است؛ فرمول‌ها به تصویرِ واقعی (کسر/رادیکال/بردار) تبدیل می‌شوند.
    """
    opts = list(item["options"])
    cells = [(_option_text(opts[i], i), _option_style(i)) for i in range(4)]
    return OptionsRow(cells, width=178 * mm, fallback=final_pdf_cleanup)


def _question_flow(item: dict[str, Any], with_lines: bool = True) -> list[Flowable]:
    """سؤال کنکوری: سربرگ + متن با فرمول‌های تصویری (fallback: final_pdf_cleanup) + شکل SVG + چهار گزینه."""
    story: list[Flowable] = [_question_header(item)]
    raw_text = item.get("text") or item.get("question_text") or item.get("title") or ""
    story += rtl_flowables(raw_text, _style("q-text", fontSize=10.5, leading=21, fontName=FONT_BOLD), 178)
    svg_flow = _svg_flowable(item.get("diagram_svg"))
    if svg_flow is not None:
        story.append(Spacer(1, 1.5 * mm))
        story.append(svg_flow)
    story.append(Spacer(1, 1.5 * mm))
    story.append(_options_table(item))
    story.append(Spacer(1, 4.5 * mm))
    # سؤال هرگز بین دو صفحه تکه نمی‌شود (سربرگ تنها در پایین صفحه نمی‌ماند)
    return [KeepTogether(story)]


def _answer_flow(item: dict[str, Any]) -> list[Flowable]:
    """بلوکِ کلیدِ هر سؤال — شماره، گزینهٔ صحیح (با حرف)، استدلال کوتاه؛ بدون هیچ تگ منبعی."""
    ca = int(item["correct_answer"])
    letter = OPTION_LETTERS[ca - 1]
    story: list[Flowable] = [_question_header(item, tag="کلید")]
    raw_text = str(item.get("text") or item.get("question_text") or item.get("title") or "")
    # پیش‌نمایش کوتاه اما با فرمول‌های تصویری (بدون تبدیل متنیِ «به روی»)
    preview = raw_text if len(raw_text) <= 160 else raw_text[:157] + "…"
    story += rtl_flowables(preview, _style("ak-prev", fontSize=9, leading=17, textColor=SLATE_600), 178)
    story.append(Spacer(1, 1.5 * mm))
    story += rtl_flowables(f"پاسخ صحیح: گزینهٔ {_fa(ca)} - {letter}", _style("ak-key", fontName=FONT_XBOLD, fontSize=11, textColor=BRAND_DARK, leading=20), 178, render_math=False)
    raw_explanation = (item.get("explanation") or "").strip()
    if raw_explanation:
        story += rtl_flowables(raw_explanation, _style("ak-a", fontSize=9, leading=18, textColor=colors.HexColor("#1F2937")), 178)
    else:
        story += rtl_flowables("استدلال تشریحی برای این سؤال در سامانه ثبت نشده است.", _style("ak-a-empty", fontSize=8.5, leading=17, textColor=SLATE_500), 178)
    story.append(Spacer(1, 4 * mm))
    return [KeepTogether(story)]


def _correction_flow(items: list[dict[str, Any]]) -> list[Flowable]:
    """راهنمای کیفی برای دبیر — جمع‌بندی و آسیب‌شناسی، بدون نمره‌دهی عددی (ECD)."""
    blocks: list[Flowable] = rtl_flowables(
        "این آزمون چهارگزینه‌ای و کیفی است؛ ثبتِ «درستی/نادرستیِ» هر سؤال — نه نمرهٔ عددی — ملاک است. "
        "مقایسهٔ دانش‌آموزان با یکدیگر ممنوع است. هدف از اجرای آزمون، شناساییِ الگویِ بدفهمیِ هر دانش‌آموز در مبحثِ مورد نظر است.",
        _style("chg-intro", fontSize=9.5, leading=19, textColor=colors.HexColor("#1F2937")),
        178,
    )
    blocks.append(Spacer(1, 2 * mm))
    blocks += rtl_flowables("• هر سؤالِ نادرست را به یکی از این ریشه‌ها نسبت دهید: «بدفهمیِ مفهومی»، «خطای محاسباتی»، «بی‌دقتی در خواندن سؤال»، «ندانستن مطلب».", _style("chg-a", fontSize=9, leading=18), 178)
    blocks += rtl_flowables("• بدون مقایسه با همکلاسی‌ها، فقط به خودِ دانش‌آموز بگویید کدام مبحث/دام اشتباه تکرار شده است.", _style("chg-b", fontSize=9, leading=18), 178)
    blocks += rtl_flowables("• سؤال‌هایی که بیش از نصف کلاس در آن‌ها غلط زده‌اند، شاخصِ «شکافِ آموزشی» هستند؛ آن مبحث را در جلسهٔ بعد مرور کنید.", _style("chg-c", fontSize=9, leading=18), 178)
    blocks += rtl_flowables("• برای گزارشِ هر دانش‌آموز، وضعیت هر سؤال را «کامل / نسبی / ناقص» ثبت کنید و از هرگونه نمرهٔ عددی یا رتبه‌بندی گروهی خودداری کنید.", _style("chg-d", fontSize=9, leading=18), 178)
    blocks.append(Spacer(1, 2 * mm))
    return blocks


def _answer_sheet_table(items: list[dict[str, Any]]) -> Table:
    """جدول پاسخنامهٔ کنکوری — هر سؤال یک ردیف، چهار چک‌باکسه (۱ تا ۴)."""
    header_num = Paragraph(_esc_xml(reshaped("شمارهٔ سؤال")), _style("as-h1", fontName=FONT_XBOLD, textColor=colors.white, alignment=TA_CENTER, leading=17))
    headers = [Paragraph(_esc_xml(reshaped(_fa(n))), _style(f"as-h{n}", fontName=FONT_XBOLD, textColor=colors.white, alignment=TA_CENTER, leading=17)) for n in (4, 3, 2, 1)]
    data = [[*headers, header_num]]  # چیدمان راست→چپ: شماره، ۱، ۲، ۳، ۴
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.7, BRAND_LINE_SOFT),
        ("BACKGROUND", (4, 1), (4, -1), SLATE_50),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, item in enumerate(items, start=1):
        num = Paragraph(_esc_xml(reshaped(_fa(item["order"]))), _style("as-n", alignment=TA_CENTER, leading=20, fontName=FONT_BOLD))
        data.append([Paragraph("&nbsp;", _style("as-b", alignment=TA_CENTER, leading=20)) for _ in range(4)] + [num])
        # چک‌باکس هر گزینه: کادرِ تو گذاری در همان سلول
        for col in range(4):
            style_cmds.append(("BOX", (col, i), (col, i), 0.9, colors.HexColor("#94A3B8")))
    t = Table(data, colWidths=[18 * mm, 18 * mm, 18 * mm, 18 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle(style_cmds))
    return t

# ---------------------------------------------------------------------------
# ساخت PDF — خروجی بایت‌ها
# ---------------------------------------------------------------------------
def build_exam_pdf(
    school_name: str,
    title: str,
    questions: list[dict[str, Any]],
    duration_minutes: int,
    difficulty: str,
    grade: Any = None,
    major: Optional[str] = None,
    subject_label: str = "",
    topic: str = "",
) -> bytes:
    """PDF نهایی از لیستِ سؤال‌های کنکوریِ تأییدشده — تگِ منبع (source_tag) مطلقاً چاپ نمی‌شود."""
    _register_fonts()

    diff_label = DIFFICULTY_LABELS.get(difficulty, difficulty)
    total = len(questions)
    stamp = _fa_date()
    grade_fa = _grade_label(grade)
    major_label = (major or "").strip() or "—"
    subject_fa = (subject_label or "").strip() or "کنکور"
    topic_fa = (topic or "").strip() or "—"

    from io import BytesIO

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title=title or "آزمون کنکوری — فهم‌یار",
        author="فهم‌یار",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="frame")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])

    story: list[Flowable] = []

    # ── سربرگ استاندارد ──
    story += rtl_flowables(school_name, _style("school", fontName=FONT_XBOLD, fontSize=13, textColor=colors.HexColor("#0F5132"), alignment=TA_CENTER, leading=21), 178)
    story += rtl_flowables("«فهم‌یار» — سامانهٔ تشخیصی فهمِ مفهومی", _style("school-sub", alignment=TA_CENTER, fontSize=8.5, leading=16, textColor=SLATE_500), 178)
    story.append(Spacer(1, 3 * mm))
    story.append(RoundedBanner(title or "آزمون کنکوری — فهم‌یار"))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _meta_table(
            [
                ("نام و نام خانوادگی", ""),
                ("پایه", grade_fa),
                ("رشته", major_label),
                ("درس", subject_fa),
                ("مبحث", topic_fa),
                ("تعداد سؤال‌ها", f"{_fa(total)} سؤال چهارگزینه‌ای"),
                ("زمان آزمون", f"{_fa(duration_minutes)} دقیقه"),
                ("سطح سختی", diff_label),
                ("تاریخ برگزاری", stamp),
            ]
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(_instruction_box())
    story.append(Spacer(1, 4 * mm))

    # ── بخش ۱ — دفترچه سؤالات (گزینه‌ها در دو ستون، بدون تگ منبع) ──
    story.append(_section_banner("بخش ۱ — دفترچهٔ سؤالات"))
    story.append(Spacer(1, 3.5 * mm))
    for item in questions:
        story += _question_flow(item)

    # ── جدول پاسخنامه (گزیدهٔ ۱ تا ۴) ──
    story.append(Spacer(1, 1 * mm))
    story.append(_section_banner("جدول پاسخنامهٔ دانش‌آموز", accent=colors.HexColor("#0EA5E9"), bg=colors.HexColor("#F0F9FF"), fg=colors.HexColor("#0C4A6E")))
    story.append(Spacer(1, 3 * mm))
    story.append(_answer_sheet_table(questions))

    # ── بخش ۲ (صفحهٔ آخر) — پاسخنامهٔ کلید آزمون ──
    story.append(PageBreak())
    secret_p = Paragraph(_esc_xml(reshaped("مختص دبیر محترم — پاسخنامهٔ کلید آزمون (هرگز در اختیار دانش‌آموز قرار نگیرد)")), _style("secret", fontName=FONT_XBOLD, fontSize=9.5, textColor=RED_TEXT, alignment=TA_CENTER, leading=18))
    secret = Table([[secret_p]], colWidths=[PAGE_W])
    secret.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), RED_SOFT),
        ("BOX", (0, 0), (0, 0), 1.0, RED_LINE),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 0), (0, 0), 6),
    ]))
    story.append(secret)
    story.append(Spacer(1, 4 * mm))
    for item in questions:
        story += _answer_flow(item)

    story.append(Spacer(1, 2 * mm))
    story.append(_section_banner("راهنمای استفاده از کلید (کیفی)", accent=colors.HexColor("#F59E0B"), bg=colors.HexColor("#FFFBEB"), fg=AMBER_DARK))
    story.append(Spacer(1, 3 * mm))
    story += _correction_flow(questions)

    story.append(Spacer(1, 4 * mm))
    story += rtl_flowables(
        f"این آزمون و پاسخنامه توسط فهم‌یار ساخته شد · {_fa(total)} سؤال چهارگزینه‌ای · سطح سختی: {diff_label} · تاریخ: {stamp}",
        _style("foot-note", alignment=TA_CENTER, fontSize=7.5, leading=15, textColor=SLATE_400),
        178,
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
