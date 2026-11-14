"""ساخت PDF «کارنامهٔ تحلیلی کیفیِ دانش‌آموز» — ReportLab + arabic_reshaper + bidi.

قوانین محتوایی (غیرقابل مذاکره):
  - مطلقاً هیچ نمره، درصد، رتبه یا مقایسه‌ای چاپ نمی‌شود.
  - فقط وضعیت‌های کیفیِ موتور ECD (تأییدشده / احتمالاً آموخته‌شده / نامشخص / بدفهمی شناسایی‌شده / فاقد شواهد کافی).
  - شواهدِ مشاهده‌شده + ریشه‌یابی مفاهیم + پیشنهاد اقدام — همه کیفی.
"""
from __future__ import annotations

from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Flowable,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from models.question import STATUS_FA
from reports.pdf_shared import (
    BRAND_ACCENT,
    BRAND_DARK,
    BRAND_LINE,
    BRAND_LINE_SOFT,
    BRAND_MINT,
    BRAND_SOFT,
    EMERALD_TEXT,
    FONT_BOLD,
    FONT_REG,
    FONT_XBOLD,
    SLATE_50,
    SLATE_400,
    SLATE_500,
    SLATE_600,
    SLATE_900,
    AMBER_DARK,
    BROWN_TEXT,
    RED_LINE,
    RED_SOFT,
    RED_TEXT,
    NumberedCanvas,
    _esc_xml,
    fa_number,
    fa_date,
    _meta_table,
    _register_fonts,
    _section_banner,
    _style,
    prepare_farsi_text,
    rtl_flowables,
    RoundedBanner,
    PAGE_W,
)

# رنگِ هر وضعیت کیفی (بدون بار داوری عددی)
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "CONFIRMED": ("#065F46", "#ECFDF5"),
    "LIKELY_UNDERSTOOD": ("#0F766E", "#F0FDFA"),
    "UNCLEAR": ("#92400E", "#FFFBEB"),
    "NEEDS_REVIEW": ("#9F1239", "#FFF1F2"),
    "INSUFFICIENT_EVIDENCE": ("#475569", "#F8FAFC"),
}


def _status_chip(status: str) -> Table:
    """چیپ رنگی وضعیت کیفی — Paragraph با پس‌زمینه و کادر (تک‌سلولی؛ کوچک و امن)."""
    status = (status or "").upper()
    fg, bg = STATUS_STYLE.get(status, STATUS_STYLE["INSUFFICIENT_EVIDENCE"])
    label = STATUS_FA.get(status, "نامشخص")
    p = Paragraph(
        _esc_xml(prepare_farsi_text(label)),
        _style(f"chip-{status}", fontName=FONT_BOLD, fontSize=8.5, leading=15, textColor=colors.HexColor(fg), alignment=TA_CENTER),
    )
    t = Table([[p]], colWidths=[34 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(bg)),
        ("BOX", (0, 0), (0, 0), 0.8, colors.HexColor(fg)),
        ("TOPPADDING", (0, 0), (0, 0), 3),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
    ]))
    return t


class _ReportCanvas(NumberedCanvas):
    footer_label = "کارنامهٔ کیفی فهم‌یار"


def _bullets(items: list[str], style_name: str, color: str = "#1F2937", indent_mm: float = 0) -> list[Flowable]:
    out: list[Flowable] = []
    for i, item in enumerate(items or [], start=1):
        out += rtl_flowables(f"• {item}", _style(f"{style_name}-{i}", fontSize=9.5, leading=19, textColor=colors.HexColor(color)), 178 - indent_mm)
        out.append(Spacer(1, 1.2 * mm))
    if not items:
        out += rtl_flowables("— موردی ثبت نشده است.", _style(f"{style_name}-empty", fontSize=9, leading=17, textColor=SLATE_500), 178)
    return out


def _amber_note(text: str) -> Table:
    flow = rtl_flowables(text, _style("amber-note", fontSize=9.5, leading=19, textColor=AMBER_DARK, fontName=FONT_BOLD), 178 - 24)
    t = Table([[flow]], colWidths=[PAGE_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FFFBEB")),
        ("BOX", (0, 0), (0, 0), 1.0, colors.HexColor("#F59E0B")),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 0), (0, 0), 6),
        ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
    ]))
    return t


