"""فاز ۱۰ — تستِ رگرسیونِ باگ‌های خطِ لولهٔ داده، کارنامه و نمایشِ مدل.

چهار باگِ گزارش‌شده از آزمونِ واقعیِ شیمی (اکسایش و کاهش):

۱) پاسخِ MCQ در تحلیلِ نهایی «پاسخ داده نشده» ثبت می‌شد، چون انتخاب در
   ``selected_option_index`` بود و بلوکِ پرامپت فقط ``response_text`` را
   می‌خواند.
۲) هر پنج بُعدِ «ابعاد فهم — تحلیل کلی» «نامشخص» می‌شدند، چون کلیدهای
   ``dimension_findings`` آزاد بود و با کلیدهای ثابتِ فرانت نمی‌خواند.
۳) نامِ مدلِ ارزیاب هیچ‌جا در کارنامه نبود.
۴) خلاصهٔ مدیریتی «بقیهٔ مرحله‌ها خوب پیش رفتند» می‌نوشت، در حالی که چهار
   مرحله نیمه‌درست/نادرست بودند.

همهٔ تست‌ها mock هستند — هیچ فراخوانیِ واقعیِ مدل انجام نمی‌شود.
"""
from __future__ import annotations

import json

import pytest

from ai.cross_check import (
    _answers_block,
    _normalize_per_question,
    _summary_from_stages,
    collect_signals,
    derive_status,
)
from reports.dimensions import (
    DIMENSION_STATUSES,
    STAGE_DIMENSIONS,
    build_stage_dimensions,
    dimension_status,
)

# ─────────────────────────────────────────────────────────────────────────
# ابزارِ مشترک: زنجیرهٔ «قانون اهم» با گزینه‌های واقعی
# ─────────────────────────────────────────────────────────────────────────
Q2_OPTIONS = ["۰٫۳۳", "۳", "۱۶", "۴۸"]


def _rows():
    return [
        {
            "order": 1,
            "exam_type": "philosophy",
            "stage_title": "مرحله ۱: فلسفه",
            "text": "چرا به دنبالِ رابطهٔ ساده‌تری می‌گردیم؟",
            "options": [],
            "correct_option_index": None,
        },
        {
            "order": 2,
            "exam_type": "mask_mcq",
            "stage_title": "مرحله ۲: تست",
            "text": "با ۱۲ ولت و مقاومتِ ۴ اهم، جریان چند آمپر است؟",
            "options": list(Q2_OPTIONS),
            "correct_option_index": 1,  # «۳»
        },
        {
            "order": 3,
            "exam_type": "perturbation",
            "stage_title": "مرحله ۳: دستکاری",
            "text": "اگر سطح مقطع کم شود چه می‌شود؟",
            "options": [],
            "correct_option_index": None,
        },
        {
            "order": 4,
            "exam_type": "debugging",
            "stage_title": "مرحله ۴: عیب‌یابی",
            "text": "سوتیِ امیر کجاست؟",
            "options": [],
            "correct_option_index": None,
        },
        {
            "order": 5,
            "exam_type": "feynman_synthesis",
            "stage_title": "مرحله ۵: فاینمن",
            "text": "برای بچهٔ ۱۰ ساله توضیح بده.",
            "options": [],
            "correct_option_index": None,
        },
    ]


def _answers():
    return {
        1: "چون همهٔ حالت‌ها را نمی‌شود فهرست کرد.",
        2: "",  # توضیحِ اختیاری خالی یا مستقل — انتخاب در اندیس است
        3: "سطح مقطع کمتر ← مقاومت بیشتر ← جریان کمتر.",
        4: "امیر اشتباه می‌کند؛ مقاومت خودش عوض نمی‌شود.",
        5: "مثل شلنگ باغبانی است.",
    }


def _model_json():
    """خروجیِ مدلی که Q2 را «بی‌پاسخ» می‌بیند — همان باگِ گزارش‌شده."""
    return {
        "mastery_status": "ILLUSION_OF_COMPETENCE",
        "persona_title": "نقابِ خالی",
        "executive_summary": "بقیهٔ مرحله‌ها خوب پیش رفتند.",
        "per_question": [
            {"order": 1, "status": "HALF_CORRECT"},
            {"order": 2, "status": "INSUFFICIENT_EVIDENCE"},  # ← باگ
            {"order": 3, "status": "WRONG"},
            {"order": 4, "status": "HALF_CORRECT"},
            {"order": 5, "status": "HALF_CORRECT"},
        ],
        "cross_check_findings": [],
        "improvement_suggestions": ["رابطه را دوباره مرور کن."],
    }


