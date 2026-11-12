"""ساخت PDF واقعی برای آزمون‌های مدرسه — دفترچه سؤالات + پاسخنامهٔ تشریحی (کلید معلم).

موتور: WeasyPrint (HTML → PDF) با فونت Vazirmatn و چینش راست‌به‌چپ (RTL).
سؤال‌ها از بانک دیتابیس (تأییدشده‌ها اول) و در صورت نیاز از مدل هوش مصنوعی (پروایدر فعال سیستم) تولید می‌شوند.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

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


def _fa(value: Any) -> str:
    return "".join(_FA_DIGITS[int(d)] if d.isdigit() else d for d in str(value))


def _fa_date() -> str:
    try:
        import jdatetime

        today = jdatetime.date.today()
        return today.strftime("%Y/%m/%d")
    except Exception:
        from datetime import date

        return date.today().strftime("%Y/%m/%d")


def _esc(text: Any) -> str:
    return html.escape(str(text or ""))


# ---------------------------------------------------------------------------
# انتخاب سؤال‌ها
# ---------------------------------------------------------------------------
def _question_dict(q: Question, subject: str, origin: str) -> dict[str, Any]:
    rubric = q.rubric if isinstance(q.rubric, dict) else {}
    mism = q.mapped_misconceptions if isinstance(q.mapped_misconceptions, list) else []
    return {
        "subject": subject,
        "text": (q.text or "").strip(),
        "difficulty": q.difficulty or "medium",
        "question_type": q.question_type or "conceptual",
        "correct_reasoning": (rubric.get("correct_reasoning") or "پاسخ‌نامه برای این سؤال ثبت نشده است؛ معلم محترم پاسخ مرجع را تکمیل کند.").strip(),
        "misconception_indicators": rubric.get("misconception_indicators") if isinstance(rubric.get("misconception_indicators"), dict) else {},
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
    # اول از سطح سختی خواسته‌شده
    exact = (
        base.filter(Question.difficulty == wanted_difficulty)
        .order_by(approved_first, Question.created_at.desc())
        .limit(limit)
        .all()
    )
    picked.extend(exact)
    # بعد از بقیۀ سطح‌ها برای تکمیل
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
            "misconception_indicators": rubric.get("misconception_indicators") if isinstance(rubric.get("misconception_indicators"), dict) else {},
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
# رندر HTML → PDF
# ---------------------------------------------------------------------------
def _question_blocks(items: list[dict[str, Any]]) -> str:
    blocks = []
    for item in items:
        subj = SUBJECT_LABELS.get(item["subject"], item["subject"])
        lines = "".join('<div class="answer-line"></div>' for _ in range(3))
        blocks.append(
            f'<div class="q-block"><div class="q-head"><span class="q-num">{_fa(item["order"])}</span>'
            f'<span class="q-meta">{_esc(subj)}</span></div>'
            f'<p class="q-text">{_esc(item["text"])}</p>{lines}</div>'
        )
    return "\n".join(blocks)


def _answer_blocks(items: list[dict[str, Any]]) -> str:
    blocks = []
    for item in items:
        subj = SUBJECT_LABELS.get(item["subject"], item["subject"])
        preview = item["text"] if len(item["text"]) <= 110 else item["text"][:110] + "…"
        mism = list(item["misconception_indicators"].keys())[:2] or item["mapped_misconceptions"][:2]
        mism_html = ""
        if mism:
            mism_html = (
                '<p class="ak-label">بدفهمی‌های رایجِ هدف:</p><ul class="ak-list">'
                + "".join(f"<li>{_esc(m)}</li>" for m in mism)
                + "</ul>"
            )
        blocks.append(
            f'<div class="ak-block"><div class="q-head"><span class="q-num">{_fa(item["order"])}</span>'
            f'<span class="q-meta">{_esc(subj)}</span></div>'
            f'<p class="ak-question">{_esc(preview)}</p>'
            f'<p class="ak-label">پاسخ/منطق صحیح:</p><p class="ak-answer">{_esc(item["correct_reasoning"])}</p>'
            f"{mism_html}</div>"
        )
    return "\n".join(blocks)


def build_exam_pdf(
    school_name: str,
    title: str,
    questions: list[dict[str, Any]],
    duration_minutes: int,
    difficulty: str,
    source: str,
) -> bytes:
    diff_label = DIFFICULTY_LABELS.get(difficulty, difficulty)
    source_label = SOURCE_LABELS.get(source, source)
    subjects_label = " + ".join(SUBJECT_LABELS.get(s, s) for s in dict.fromkeys(q["subject"] for q in questions))
    total = len(questions)
    stamp = _fa_date()

    css = f"""
    @font-face {{ font-family: 'Vazirmatn'; src: url('assets/fonts/Vazirmatn-Regular.ttf') format('truetype'); font-weight: 400; }}
    @font-face {{ font-family: 'Vazirmatn'; src: url('assets/fonts/Vazirmatn-Bold.ttf') format('truetype'); font-weight: 700; }}
    @font-face {{ font-family: 'Vazirmatn'; src: url('assets/fonts/Vazirmatn-ExtraBold.ttf') format('truetype'); font-weight: 800; }}
    @page {{
      size: A4;
      margin: 16mm 14mm 18mm 14mm;
      @bottom-center {{
        content: 'فه‌میار · آزمون جامع تشخیصی — صفحهٔ ' counter(page) ' از ' counter(pages);
        font-family: 'Vazirmatn'; font-size: 8pt; color: #64748b;
      }}
    }}
    @page :first {{ margin-top: 14mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Vazirmatn', sans-serif; direction: rtl; color: #0f172a; font-size: 10.5pt; line-height: 2;
    }}
    .school-name {{ text-align: center; font-size: 12pt; font-weight: 700; color: #0f5132; letter-spacing: .02em; margin: 0 0 2mm; }}
    .school-sub {{ text-align: center; font-size: 8.5pt; color: #64748b; margin-bottom: 5mm; }}
    h1.exam-title {{
      text-align: center; font-size: 19pt; font-weight: 800; color: #064e3b;
      border: 1.6pt solid #059669; border-radius: 6mm; padding: 3mm 2mm; margin: 0 0 4mm;
      background: linear-gradient(135deg, #ecfdf5 0%, #f0fdfa 100%);
    }}
    table.meta {{
      width: 100%; border-collapse: collapse; margin-bottom: 4mm; font-size: 9.5pt;
    }}
    table.meta td {{
      border: .6pt solid #a7f3d0; padding: 2mm 3mm; background: #f8fafc;
    }}
    table.meta td.k {{ font-weight: 700; color: #065f46; width: 30%; }}
    .instructions {{
      border: .6pt dashed #34d399; background: #f0fdf4; border-radius: 3mm;
      padding: 3mm 4mm; font-size: 9pt; margin-bottom: 6mm;
    }}
    .instructions b {{ color: #065f46; }}
    .section-title {{
      font-size: 13pt; font-weight: 800; color: #064e3b; border-right: 4pt solid #10b981;
      padding: 1mm 3mm; margin: 6mm 0 4mm; background: #ecfdf5; border-radius: 2mm;
    }}
    .q-block {{
      break-inside: avoid; page-break-inside: avoid;
      border: .7pt solid #d1fae5; border-radius: 3mm; padding: 3mm 4mm; margin-bottom: 4mm;
      background: #ffffff;
    }}
    .q-head {{ display: flex; align-items: center; gap: 3mm; margin-bottom: 1.5mm; }}
    .q-num {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 8mm; height: 8mm; border-radius: 50%;
      background: #047857; color: #ffffff; font-weight: 800; font-size: 11pt;
    }}
    .q-meta {{ font-size: 8.5pt; color: #0f766e; font-weight: 700; }}
    .q-text {{ margin: 1mm 0 2mm; font-size: 10.5pt; white-space: pre-line; }}
    .answer-line {{ border-bottom: .55pt dotted #94a3b8; height: 8mm; }}
    .ak-section {{ page-break-before: always; }}
    .ak-secret {{
      text-align: center; font-size: 8.5pt; font-weight: 700; color: #b91c1c;
      border: .7pt solid #fecaca; background: #fef2f2; border-radius: 2mm;
      padding: 1.5mm; margin-bottom: 5mm; letter-spacing: .05em;
    }}
    .ak-block {{
      break-inside: avoid; page-break-inside: avoid;
      border: .7pt solid #e2e8f0; border-radius: 3mm; padding: 3mm 4mm; margin-bottom: 3.5mm;
      background: #f8fafc;
    }}
    .ak-question {{ color: #334155; font-size: 9.5pt; margin: 0 0 1.5mm; border-bottom: .5pt dashed #cbd5e1; padding-bottom: 1.5mm; }}
    .ak-label {{ font-size: 8.5pt; font-weight: 800; color: #065f46; margin: 1.5mm 0 .5mm; }}
    .ak-answer {{ margin: 0; font-size: 9.5pt; white-space: pre-line; }}
    .ak-list {{ margin: 0; padding-right: 5mm; font-size: 8.5pt; color: #7c2d12; }}
    .footer-note {{ text-align: center; color: #94a3b8; font-size: 7.5pt; margin-top: 6mm; }}
    """

    html_doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head><meta charset="utf-8"><title>{_esc(title)}</title>
<style>{css}</style></head>
<body>

  <p class="school-name">{_esc(school_name)}</p>
  <p class="school-sub">«فهم‌یار» — سامانهٔ تشخیصی فهمِ مفهومی</p>
  <h1 class="exam-title">{_esc(title)}</h1>

  <table class="meta">
    <tr><td class="k">نام و نام خانوادگی</td><td></td></tr>
    <tr><td class="k">درس / دروس</td><td>{_esc(subjects_label)}</td></tr>
    <tr><td class="k">تعداد سؤال‌ها</td><td>{_fa(total)} سؤال تشریحی</td></tr>
    <tr><td class="k">زمان آزمون</td><td>{_fa(duration_minutes)} دقیقه</td></tr>
    <tr><td class="k">سطح سختی</td><td>{_esc(diff_label)}</td></tr>
    <tr><td class="k">منبع سؤالات</td><td>{_esc(source_label)}</td></tr>
    <tr><td class="k">تاریخ برگزاری</td><td>{_esc(stamp)}</td></tr>
  </table>

  <div class="instructions">
    <b>دستورالعمل آزمون:</b>
    <ul style="margin: 1mm 0 0; padding-right: 5mm;">
      <li>پاسخ‌ها را با خودکار آبی به‌صورت کامل و با دلیل بنویسید؛ صرفاً عدد صحیح نمره نمی‌گیرد.</li>
      <li>نوشتن پاسخ تشریحی الزام است — کشف «چرایی» مهم‌تر از «چیستی» است.</li>
      <li>همراه داشتن هرگونه جزوه و ابزار هوشمند ممنوع است. برای هر سؤال، فضای پاسخ زیر آن تعبیه شده است.</li>
    </ul>
  </div>

  <div class="section-title">بخش ۱ — دفترچه سؤالات</div>
  {_question_blocks(questions)}

  <div class="ak-section">
    <div class="ak-secret">مختص دبیر محترم — پاسخنامهٔ تشریحی (کلید آزمون)</div>
    {_answer_blocks(questions)}
    <p class="footer-note">این آزمون و پاسخنامه توسط فهم‌یار ساخته شد · {_fa(total)} سؤال · سطح سختی: {_esc(diff_label)} · تاریخ: {_esc(stamp)}</p>
  </div>

</body></html>"""

    from weasyprint import HTML

    return HTML(string=html_doc, base_url=str(BASE_DIR) + "/").write_pdf()