def _dimension_rows(dimensions: list[dict[str, Any]]) -> list[Flowable]:
    blocks: list[Flowable] = []
    for i, d in enumerate(dimensions or [], start=1):
        dim = str(d.get("dimension") or "بُعد نامشخص")
        status = str(d.get("status") or "UNCLEAR").upper()
        finding = str(d.get("finding") or "—")
        chip = _status_chip(status)
        head = rtl_flowables(f"{fa_number(i)}. {dim}", _style(f"dim-h-{i}", fontName=FONT_XBOLD, fontSize=9.5, textColor=SLATE_900, leading=18), 118)
        t = Table([[chip, head]], colWidths=[38 * mm, 140 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        blocks.append(t)
        blocks += rtl_flowables(finding, _style(f"dim-f-{i}", fontSize=9, leading=18, textColor=SLATE_600), 178, )
        blocks.append(Spacer(1, 2.5 * mm))
    return blocks


def _per_question_blocks(per_question: list[dict[str, Any]]) -> list[Flowable]:
    blocks: list[Flowable] = []
    for i, q in enumerate(per_question or [], start=1):
        order = q.get("order") or i
        qtype = q.get("exam_type") or "—"
        status = str(q.get("status") or "UNCLEAR").upper()
        feedback = str(q.get("qualitative_feedback") or q.get("reasoning") or "—")
        label_style = _style(f"pq-h-{i}", fontName=FONT_BOLD, fontSize=9, leading=18, textColor=EMERALD_TEXT,
                             backColor=SLATE_50, borderWidth=0.6, borderColor=BRAND_LINE, borderPadding=5, borderRadius=3)
        blocks.append(Paragraph(_esc_xml(prepare_farsi_text(f"سؤال {fa_number(order)} — {qtype}")), label_style))
        blocks.append(Spacer(1, 1.5 * mm))
        chip = _status_chip(status)
        chip_row = Table([[chip]], colWidths=[PAGE_W])
        chip_row.setStyle(TableStyle([("TOPPADDING", (0, 0), (0, 0), 1), ("BOTTOMPADDING", (0, 0), (0, 0), 1)]))
        blocks.append(chip_row)
        blocks += rtl_flowables(feedback, _style(f"pq-f-{i}", fontSize=9, leading=18, textColor=SLATE_600), 178)
        blocks.append(Spacer(1, 3.5 * mm))
    return blocks


def _root_cause_blocks(root_causes: list[dict[str, Any]], target: str) -> list[Flowable]:
    blocks: list[Flowable] = []
    for i, rc in enumerate(root_causes or [], start=1):
        name = str(rc.get("concept_name") or rc.get("area") or "عنوان ریشه ثبت نشد")
        reasoning = str(rc.get("reasoning") or "")
        cross = bool(rc.get("cross_subject"))
        title = f"ریشهٔ {fa_number(i)}: {name}" + (" (بین‌درسی)" if cross else "")
        blocks.append(Paragraph(
            _esc_xml(prepare_farsi_text(title)),
            _style(f"rc-h-{i}", fontName=FONT_XBOLD, fontSize=9.5, leading=19, textColor=BROWN_TEXT,
                   backColor=colors.HexColor("#FFF7ED"), borderWidth=0.6, borderColor=colors.HexColor("#FED7AA"),
                   borderPadding=5, borderRadius=3),
        ))
        if reasoning:
            blocks += rtl_flowables(reasoning, _style(f"rc-r-{i}", fontSize=9, leading=18, textColor=SLATE_600), 178)
        # مسیر علّی: ریشه ← مفهوم هدف
        blocks += rtl_flowables(f"مسیرِ اثر: ضعف در «{name}» اختلال در یادگیریِ «{target}» ایجاد می‌کند.",
                                _style(f"rc-p-{i}", fontSize=9, leading=18, textColor=AMBER_DARK, fontName=FONT_BOLD), 178)
        blocks.append(Spacer(1, 3.5 * mm))
    if not root_causes:
        blocks += rtl_flowables("بدفهمیِ ریشه‌دارِ تکرارشونده‌ای یافت نشد.",
                                _style("rc-none", fontSize=9, leading=18, textColor=EMERALD_TEXT, fontName=FONT_BOLD), 178)
    return blocks


def build_report_pdf(
    *,
    student_name: str,
    student_username: str,
    student_grade: Any = None,
    student_major: str | None = None,
    report: dict[str, Any],
) -> bytes:
    """خروجی بایت‌های PDF کارنامه — کاملاً در حافظه."""
    _register_fonts()

    is_exam = bool(report.get("exam"))
    concept_name = report.get("concept_name") or "نامشخص"
    stamp = fa_date()
    grade_text = f"پایهٔ {fa_number(student_grade)}" if student_grade else "—"
    major_text = (student_major or "").strip()
    if major_text:
        grade_text = f"{grade_text} — {major_text}"

    from io import BytesIO

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title="کارنامهٔ تحلیلی کیفی — فهم‌یار",
        author="فهم‌یار",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="frame")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])

    story: list[Flowable] = []

    # ── سربرگ ──
    story += rtl_flowables("«فهم‌یار» — سامانهٔ تشخیصی فهمِ مفهومی", _style("rp-sub", alignment=TA_CENTER, fontSize=8.5, leading=16, textColor=SLATE_500), 178)
    story.append(Spacer(1, 2 * mm))
    story.append(RoundedBanner("کارنامهٔ تحلیلی کیفی"))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _meta_table(
            [
                ("دانش‌آموز", student_name or student_username or "—"),
                ("نام کاربری", student_username or "—"),
                ("پایه / رشته", grade_text),
                ("زمینهٔ بررسی", concept_name),
                ("نوع گزارش", "آزمون جامع تشخیصی" if is_exam else "فهم‌سنجیِ مفهومی (ECD)"),
                ("تعداد پاسخ ثبت‌شده", f"{fa_number(report.get('questions_answered') or 0)} پاسخ"),
                ("تاریخ تولید گزارش", stamp),
            ]
        )
    )
    story.append(Spacer(1, 4 * mm))
    note = (report.get("exam_score_note") or "").replace("⚠️", "").replace("⚠", "").strip()
    story.append(_amber_note(note or "توجه: نمرهٔ آزمون — نه سنجش فهم: این کارنامه نمره/رتبه/درصد ندارد؛ فقط شواهدِ کیفی از فهمیدن ثبت می‌شود."))
    story.append(Spacer(1, 4 * mm))

    sections = report.get("sections") or {}

    if is_exam:
        story.append(_section_banner("نمای کلی وضعیت — ابعاد فهم", accent=colors.HexColor("#0EA5E9"), bg=colors.HexColor("#F0F9FF"), fg=colors.HexColor("#0C4A6E")))
        story.append(Spacer(1, 3 * mm))
        story += _dimension_rows(report.get("dimensions") or [])
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("تحلیل تک‌تک سؤالات (کیفی)"))
        story.append(Spacer(1, 3 * mm))
        story += _per_question_blocks(report.get("per_question") or [])
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("ریشهٔ خطاها و بدفهمی‌ها", accent=colors.HexColor("#F59E0B"), bg=colors.HexColor("#FFFBEB"), fg=AMBER_DARK))
        story.append(Spacer(1, 3 * mm))
        story += _root_cause_blocks(report.get("root_causes") or [], concept_name)
        unclear = sections.get("موارد هنوز روشن‌نشده") or []
        if unclear:
            story.append(Spacer(1, 1 * mm))
            story.append(_section_banner("موارد هنوز روشن‌نشده", accent=colors.HexColor("#F43F5E"), bg=colors.HexColor("#FFF1F2"), fg=colors.HexColor("#9F1239")))
            story.append(Spacer(1, 2 * mm))
            story += _bullets(unclear, "unclear-exam", "#9F1239")
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("پیشنهادهای بهبود (کیفی)", accent=BRAND_ACCENT, bg=BRAND_SOFT, fg=BRAND_DARK))
        story.append(Spacer(1, 3 * mm))
        story += _bullets([f"دانش‌آموز: {s}" if not str(s).startswith("دانش‌آموز") else str(s) for s in (report.get("suggestions") or [])], "sugg", "#064E3B")
    else:
        story.append(_section_banner("مشاهدات (چه چیزی دیدیم؟)"))
        story.append(Spacer(1, 3 * mm))
        story += _bullets(sections.get("مشاهدات") or [], "obs", "#064E3B")
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("شواهد گزاره‌به‌گزاره", accent=colors.HexColor("#0EA5E9"), bg=colors.HexColor("#F0F9FF"), fg=colors.HexColor("#0C4A6E")))
        story.append(Spacer(1, 3 * mm))
        story += _bullets(sections.get("شواهد") or [], "evd", "#0C4A6E")
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("ریشه‌یابی مفاهیم (فرضیه‌های ریشهٔ خطا)", accent=colors.HexColor("#F59E0B"), bg=colors.HexColor("#FFFBEB"), fg=AMBER_DARK))
        story.append(Spacer(1, 3 * mm))
        story += _bullets(sections.get("فرضیه‌های ریشهٔ خطا") or [], "rc-ecd", "#92400E")
        unclear = sections.get("موارد هنوز روشن‌نشده") or []
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("موارد هنوز روشن‌نشده", accent=colors.HexColor("#F43F5E"), bg=colors.HexColor("#FFF1F2"), fg=colors.HexColor("#9F1239")))
        story.append(Spacer(1, 2 * mm))
        story += _bullets(unclear, "unclear-ecd", "#9F1239")
        story.append(Spacer(1, 1 * mm))
        story.append(_section_banner("پیشنهاد اقدام (کیفی)", accent=BRAND_ACCENT, bg=BRAND_SOFT, fg=BRAND_DARK))
        story.append(Spacer(1, 3 * mm))
        actions = [f"دانش‌آموز: {a}" for a in (sections.get("پیشنهاد اقدام برای دانش‌آموز") or [])]
        notes = [f"معلم: {t}" for t in (sections.get("یادداشت برای معلم") or [])]
        story += _bullets(actions + notes, "act-ecd", "#064E3B")

    story.append(Spacer(1, 4 * mm))
    story += rtl_flowables(
        "این کارنامه توسط فهم‌یار تولید شد · بدون هیچ نمره، درصد، رتبه یا مقایسه‌ای · مقایسهٔ دانش‌آموزان با یکدیگر ممنوع است.",
        _style("rp-foot", alignment=TA_CENTER, fontSize=7.5, leading=15, textColor=SLATE_400),
        178,
    )

    doc.build(story, canvasmaker=_ReportCanvas)
    return buffer.getvalue()
