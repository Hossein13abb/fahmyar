# -*- coding: utf-8 -*-
"""Primitives shared by every ReportLab document in the project.

This module is the surviving core of the old ``reports/exam_pdf.py``.  That file
contained two kinds of code:

* the **exam booklet renderer** — tables, options, matrices, formula-to-image
  conversion — which the browser engine replaced and which is now deleted;
* a set of **generic ReportLab helpers** — fonts, colours, Persian shaping,
  page numbering, section banners — which ``reports/report_pdf.py`` (the
  qualitative report card) genuinely uses.

Deleting ``exam_pdf.py`` outright would have broken the report card, so the
helpers moved here first and that module now imports from here.  Nothing in this
file draws exam content.
"""
from __future__ import annotations

from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

__all__ = [
    "DIFFICULTY_LABELS", "SUBJECT_LABELS",
    # colours
    "BRAND", "BRAND_ACCENT", "BRAND_DARK", "BRAND_LINE", "BRAND_LINE_SOFT",
    "BRAND_MINT", "BRAND_SOFT", "EMERALD_TEXT", "TEAL_TEXT", "BROWN_TEXT",
    "AMBER_DARK", "RED_TEXT", "RED_SOFT", "RED_LINE", "SLATE_50", "SLATE_400",
    "SLATE_500", "SLATE_600", "SLATE_900",
    # fonts
    "FONT_REG", "FONT_BOLD", "FONT_XBOLD", "FONT_DIR", "_register_fonts",
    # text
    "to_persian_numbers", "final_pdf_cleanup", "get_pdf_safe_text",
    "prepare_farsi_text", "reshaped", "_esc_xml", "fa_number", "fa_date",
    # layout
    "_style", "rtl_flowables", "PAGE_W", "_meta_table", "_section_banner",
    "RoundedBanner", "DottedLine", "NumberedCanvas",
]

#: برچسب‌های فارسی سطح سختی — قرارداد API و کلیدواژهٔ گزارش‌ها
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
}

SUBJECT_LABELS = {
    "math": "ریاضی",
    "physics": "فیزیک",
    "chemistry": "شیمی",
    "biology": "زیست‌شناسی",
    "english": "انگلیسی",
    "calculus": "حسابان",
    "geometry": "هندسه",
    "آمار": "آمار و احتمال",
}

BRAND_DARK = colors.HexColor("#064E3B")
BRAND = colors.HexColor("#047857")
BRAND_ACCENT = colors.HexColor("#10B981")
BRAND_SOFT = colors.HexColor("#ECFDF5")
BRAND_MINT = colors.HexColor("#F0FDF4")
BRAND_LINE = colors.HexColor("#D1FAE5")
BRAND_LINE_SOFT = colors.HexColor("#A7F3D0")

SLATE_50 = colors.HexColor("#F8FAFC")
SLATE_400 = colors.HexColor("#94A3B8")
SLATE_500 = colors.HexColor("#64748B")
SLATE_600 = colors.HexColor("#475569")
SLATE_900 = colors.HexColor("#0F172A")

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

from pathlib import Path  # noqa: E402  (kept next to FONT_DIR for readability)

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = BASE_DIR / "assets" / "fonts"

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_persian_numbers(text: Any) -> str:
    """Map ASCII digits to Persian digits, leaving everything else alone."""
    return str(text).translate(str.maketrans("0123456789", _FA_DIGITS))


#: usable content width on A4 with 16 mm margins
PAGE_W = 178 * 2.834645669  # 178 mm in points


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------

def final_pdf_cleanup(text: Any) -> str:
    """Strip LaTeX/symbol noise left over in plain text bound for ReportLab.

    Persian shaping happens afterwards, in :func:`get_pdf_safe_text`.  This
    function only removes markup; it never translates a command into a Persian
    word.
    """
    import re

    if not text:
        return ""
    s = str(text)
    # control characters eaten by JSON (\b in \begin, \f in \frac)
    s = s.replace("\x08", r"\b").replace("\x0c", r"\f")
    # remaining LaTeX commands and delimiters
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[\\${}]", " ", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def get_pdf_safe_text(text: Any) -> str:
    """Clean, shape and bidi-order Persian text for ReportLab's paragraph flow."""
    if not text:
        return ""
    cleaned = final_pdf_cleanup(str(text))
    return get_display(arabic_reshaper.reshape(cleaned))


def prepare_farsi_text(text: str) -> str:
    return get_pdf_safe_text(text)


def reshaped(text: Any) -> str:
    return get_pdf_safe_text(str(text or ""))