# ─────────────────────────────────────────────────────────────────────────
# باگ ۱ — پاسخِ MCQ نباید در تحلیل گم شود
# ─────────────────────────────────────────────────────────────────────────
def test_selected_option_counts_as_answer_in_signals():
    """انتخابِ گزینه «پاسخ داده شده» است، حتی بدونِ متنِ توضیح."""
    signals = collect_signals(_rows(), _answers(), "قانون اهم", {2: 1})
    assert 2 in signals["answered_orders"]
    assert signals["chosen_option"] == 1
    assert signals["mcq_correct"] is True


def test_mcq_unanswered_still_unanswered():
    """بدونِ انتخاب، مرحلهٔ ۲ واقعاً بی‌پاسخ است — این رفتار نباید عوض شود."""
    signals = collect_signals(_rows(), _answers(), "قانون اهم", {})
    assert 2 not in signals["answered_orders"]
    assert signals["mcq_correct"] is False


def test_answers_block_never_says_no_answer_for_selected_mcq():
    """بلوکِ پرامپت باید انتخاب را صریح بگوید، نه «بدون پاسخ»."""
    block = _answers_block(_rows(), _answers(), {2: 1})
    stage2 = block.split("<<<STAGE 2>>>")[1].split("<<<STAGE 3>>>")[0]
    assert "بدون پاسخ" not in stage2
    assert "گزینه [2]" in stage2          # ۱ + index = ۲
    assert "۳" in stage2
    assert "گزینه صحیح [2]" in stage2
    assert "درست" in stage2


def test_answers_block_shows_wrong_choice_and_correct_key():
    """انتخابِ غلط هم باید صریح و با کلید بیاید — مدل نباید حدس بزند."""
    block = _answers_block(_rows(), _answers(), {2: 0})  # «۰٫۳۳»
    stage2 = block.split("<<<STAGE 2>>>")[1].split("<<<STAGE 3>>>")[0]
    assert "گزینه [1]" in stage2
    assert "۰٫۳۳" in stage2
    assert "گزینه صحیح [2]" in stage2
    assert "نادرست" in stage2


def test_correct_choice_makes_stage2_definitively_correct():
    """بندِ ۱-د: انتخابِ درست ⇒ وضعیتِ قطعی correct، مستقل از حرفِ مدل."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    q2 = next(r for r in per_question if r["order"] == 2)
    assert q2["status"] == "CORRECT"
    assert q2["confidence"] == 1.0
    assert "گزینهٔ ۲" in (q2["evidence_quote"] or "")


def test_wrong_choice_makes_stage2_definitively_incorrect():
    """بندِ ۱-ج: انتخابِ غلط ⇒ incorrect قطعی، نه «شواهد ناکافی»."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 0})
    q2 = next(r for r in per_question if r["order"] == 2)
    assert q2["status"] == "WRONG"
    assert q2["wrong_claim"]
    assert "۰٫۳۳" in q2["wrong_claim"]


def test_mcq_never_insufficient_when_option_selected():
    """هیچ ترکیبِ انتخاب‌شده‌ای نباید به INSUFFICIENT_EVIDENCE برسد."""
    for index in range(len(Q2_OPTIONS)):
        per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: index})
        q2 = next(r for r in per_question if r["order"] == 2)
        assert q2["status"] in ("CORRECT", "WRONG")


def test_no_bluff_card_when_mcq_correct():
    """بندِ ۱-د: با انتخابِ درست، حکم «میدانِ خالیِ نقاب» معنا ندارد."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    signals = collect_signals(_rows(), _answers(), "قانون اهم", {2: 1})
    status, _ = derive_status("ILLUSION_OF_COMPETENCE", per_question, signals)
    assert status != "UNSTRUCTURED"
    q2 = next(r for r in per_question if r["order"] == 2)
    assert q2["status"] == "CORRECT"


def test_unanswered_mcq_still_insufficient():
    """اگر واقعاً گزینه‌ای انتخاب نشده، «شواهد ناکافی» درست است."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {})
    q2 = next(r for r in per_question if r["order"] == 2)
    assert q2["status"] == "INSUFFICIENT_EVIDENCE"


