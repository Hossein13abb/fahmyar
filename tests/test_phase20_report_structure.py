"""فاز ۲۰ — ساختارِ کارنامه: دو سکشن حذف شد و نباید برگردد.

این تست‌ها یک قرارداد را قفل می‌کنند: کارنامه چهار خروجی دارد و نه بیشتر —

  ۱. تحلیل کلی ابعاد پنج‌گانه
  ۲. شکارِ تناقض‌های واقعی
  ۳. تحلیل تشخیصیِ تک‌تکِ سؤال‌ها
  ۴. تمرین‌های عملی (پیشنهادهای قدم‌به‌قدم) — جمع‌بندیِ پایانی

«گراف وابستگی مفاهیم» و «حلقه‌های مفقوده» از این فهرست بیرون‌اند. اگر فردا
کسی دوباره رندرشان کند یا فیلدِ مرده‌شان را به قرارداد برگرداند، همین‌جا
سرخ می‌شود.
"""

from __future__ import annotations

import io
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return io.open(REPO.joinpath(*parts), encoding="utf-8").read()


# ── فرانت‌اند ─────────────────────────────────────────────────────────

def test_report_view_does_not_render_the_dependency_graph():
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "<RootCauseDag" not in src
    assert "<DagArrow" not in src
    assert 'title="تحلیل ریشه‌ای بدفهمی‌ها' not in src


def test_report_view_does_not_render_unresolved_loop_section():
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert 'title="حلقه‌های مفقوده' not in src
    assert "openGears" not in src


def test_report_view_does_not_render_gear_badges():
    """بج‌های زردِ «گره‌های کلیدی» هم رفتند — با سکشنِ حلقه‌ها یکی بودند."""
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "missing_gear" not in src


def test_action_plan_survives():
    """«پیشنهادهای بهبود — قدم‌به‌قدم» جمع‌بندیِ نهایی است و باید بماند."""
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "پیشنهادهای بهبود" in src


# ── بک‌اند ────────────────────────────────────────────────────────────

def test_report_contract_has_no_root_causes():
    """فیلدِ قدیمیِ ``root_causes`` رفت؛ جایش را ``root_cause_chains`` گرفت."""
    src = _read("reports", "exam_report.py")
    assert '"root_causes":' not in src
    assert "root_cause_lines" not in src


def test_report_contract_has_no_missing_gear():
    src = _read("reports", "exam_report.py")
    assert '"missing_gear": record.get' not in src


def test_prompt_no_longer_asks_for_root_cause_hypotheses():
    """گراف رفت، پس تولیدِ فرضیه‌های ریشه هم توکن‌سوزیِ بی‌مصرف است."""
    from ai.cross_check import _EXAM_PROMPT

    assert '"root_cause_hypotheses": []' not in _EXAM_PROMPT
    assert "را تولید نکن" in _EXAM_PROMPT
    assert "root_cause_hypotheses" in _EXAM_PROMPT


def test_prompt_states_the_four_outputs():
    from ai.cross_check import _EXAM_PROMPT

    assert "چهار چیز" in _EXAM_PROMPT
    for needle in (
        "تحلیل کلی ابعاد پنج‌گانه",
        "شکارِ تناقض‌های واقعی",
        "تحلیل تشخیصیِ تک‌تکِ سؤال‌ها",
        "تمرین‌های شفاف",
    ):
        assert needle in _EXAM_PROMPT, f"«{needle}» در فهرستِ خروجی‌ها نیست"


def test_pdf_sections_mirror_the_report():
    """PDF نباید بخشی را نشان دهد که در صفحه نیست."""
    src = _read("reports", "exam_report.py")
    assert '"تحلیل ریشه‌ای بدفهمی‌ها"' not in src
    assert '"موارد هنوز روشن‌نشده"' not in src
    assert '"پیشنهادهای بهبود"' in src
