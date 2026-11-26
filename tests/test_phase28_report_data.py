"""گاردهای فاز ۲۸ — صحتِ دادهٔ کارنامه پیش از ظاهر.

تصویرِ «ناموفق» کارنامه سه نشانه داشت: عنوانِ «نامشخص»، جدولِ پنج‌ردیفیِ
خالی و نوارهای بی‌داده. هیچ‌کدام از این‌ها به CSS ربط نداشت؛ همه از دو
باگِ داده‌ای می‌آمدند:

  ۱. ``build_report`` خروجیِ کاملِ ارزیاب را که در
     ``session.cognitive_report["evaluation_report"]`` ذخیره شده بود
     نادیده می‌گرفت و گزارشِ متنیِ قدیمی می‌ساخت.

  ۲. در فرانت، دروازهٔ رندر به وجودِ ``report.exam`` گره خورده بود؛
     کلیدی که فقط مسیرِ آزمونِ ده‌سؤالی آن را می‌سازد. پس کارنامه‌ای با
     پنج حکمِ واقعی به صفحهٔ «این نشست کارنامه ندارد» می‌افتاد.

این تست‌ها همان دو مسیر را قفل می‌کنند تا برنگردند.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


# ══════════════ ۱. خواندنِ خروجیِ ذخیره‌شدهٔ ارزیاب ══════════════

def test_build_report_reads_persisted_evaluation():
    """``build_report`` باید ``evaluation_report`` را ببیند، نه نادیده بگیرد."""
    src = _read("reports", "report_generator.py")
    assert "_persisted_evaluation" in src, "تابعِ خواندنِ خروجیِ ذخیره‌شده حذف شده است"
    assert 'raw.get("evaluation_report")' in src
    # و باید واقعاً در مسیرِ build_report صدا زده شود
    assert "persisted = _persisted_evaluation(session)" in src


def test_no_placeholder_concept_name_for_evaluation_sessions():
    """برای جلسهٔ ارزیابی، نامِ مبحث از ``cognitive_payload.topic`` می‌آید.

    وگرنه عنوانِ کارنامه «نامشخص» می‌شد — همان چیزی که در تصویر بود.
    """
    src = _read("reports", "report_generator.py")
    assert 'payload.get("topic")' in src
    assert "display_name = concept.name if concept else topic_name" in src


def test_advice_helper_never_invents_text():
    """کمکیِ متنِ توصیه فقط از خروجیِ ارزیاب می‌خواند و رشتهٔ تازه نمی‌سازد."""
    src = _read("reports", "report_generator.py")
    start = src.index("def _advice_text(")
    body = src[start : src.index("\n\n\n", start)]
    for key in ("advice", "text", "summary"):
        assert key in body
    # هیچ جملهٔ آموزشیِ ثابتی نباید داخلش باشد
    assert "تمرین" not in body
    assert "پیشنهاد می‌شود" not in body


# ══════════════ ۲. دروازهٔ رندرِ فرانت ══════════════

def test_frontend_gate_does_not_require_exam_key():
    """دروازهٔ کارنامه نباید به ``exam`` گره خورده باشد.

    ``exam`` فقط در مسیرِ آزمونِ ده‌سؤالی هست. کارنامهٔ ارزیابیِ کل‌نگر
    همان ``per_question`` و ``cross_check_findings`` را دارد بدونِ آن کلید.
    """
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "if (report?.exam) {" not in src, "دروازهٔ قدیمیِ مخصوصِ exam برگشته است"
    assert "const hasPerQuestion = Array.isArray(report?.per_question)" in src
    assert "if (hasPerQuestion || hasDimensions || hasNarrative)" in src


def test_frontend_never_renders_placeholder_dimension_rows():
    """ردیفِ «نامشخص» به‌عنوان پرکننده نباید ساخته شود."""
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    # فیلترِ خالی‌ها باید سرِ جایش باشد
    assert "!isEmptyDimension(d)" in src
    # و بخشِ ابعاد فقط با دادهٔ واقعی رندر شود
    assert "dimensions.length > 0" in src


def test_action_plan_section_is_conditional():
    """بخشِ «برنامهٔ اقدام» نباید کارتِ سفیدِ خالی بسازد."""
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "(suggestions.length > 0 || nextStep) &&" in src


def test_assessed_tone_distinguishes_no_verdict_from_no_status():
    """``status`` تهی با حکمِ توصیفی، «شواهد ناکافی» نیست.

    این دو وضعیت در UI نباید یکی دیده شوند: یکی یعنی «داوری نشد»، دیگری
    یعنی «حکم هست ولی درست/غلطش را نمی‌دانیم».
    """
    src = _read("frontend", "src", "components", "cognitive", "DetailedQuestions.jsx")
    assert "ASSESSED:" in src
    assert "export const toneOf = (status, verdict = '')" in src
    assert "return rawText(verdict) ? TONE.ASSESSED : TONE.INSUFFICIENT_EVIDENCE" in src


# ══════════════ ۳. بدونِ ساختِ وضعیت یا درصد ══════════════

def test_no_fabricated_status_or_percentage_in_report_generator():
    """از حکمِ توصیفی، درست/غلط یا درصد ساخته نمی‌شود."""
    src = _read("reports", "report_generator.py")
    start = src.index("def _report_from_persisted_evaluation(")
    body = src[start : src.index("def build_report(", start)]
    # وضعیتِ سؤال عمداً None می‌ماند
    assert '"status": None' in body
    # هیچ محاسبهٔ درصدی
    assert "%" not in body.replace("%s", "").replace("%(", "")
    assert "percent" not in body.lower()
    # ``exam_score_note`` یک **هشدارِ منفی** است («نمره معیارِ فهم نیست»)،
    # نه امتیاز. پس فقط وجودِ محاسبهٔ امتیاز ممنوع است، نه نامِ آن هشدار.
    for forbidden in ('"score":', "'score':", "score =", "= score"):
        assert forbidden not in body.lower()