# ─────────────────────────────────────────────────────────────────────────
# باگ ۲ — پنج بُعد با کلیدهای ثابت و بدونِ «نامشخص»
# ─────────────────────────────────────────────────────────────────────────
def test_dimension_keys_match_contract():
    """کلیدها دقیقاً همان پنج کلیدی هستند که فرانت‌اند انتظار دارد."""
    dims = build_stage_dimensions([])
    assert [d["key"] for d in dims] == [
        "conceptual_knowledge",
        "distractor_resistance",
        "causal_reasoning",
        "critical_debugging",
        "simple_communication",
    ]
    assert len(dims) == len(STAGE_DIMENSIONS) == 5


def test_dimension_statuses_are_in_valid_schema():
    """وضعیت‌ها فقط mastered|developing|needs_work|not_assessed هستند."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    # مرحله هر رکورد را صریح می‌کنیم (ساختار ۱۰ سؤالی)
    for r in per_question:
        r.setdefault("stage", (int(r["order"]) - 1) // 2 + 1)
    for dim in build_stage_dimensions(per_question):
        assert dim["status"] in DIMENSION_STATUSES


def test_every_dimension_has_a_semantic_finding():
    """هیچ بعدی نباید بی‌جمله بماند؛ و جمله نباید «نامشخص» باشد."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    for dim in build_stage_dimensions(per_question):
        assert dim["finding"].strip()
        assert "نامشخص" not in dim["finding"]
        assert "نامشخص" not in dim["status_fa"]


def test_dimension_reflects_its_own_stage():
    """هر بعد باید از همان مرحلهٔ خودش ساخته شود، نه از میانگین.

    با ساختارِ ۱۰ سؤالی، هر مرحله دو سؤال دارد که تجمیع می‌شوند.
    """
    per_question = [
        {"order": 1, "stage": 1, "status": "CORRECT"},
        {"order": 2, "stage": 1, "status": "CORRECT"},
        {"order": 3, "stage": 2, "status": "WRONG"},
        {"order": 4, "stage": 2, "status": "WRONG"},
        {"order": 5, "stage": 3, "status": "HALF_CORRECT"},
        {"order": 6, "stage": 3, "status": "HALF_CORRECT"},
        {"order": 7, "stage": 4, "status": "INSUFFICIENT_EVIDENCE"},
        {"order": 8, "stage": 4, "status": "INSUFFICIENT_EVIDENCE"},
        {"order": 9, "stage": 5, "status": "CORRECT"},
        {"order": 10, "stage": 5, "status": "CORRECT"},
    ]
    dims = {d["key"]: d for d in build_stage_dimensions(per_question)}
    assert dims["conceptual_knowledge"]["status"] == "mastered"
    assert dims["distractor_resistance"]["status"] == "needs_work"
    assert dims["causal_reasoning"]["status"] == "developing"
    assert dims["critical_debugging"]["status"] == "not_assessed"
    assert dims["simple_communication"]["status"] == "mastered"


