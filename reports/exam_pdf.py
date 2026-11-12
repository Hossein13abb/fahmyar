"""ساخت PDF آزمون با **ReportLab** (Pure Python — بدون هیچ وابستگی به سیستم‌عامل/GTK/DLL).

چینش متن فارسی (چندخطی): متن به‌صورت دستی به خط‌هایی با عرض ثابت شکسته می‌شود
(`stringWidth` روی متنِ reshape‌شده) و سپس هر خط با `arabic_reshaper.reshape` +
`bidi.get_display` آماده می‌شود؛ هر خط یک پاراگراف مجزا و راست‌چین رندر می‌شود.
قلم: Vazirmatn (فایل‌های TTFِ همراه ریپو در assets/fonts).
خروجی: بایت‌های PDF — کاملاً در حافظه، بدون فایل موقت، روی هر سیستم‌عامل.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
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
    KeepTogether,
)

from models.concept import Concept
from models.question import Question

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
    "challenging": "چالش‌برانگیز",
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


def _fa(value: Any) -> str:
    return "".join(_FA_DIGITS[int(d)] if d.isdigit() else d for d in str(value))


def _fa_date() -> str:
    try:
        import jdatetime

        return jdatetime.date.today().strftime("%Y/%m/%d")
    except Exception:
        from datetime import date

        return date.today().strftime("%Y/%m/%d")


def reshaped(text: Any) -> str:
    """متن فارسی را برای رندرِ تک‌خطی آماده می‌کند (اتصال حروف + ترتیب نمایشی راست‌به‌چپ)."""
    return get_display(arabic_reshaper.reshape(str(text or "")))


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
) -> list[Paragraph]:
    """متن فارسی را به خط‌های پاراگراف راست‌چین تبدیل می‌کند (امن برای Platypus)."""
    font = style.fontName or FONT_REG
    size = style.fontSize
    max_width = max_width_mm * mm
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


class CircleNumber(Flowable):
    """نشانگرِ دایره‌ایِ سبز با شمارهٔ سؤال به فارسی."""

    def __init__(self, number: int, size: float = 9 * mm):
        super().__init__()
        self.number = number
        self.size = size

    def wrap(self, availWidth, availHeight):
        return self.size, self.size

    def draw(self):
        c = self.canv
        s = self.size
        c.saveState()
        c.setFillColor(BRAND)
        c.circle(s / 2, s / 2, s / 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FONT_XBOLD, 13)
        c.drawCentredString(s / 2, s / 2 - 4.6, reshaped(_fa(self.number)))
        c.restoreState()


class NumberedCanvas(canvas.Canvas):
    """کانواس دوگذری برای نوشتن «صفحه X از Y» در پاورقی همهٔ صفحات."""

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
        text = reshaped(f"فهم‌یار · آزمون جامع تشخیصی — صفحهٔ {_fa(self._pageNumber)} از {_fa(total)}")
        self.drawCentredString(A4[0] / 2, 8 * mm, text)
        self.restoreState()


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
        "پاسخ‌ها را با خودکار آبی به‌صورت کامل و با دلیل بنویسید؛ صرفاً نوشتن جواب نهایی نمره نمی‌گیرد.",
        "نوشتن پاسخ تشریحی الزامی است — کشفِ «چرایی» مهم‌تر از «چیستی» است.",
        "همراه داشتن جزوه و ابزار هوشمند ممنوع است. فضای پاسخ زیر هر سؤال تعبیه شده است.",
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


def _question_block(item: dict[str, Any], with_lines: bool = True) -> Table:
    subj = SUBJECT_LABELS.get(item["subject"], item["subject"])
    body: list[Flowable] = rtl_flowables(subj, _style("q-subj", fontName=FONT_BOLD, fontSize=8.5, textColor=TEAL_TEXT, leading=15), 144)
    body += rtl_flowables(item["text"], _style("q-text", fontSize=10.5, leading=21), 144)
    if with_lines:
        body += [Spacer(1, 1 * mm), DottedLine(), DottedLine(), DottedLine()]
    badge = CircleNumber(int(item["order"]), 9 * mm)
    t = Table([[body, badge]], colWidths=[160 * mm, 18 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.8, BRAND_LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def _answer_block(item: dict[str, Any]) -> Table:
    subj = SUBJECT_LABELS.get(item["subject"], item["subject"])
    body: list[Flowable] = rtl_flowables(subj, _style("ak-subj", fontName=FONT_BOLD, fontSize=8.5, textColor=TEAL_TEXT, leading=15), 144)
    preview = item["text"] if len(item["text"]) <= 110 else item["text"][:110] + "…"
    body += rtl_flowables(preview, _style("ak-prev", fontSize=9, leading=17, textColor=SLATE_600), 144)
    body.append(Spacer(1, 1.5 * mm))
    body += rtl_flowables("پاسخ / منطق صحیح:", _style("ak-l1", fontName=FONT_XBOLD, fontSize=8.5, textColor=EMERALD_TEXT, leading=16), 144)
    body += rtl_flowables(item["correct_reasoning"], _style("ak-a", fontSize=9.5, leading=19), 144)

    mism = item["misconception_indicators"] or item["mapped_misconceptions"]
    if mism:
        body += rtl_flowables("بدفهمی‌های رایجِ هدف:", _style("ak-l2", fontName=FONT_XBOLD, fontSize=8.5, textColor=BROWN_TEXT, leading=16), 144)
        for m in mism:
            body += rtl_flowables(f"• {m}", _style("ak-m", fontSize=8.5, leading=16, textColor=BROWN_TEXT), 144)

    badge = CircleNumber(int(item["order"]), 9 * mm)
    t = Table([[body, badge]], colWidths=[160 * mm, 18 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E2E8F0")),
                ("BACKGROUND", (0, 0), (-1, -1), SLATE_50),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def _correction_guide(items: list[dict[str, Any]]) -> Table:
    """راهنمای تصحیح کیفی — سطح‌های کامل/نسبی/ناقص بدون نمره و رتبه."""
    blocks: list[Flowable] = rtl_flowables(
        "تصحیح این آزمون کیفی است: هر پاسخ در یکی از سه سطح «کامل / نسبی / ناقص» قرار می‌گیرد. "
        "هیچ نمره‌ای عددی ثبت نمی‌شود و مقایسهٔ دانش‌آموزان با یکدیگر ممنوع است؛ هدف، تشخیص ریشهٔ بدفهمی است.",
        _style("chg-intro", fontSize=9.5, leading=19, textColor=colors.HexColor("#1F2937")),
        178 - 20,
    )
    blocks.append(Spacer(1, 2 * mm))
    for item in items:
        order = _fa(item["order"])
        blocks += rtl_flowables(f"سؤال {order} — راهنمای بارم‌دهی کیفی", _style("chg-q", fontName=FONT_XBOLD, fontSize=9.5, textColor=BRAND_DARK, leading=19), 178 - 20)
        blocks += rtl_flowables(f"• کامل: {item['correct_reasoning']}", _style("chg-full", fontSize=8.5, leading=16, textColor=EMERALD_TEXT), 178 - 20)
        partial = item["partial_credit_signs"] or ["به پاسخ نزدیک شده ولی استدلال/برهان کامل نیست"]
        for sign in partial:
            blocks += rtl_flowables(f"• نسبی: {sign}", _style("chg-part", fontSize=8.5, leading=16, textColor=AMBER_DARK), 178 - 20)
        mism = item["misconception_indicators"] or item["mapped_misconceptions"] or ["پاسخ هیچ نشانه‌ای از درک گزارهٔ هدف ندارد"]
        for sign in mism:
            blocks += rtl_flowables(f"• ناقص: {sign}", _style("chg-bad", fontSize=8.5, leading=16, textColor=BROWN_TEXT), 178 - 20)
        blocks.append(Spacer(1, 1.5 * mm))
    t = Table([[blocks]], colWidths=[PAGE_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FFFBEB")),
                ("BOX", (0, 0), (0, 0), 1.0, colors.HexColor("#FDE68A")),
                ("TOPPADDING", (0, 0), (0, 0), 8),
                ("BOTTOMPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
            ]
        )
    )
    return t


def _answer_sheet_table(items: list[dict[str, Any]]) -> Table:
    """جدول پاسخنامهٔ دانش‌آموز برای ثبتِ پاسخِ کوتاهِ هر سؤال."""
    header_num = Paragraph(_esc_xml(reshaped("شمارهٔ سؤال")), _style("as-h1", fontName=FONT_XBOLD, textColor=colors.white, alignment=TA_CENTER, leading=17))
    header_ans = Paragraph(_esc_xml(reshaped("پاسخ کوتاه / واژهٔ کلیدی")), _style("as-h2", fontName=FONT_XBOLD, textColor=colors.white, alignment=TA_CENTER, leading=17))
    data = [[header_ans, header_num]]  # ستون‌ها: [پاسخ، شماره] برای چیدمان راست‌به‌چپ
    for item in items:
        num = Paragraph(_esc_xml(reshaped(_fa(item["order"]))), _style("as-n", alignment=TA_CENTER, leading=23))
        data.append([Paragraph("&nbsp;", _style("as-e")), num])
    t = Table(data, colWidths=[140 * mm, 38 * mm], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("GRID", (0, 0), (-1, -1), 0.7, BRAND_LINE_SOFT),
                ("BACKGROUND", (1, 1), (1, -1), SLATE_50),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
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
    source: str,
    grade: Optional[int] = None,
    major: Optional[str] = None,
) -> bytes:
    _register_fonts()

    diff_label = DIFFICULTY_LABELS.get(difficulty, difficulty)
    source_label = SOURCE_LABELS.get(source, source)
    subjects_label = " + ".join(SUBJECT_LABELS.get(s, s) for s in dict.fromkeys(q["subject"] for q in questions))
    total = len(questions)
    stamp = _fa_date()
    grade_label = f"پایهٔ {_fa(grade)}" if grade else "—"
    major_label = (major or "").strip() or "—"

    from io import BytesIO

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title=title or "آزمون فهم‌یار",
        author="فهم‌یار",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="frame")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])

    story: list[Flowable] = []

    # ── سربرگ استاندارد ──
    story += rtl_flowables(school_name, _style("school", fontName=FONT_XBOLD, fontSize=13, textColor=colors.HexColor("#0F5132"), alignment=TA_CENTER, leading=21), 178)
    story += rtl_flowables("«فهم‌یار» — سامانهٔ تشخیصی فهمِ مفهومی", _style("school-sub", alignment=TA_CENTER, fontSize=8.5, leading=16, textColor=SLATE_500), 178)
    story.append(Spacer(1, 3 * mm))
    story.append(RoundedBanner(title))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _meta_table(
            [
                ("نام و نام خانوادگی", ""),
                ("پایه / رشته", f"{grade_label} — {major_label}"),
                ("درس / دروس", subjects_label),
                ("مباحث آزمون", subjects_label),
                ("تعداد سؤال‌ها", f"{_fa(total)} سؤال تشریحی"),
                ("زمان آزمون", f"{_fa(duration_minutes)} دقیقه"),
                ("سطح سختی", diff_label),
                ("منبع سؤالات", source_label),
                ("تاریخ برگزاری", stamp),
            ]
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(_instruction_box())
    story.append(Spacer(1, 4 * mm))

    # ── بخش ۱ — دفترچه سؤالات ──
    story.append(_section_banner("بخش ۱ — دفترچه سؤالات"))
    story.append(Spacer(1, 3.5 * mm))
    for item in questions:
        story.append(KeepTogether([_question_block(item, with_lines=True), Spacer(1, 3.5 * mm)]))

    # ── جدول پاسخنامه (ثبت پاسخ کوتاه) ──
    story.append(Spacer(1, 1 * mm))
    story.append(KeepTogether([
        _section_banner("جدول پاسخنامهٔ دانش‌آموز", accent=colors.HexColor("#0EA5E9"), bg=colors.HexColor("#F0F9FF"), fg=colors.HexColor("#0C4A6E")),
        Spacer(1, 3 * mm),
        _answer_sheet_table(questions),
    ]))

    # ── بخش ۲ — پاسخنامهٔ تشریحی + راهنمای تصحیح کیفی (صفحهٔ مجزا) ──
    story.append(PageBreak())
    secret_p = Paragraph(_esc_xml(reshaped("مختص دبیر محترم — پاسخنامهٔ تشریحی (کلید آزمون)")), _style("secret", fontName=FONT_XBOLD, fontSize=9.5, textColor=RED_TEXT, alignment=TA_CENTER, leading=18))
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
        story.append(KeepTogether([_answer_block(item), Spacer(1, 3 * mm)]))

    story.append(Spacer(1, 2 * mm))
    story.append(_section_banner("راهنمای تصحیح کیفی", accent=colors.HexColor("#F59E0B"), bg=colors.HexColor("#FFFBEB"), fg=AMBER_DARK))
    story.append(Spacer(1, 3 * mm))
    story.append(_correction_guide(questions))

    story.append(Spacer(1, 4 * mm))
    story += rtl_flowables(
        f"این آزمون و پاسخنامه توسط فهم‌یار ساخته شد · {_fa(total)} سؤال · سطح سختی: {diff_label} · تاریخ: {stamp}",
        _style("foot-note", alignment=TA_CENTER, fontSize=7.5, leading=15, textColor=SLATE_400),
        178,
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