def _esc_xml(value: str) -> str:
    """Escape the three characters ReportLab's mini-XML parser chokes on."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fa_number(value: Any) -> str:
    return to_persian_numbers(str(value))


def fa_date() -> str:
    try:
        import jdatetime

        return to_persian_numbers(jdatetime.date.today().strftime("%Y/%m/%d"))
    except Exception:
        from datetime import date

        return to_persian_numbers(date.today().strftime("%Y/%m/%d"))


# ---------------------------------------------------------------------------
# fonts and styles
# ---------------------------------------------------------------------------

_FONTS_READY = False


def _register_fonts() -> None:
    """Register the three Vazirmatn weights once per process."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    for name, filename in (
        (FONT_REG, "Vazirmatn-Regular.ttf"),
        (FONT_BOLD, "Vazirmatn-Bold.ttf"),
        (FONT_XBOLD, "Vazirmatn-ExtraBold.ttf"),
    ):
        path = FONT_DIR / filename
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:
                pass
    _FONTS_READY = True


def _style(name: str, **kwargs) -> ParagraphStyle:
    kwargs.setdefault("fontName", FONT_REG)
    kwargs.setdefault("fontSize", 10)
    kwargs.setdefault("leading", 18)
    kwargs.setdefault("textColor", SLATE_900)
    return ParagraphStyle(name=name, **kwargs)


def rtl_flowables(text: str, style: ParagraphStyle, width: float) -> list:
    """Wrap text in a Paragraph, width-limited for RTL layout."""
    from reportlab.platypus import Paragraph

    return [Paragraph(_esc_xml(get_pdf_safe_text(text)), style)]


# ---------------------------------------------------------------------------
# flowables
# ---------------------------------------------------------------------------

def _section_banner(text, accent=BRAND_ACCENT, bg=BRAND_SOFT, fg=BRAND_DARK):
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    p = Paragraph(
        _esc_xml(get_pdf_safe_text(text)),
        _style(
            f"banner-{text[:8]}",
            fontName=FONT_XBOLD,
            fontSize=10.5,
            leading=20,
            textColor=fg,
        ),
    )
    t = Table([[p]], colWidths=[PAGE_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), bg),
                ("LINEBEFORE", (0, 0), (0, 0), 3, accent),
                ("TOPPADDING", (0, 0), (0, 0), 5),
                ("BOTTOMPADDING", (0, 0), (0, 0), 5),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
            ]
        )
    )
    return t


def _meta_table(rows):
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    data = []
    for key, value in rows:
        data.append(
            [
                Paragraph(_esc_xml(get_pdf_safe_text(value or " ")), _style(f"mv-{key}", fontSize=9.5, leading=16)),
                Paragraph(_esc_xml(get_pdf_safe_text(key)), _style(f"mk-{key}", fontName=FONT_BOLD, fontSize=9.5, leading=16, textColor=EMERALD_TEXT)),
            ]
        )
    t = Table(data, colWidths=[PAGE_W - 32 * mm, 32 * mm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                ("BACKGROUND", (1, 0), (1, -1), BRAND_SOFT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


class RoundedBanner:
    """Factory for the exam title band (kept because the report card uses it)."""

    def __new__(cls, text, *args, **kwargs):
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Table, TableStyle

        p = Paragraph(
            _esc_xml(get_pdf_safe_text(text)),
            _style("title-band", fontName=FONT_XBOLD, fontSize=15, leading=28, textColor=BRAND_DARK),
        )
        t = Table([[p]], colWidths=[PAGE_W])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), BRAND_SOFT),
                    ("BOX", (0, 0), (0, 0), 1.4, BRAND),
                    ("TOPPADDING", (0, 0), (0, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 10),
                ]
            )
        )
        return t


class DottedLine:
    """A thin dotted separator."""

    def __new__(cls, width=PAGE_W, color=BRAND_LINE, dash=(1, 2)):
        from reportlab.platypus import HRFlowable

        return HRFlowable(width=width, thickness=0.6, color=color, dash=dash)


class NumberedCanvas:
    """Canvas subclass that stamps ``صفحهٔ n از m`` on every page."""

    footer_label = "فهم‌یار"

    def __new__(cls, *args, **kwargs):
        from reportlab.pdfgen import canvas as _canvas

        base = _canvas.Canvas

        class _Inner(base):  # noqa: D101 - internal
            _saved_states: list = []

            def __init__(self, *a, **kw):
                base.__init__(self, *a, **kw)
                self._saved_states = []

            def showPage(self):  # noqa: N802 - ReportLab API
                self._saved_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._saved_states)
                for state in self._saved_states:
                    self.__dict__.update(state)
                    self._draw_footer(total)
                    base.showPage(self)
                base.save(self)

            def _draw_footer(self, total):
                from reportlab.lib.units import mm

                label = (
                    f"صفحهٔ {to_persian_numbers(str(self._pageNumber))} "
                    f"از {to_persian_numbers(str(total))} · {cls.footer_label}"
                )
                self.setFont(FONT_REG, 7.5)
                self.setFillColor(SLATE_400)
                self.drawCentredString(
                    self._pagesize[0] / 2.0, 8 * mm, get_pdf_safe_text(label)
                )

        return _Inner(*args, **kwargs)