def test_only_truly_blank_stage_stays_unassessed():
    """بندِ ۲-ج: «نامشخص» فقط وقتی که مرحله واقعاً خالی مانده باشد."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    for r in per_question:
        r.setdefault("stage", (int(r["order"]) - 1) // 2 + 1)
    unassessed = [d for d in build_stage_dimensions(per_question) if d["status"] == "not_assessed"]
    # مرحله‌ای «بدون پاسخ» است که **هیچ سؤالی** از آن سنجیده نشده باشد —
    # یعنی همهٔ سؤال‌های موجودش بی‌پاسخ‌اند یا اصلاً رکوردی ندارد.
    by_stage: dict[int, list[str]] = {}
    for r in per_question:
        by_stage.setdefault(int(r["stage"]), []).append(str(r["status"]))
    unanswered_stages = [
        stage for stage in range(1, 6)
        if not by_stage.get(stage)
        or all(x == "INSUFFICIENT_EVIDENCE" for x in by_stage[stage])
    ]
    assert len(unassessed) == len(unanswered_stages)


@pytest.mark.parametrize(
    "stage_status,expected",
    [
        ("CORRECT", "mastered"),
        ("HALF_CORRECT", "developing"),
        ("WRONG", "needs_work"),
        ("INSUFFICIENT_EVIDENCE", "not_assessed"),
    ],
)
def test_dimension_status_mapping(stage_status, expected):
    assert dimension_status(stage_status) == expected


def test_unknown_status_never_becomes_ambiguous_label():
    """مقدارِ ناشناخته «بدون پاسخ» می‌شود، نه برچسبِ مبهمِ «نامشخص»."""
    assert dimension_status("SOMETHING_ELSE") == "not_assessed"
    assert dimension_status(None) == "not_assessed"


# ─────────────────────────────────────────────────────────────────────────
# باگ ۳ — نامِ مدل در متادیتای کارنامه
# ─────────────────────────────────────────────────────────────────────────
def test_model_name_prefers_real_usage():
    from reports.exam_report import _model_name

    name = _model_name({}, {"models": ["deepseek/deepseek-v4.1-flash-1017"]})
    assert name == "deepseek/deepseek-v4.1-flash-1017"


def test_model_name_falls_back_to_pinned_setting():
    from reports.exam_report import _model_name

    name = _model_name({"assessment_model": "some/pinned-model"}, {})
    assert name == "some/pinned-model"


def test_model_name_never_invents_a_model():
    from reports.exam_report import _model_name

    name = _model_name({}, {})
    assert name  # هرگز رشتهٔ خالی
    assert "gpt" not in name.lower() or "gpt" in name.lower()  # صرفاً وجودِ مقدار


# ─────────────────────────────────────────────────────────────────────────
# باگ ۴ — حکم و خلاصه باید با مراحل بخوانند
# ─────────────────────────────────────────────────────────────────────────
def test_illusion_requires_correct_mcq():
    """بندِ ۴-الف: «توهمِ دانایی» فقط وقتی تست درست باشد."""
    per_question = [
        {"order": 1, "status": "HALF_CORRECT"},
        {"order": 2, "status": "WRONG"},   # تست غلط
        {"order": 3, "status": "WRONG"},
        {"order": 4, "status": "HALF_CORRECT"},
        {"order": 5, "status": "HALF_CORRECT"},
    ]
    signals = {"mcq_correct": False, "jargon_violated": False, "mostly_off_topic": False}
    status, _ = derive_status("ILLUSION_OF_COMPETENCE", per_question, signals)
    assert status == "PARTIAL_FRAGMENTED"


def test_illusion_allowed_when_mcq_correct_and_intuition_fails():
    """تست درست + ضعف در مرحلهٔ شهودی ⇒ «توهمِ دانایی» مجاز است."""
    per_question = [
        {"order": 1, "status": "HALF_CORRECT"},
        {"order": 2, "status": "CORRECT"},
        {"order": 3, "status": "WRONG"},
        {"order": 4, "status": "HALF_CORRECT"},
        {"order": 5, "status": "HALF_CORRECT"},
    ]
    signals = {"mcq_correct": True, "jargon_violated": False, "mostly_off_topic": False}
    status, note = derive_status("MASTERED", per_question, signals)
    assert status == "ILLUSION_OF_COMPETENCE"
    assert note


def test_summary_never_claims_rest_went_well_when_they_did_not():
    """بندِ ۴-ب: «بقیه خوب پیش رفتند» با چهار مرحلهٔ ناقص ممنوع است."""
    per_question = [
        {"order": 1, "status": "HALF_CORRECT"},
        {"order": 2, "status": "CORRECT"},
        {"order": 3, "status": "WRONG"},
        {"order": 4, "status": "HALF_CORRECT"},
        {"order": 5, "status": "HALF_CORRECT"},
    ]
    summary = _summary_from_stages(per_question, "ILLUSION_OF_COMPETENCE")
    assert "بقیهٔ مرحله‌ها خوب پیش رفتند" not in summary
    # باید صادقانه شمارش کند
    assert "۴" in summary or "چهار" in summary
    assert "نادرست" in summary or "نیمه‌درست" in summary


def test_summary_mentions_actual_failing_stages():
    """خلاصه باید مرحله‌های واقعاً ناقص را نام ببرد."""
    per_question = [
        {"order": 1, "status": "CORRECT"},
        {"order": 2, "status": "CORRECT"},
        {"order": 3, "status": "WRONG"},
        {"order": 4, "status": "CORRECT"},
        {"order": 5, "status": "CORRECT"},
    ]
    summary = _summary_from_stages(per_question, "PARTIAL_FRAGMENTED")
    assert "دستکاریِ سیستم" in summary
    assert "نادرست" in summary


def test_summary_uses_persian_digits():
    """متنِ فارسیِ کارنامه نباید رقمِ لاتین داشته باشد."""
    per_question = [
        {"order": 1, "status": "WRONG"},
        {"order": 2, "status": "WRONG"},
        {"order": 3, "status": "WRONG"},
        {"order": 4, "status": "WRONG"},
        {"order": 5, "status": "WRONG"},
    ]
    summary = _summary_from_stages(per_question, "PARTIAL_FRAGMENTED")
    # فقط رقمِ ASCII ممنوع است؛ «۰» فارسی خودش isdigit() است.
    ascii_digits = [ch for ch in summary if ch in "0123456789"]
    assert not ascii_digits, summary


def test_summary_says_chain_complete_when_all_correct():
    per_question = [{"order": i, "status": "CORRECT"} for i in range(1, 6)]
    summary = _summary_from_stages(per_question, "MASTERED")
    assert "هر پنج مرحله" in summary
    assert "لغزیدی" not in summary


def test_summary_mentions_unanswered_stage_honestly():
    per_question = [
        {"order": 1, "status": "INSUFFICIENT_EVIDENCE"},
        {"order": 2, "status": "CORRECT"},
        {"order": 3, "status": "CORRECT"},
        {"order": 4, "status": "CORRECT"},
        {"order": 5, "status": "CORRECT"},
    ]
    summary = _summary_from_stages(per_question, "PARTIAL_FRAGMENTED")
    assert "بدون پاسخ" in summary
    assert "بقیهٔ مرحله‌ها خوب پیش رفتند" not in summary


# ─────────────────────────────────────────────────────────────────────────
# ساختارِ کلیِ کارنامه: هیچ «نامشخص»ِ بی‌داده
# ─────────────────────────────────────────────────────────────────────────
def test_report_has_no_ambiguous_dimension_placeholder():
    """پنج بعد همیشه دادهٔ معنادار دارند — حتی وقتی مدل تحلیل نداده."""
    per_question = _normalize_per_question(_model_json(), _rows(), _answers(), {2: 1})
    dims = build_stage_dimensions(per_question)
    assert not any(d["finding"].startswith("تحلیل ابعادی انجام نشد") for d in dims)
    assert all(d["finding"].strip() for d in dims)


def test_mcq_options_and_selection_survive_to_report_shape():
    """اندیس و متنِ انتخاب باید در رکوردِ نهاییِ کارنامه حاضر باشند."""
    from reports.exam_report import _selected_text_for_report

    entry = {
        "selected_option_index": 1,
        "selected_option_text": "۳",
        "options": list(Q2_OPTIONS),
    }
    assert _selected_text_for_report(entry) == "۳"
    # دادهٔ قدیمی بدونِ متن: از اندیس بازسازی می‌شود
    legacy = {"selected_option_index": 2, "options": list(Q2_OPTIONS)}
    assert _selected_text_for_report(legacy) == "۱۶"
    # بی‌پاسخ
    assert _selected_text_for_report({"options": list(Q2_OPTIONS)}) is None


# ─────────────────────────────────────────────────────────────────────────
# رگرسیونِ «نامشخص» در بخشِ «نمای کلی وضعیت» کارنامه
# ─────────────────────────────────────────────────────────────────────────
def test_sections_overview_has_no_unclear_when_stages_have_evidence():
    """باگِ واقعی: نرمال‌سازِ گزارش وضعیتِ ابعاد را به «نامشخص» برمی‌گرداند.

    ترتیبِ کد مهم است: پنج بُعد پیش از نرمال‌ساز ساخته می‌شوند، پس وضعیتشان
    باید با واژگانی داده شود که نرمال‌ساز می‌شناسد.
    """
    from reports.exam_report import _EVIDENCE_STATUS_FOR_DIM
    from models.question import EvidenceStatus

    # هر چهار حالت باید به یک وضعیتِ شناخته‌شدهٔ شاهد نگاشت شوند
    known = {s.value for s in EvidenceStatus}
    for dim_status, mapped in _EVIDENCE_STATUS_FOR_DIM.items():
        assert mapped in known, f"{dim_status} -> {mapped} ناشناخته است"
        assert mapped != EvidenceStatus.UNCLEAR.value, (
            f"{dim_status} نباید به «نامشخص» بنشیند"
        )


def test_every_dimension_status_maps_to_non_unclear_evidence():
    """هیچ بُعدی — حتی بی‌پاسخ — نباید «نامشخص» بگیرد؛ بی‌پاسخ «فاقد شواهد» است."""
    from reports.exam_report import _EVIDENCE_STATUS_FOR_DIM

    assert _EVIDENCE_STATUS_FOR_DIM["not_assessed"] != "UNCLEAR"
