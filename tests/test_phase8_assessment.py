"""آزمون‌های فاز ۸ — بازسازیِ ایرادهای آزمونِ واقعی «قانون اهم».

هر تست به یک ایرادِ مشاهده‌شده در اجرای واقعی گره خورده است:

  ۱. مدل: پیش‌فرضِ ارزیابی دقیقاً ``deepseek/deepseek-v4.1-flash-1017``، بدونِ
     سوییچِ خاموش به مدل‌های رایگان، با ثبتِ هزینه/توکنِ همهٔ تلاش‌ها.
  ۲. کیفیتِ سؤال: Q1 تک‌پرسش و بی‌عدد، Q2 چهار گزینهٔ مستقل + کلیدِ معتبر،
     «مدار» به‌جای «دایره» در متنِ الکتریکی (و هندسه دست‌نخورده).
  ۳. حکم: MASTERED فقط با درستیِ محتواییِ Q3 و Q4؛ پاسخِ بلندِ نیمه‌درست
     ارتقا نمی‌یابد؛ حکم/عنوان/خلاصه یک داستان می‌گویند.
  ۴. گزارش: پیشنهادها رشتهٔ تمیز، نشتِ انگلیسی ترجمه، وضعیتِ مرحله فارسی.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import ai.cross_check as cross_check
import ai.model_abstraction as ma
from ai.cross_check import (
    canonical_stage_status,
    compute_debugging_strength,
    normalize_suggestions,
    _verdict_conflict,
)
from ai.stage_chain import (
    fix_terminology,
    normalize_stage_items,
    question_quality_issues,
    apply_quality_fixes,
)
from reports.fa_map import scrub_english_leaks, fa_text


# ═══════════════════════════════════════════════════════════════════════════
# ۱) مدل — پین‌شدن، بدونِ سوییچِ خاموش، حسابداریِ تلاش‌ها
# ═══════════════════════════════════════════════════════════════════════════
def test_default_assessment_model_is_the_pinned_deepseek():
    from config import settings

    pinned = settings.OPENROUTER_ASSESSMENT_MODEL
    assert pinned.strip(), "مدل ارزیابی نباید خالی باشد"
    # شرطِ کاربر: نسخهٔ دقیق، نه :batch و نه R1
    if not pinned.startswith("deepseek/deepseek-v4.1-flash-1017"):
        pytest.skip(f"override شده در محیط: {pinned}")
    assert ":batch" not in pinned
    assert "r1" not in pinned.lower()


def test_assessment_tasks_are_routed_to_the_pinned_model():
    assert {"generate_test_booklet", "analyze_exam", "analyze_response"} <= ma.ASSESSMENT_TASKS
    assert ma.assessment_model_name()


def test_pinned_model_never_silently_switches_to_a_free_model():
    """خطای گذرا نباید مدل را عوض کند؛ فقط همان مدل دوباره امتحان می‌شود."""
    calls: list[str] = []

    class _Provider(ma.OpenRouterProvider):
        def __init__(self):
            self.model_name = "deepseek/deepseek-v4.1-flash-1017"

        def _post_chat_completion(self, prompt, temperature, model):
            calls.append(model)
            if len(calls) < 3:
                raise ma.AIProviderError("429 rate-limited", retryable=True)
            return {
                "choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 120, "cost": 0.0031},
            }

        def fetch_active_free_models(self, force_refresh=False):
            return ["free/a", "free/b"]

        def _model_supports_json(self, model):
            return False

        def _throttle(self):
            pass

    provider = _Provider()
    response = provider._generate_with_fallback(
        "p", "generate_test_booklet", 0.7, model_override=ma.assessment_model_name()
    )
    assert len(set(calls)) == 1, f"مدل عوض شد: {calls}"
    assert calls[0] == ma.assessment_model_name()
    assert response.attempts == 3


def test_cost_comes_from_usage_not_from_a_hardcoded_price_table():
    """هزینه فقط از ``usage.cost`` پاسخِ OpenRouter خوانده می‌شود."""
    tokens, cost, prompt_tokens, completion_tokens = ma.OpenRouterProvider._usage_from(
        {"usage": {"total_tokens": 1000, "cost": 0.0123}}, "p", "t", "some/model"
    )
    assert (tokens, cost) == (1000, 0.0123)

    # تفکیکِ ورودی/خروجی از همان usage خوانده می‌شود
    tokens2, _, pt, ct = ma.OpenRouterProvider._usage_from(
        {"usage": {"prompt_tokens": 900, "completion_tokens": 100, "total_tokens": 1000}},
        "p", "t", "some/model",
    )
    assert (tokens2, pt, ct) == (1000, 900, 100)

    # بدونِ usage.cost هیچ قیمتی از خودمان نمی‌سازیم.
    _, cost_unknown, _, _ = ma.OpenRouterProvider._usage_from(
        {}, "p" * 400, "t" * 400, "some/model"
    )
    assert cost_unknown == 0.0

    # جدولِ قیمتِ هاردکد باید حذف شده باشد.
    assert not hasattr(ma.OpenRouterProvider, "_PRICING_PER_1K")
    assert not hasattr(ma.OpenRouterProvider, "_estimate_cost")


def test_response_reports_total_cost_across_all_attempts():
    response = ma.AIResponse(
        text="x",
        model_name="m",
        token_count=100,
        cost_usd=0.01,
        failed_cost_usd=0.02,
        failed_tokens=50,
    )
    assert response.total_cost_usd == pytest.approx(0.03)
    assert response.total_tokens == 150


# ═══════════════════════════════════════════════════════════════════════════
# ۲) کیفیتِ سؤال
# ═══════════════════════════════════════════════════════════════════════════
def test_philosophy_stage_must_be_a_single_question():
    multi = {
        "order": 1,
        "exam_type": "philosophy",
        "text": "چرا به مفهوم قانون اهم نیاز شد؟ و مقاومت اصلاً چیست؟ و چه چیزی را می‌سنجد؟",
    }
    assert "philosophy_multi_question" in question_quality_issues(multi)

    single = {
        "order": 1,
        "exam_type": "philosophy",
        "text": "چرا انسان‌ها برای توصیفِ رفتارِ مدار به مفهومِ تازه‌ای نیاز پیدا کردند؟",
    }
    assert question_quality_issues(single) == []


def test_philosophy_and_perturbation_must_not_contain_numbers_or_formulas():
    assert "philosophy_has_number" in question_quality_issues(
        {"order": 1, "exam_type": "philosophy", "text": "چرا ۱۲ ولت را تقسیم می‌کنیم؟"}
    )
    assert "perturbation_has_formula" in question_quality_issues(
        {"order": 3, "exam_type": "perturbation", "text": "وقتی $R$ کم شود چه می‌شود؟"}
    )


def test_mcq_requires_four_independent_options_and_a_valid_key():
    base = {"order": 2, "exam_type": "mask_mcq", "text": "جریان چند آمپر است؟"}
    assert "mcq_needs_four_options" in question_quality_issues(
        {**base, "options": ["الف", "ب", "ج"], "correct_option_index": 1}
    )
    assert "mcq_duplicate_options" in question_quality_issues(
        {**base, "options": ["۳", "۳", "۵", "۶"], "correct_option_index": 1}
    )
    assert "mcq_missing_key" in question_quality_issues(
        {**base, "options": ["۳", "۴", "۵", "۶"], "correct_option_index": None}
    )
    assert question_quality_issues(
        {**base, "options": ["۳", "۴", "۵", "۶"], "correct_option_index": 0}
    ) == []


def test_correct_option_key_is_never_exposed_to_the_student():
    from api.routes_assessment import _question_to_exam_dict

    class _Q:
        id = 1
        concept_id = 1
        text = "جریان چند آمپر است؟"
        question_type = "mask_mcq"
        difficulty = "medium"
        cognitive_type = "conceptual"
        rubric = {
            "exam_type": "mask_mcq",
            "options": ["$۳$ آمپر", "$۴$ آمپر", "$۶$ آمپر", "$۱۲$ آمپر"],
            "correct_option_index": 0,
            "expected_logic": "قانون اهم",
        }

    payload = _question_to_exam_dict(_Q(), 2)
    assert "correct_option_index" not in payload
    assert "expected_logic" not in payload


def test_circuit_context_uses_madار_not_daere():
    """«دایره» فقط در هندسه درست است؛ در مدار باید «مدار» شود."""
    assert "دایره" not in fix_terminology(
        "وقتی مقاومت کم می‌شود، جریان در دایرهٔ الکتریکی بیشتر می‌شود."
    )
    # هندسه دست‌نخورده می‌ماند — جایگزینیِ سراسری ممنوع است.
    geometry = "نسبتِ محیط به قطر در هر دایره ثابت و برابرِ عددِ پی است."
    assert "دایره" in fix_terminology(geometry)


def test_wrong_terminology_is_flagged_in_quality_check():
    item = {
        "order": 3,
        "exam_type": "perturbation",
        "text": "در این دایره، اگر مقاومت کم شود جریان چه می‌کند؟",
    }
    assert "wrong_terminology_daere" in question_quality_issues(item)


def test_quality_fixes_are_applied_during_normalization():
    raw = [
        {
            "order": 1,
            "exam_type": "philosophy",
            "text": "چرا این مفهوم ساخته شد؟",
            "options": None,
            "correct_option_index": None,
        },
        {
            "order": 3,
            "exam_type": "perturbation",
            "text": "در دایرهٔ برقی با کاهش مقاومت چه می‌شود؟",
            "options": None,
            "correct_option_index": None,
        },
    ]
    items = normalize_stage_items(raw)
    perturbation = next(i for i in items if i["exam_type"] == "perturbation")
    assert "دایره" not in perturbation["text"]


# ═══════════════════════════════════════════════════════════════════════════
# ۳) حکم — سازگاریِ نهایی و جلوگیری از MASTERED کاذب
# ═══════════════════════════════════════════════════════════════════════════
def test_stage_status_aliases_map_to_four_canonical_states():
    assert canonical_stage_status("CORRECT") == "CORRECT"
    assert canonical_stage_status("CONFIRMED") == "CORRECT"
    assert canonical_stage_status("HALF_CORRECT") == "HALF_CORRECT"
    assert canonical_stage_status("PARTIALLY_CORRECT") == "HALF_CORRECT"
    assert canonical_stage_status("WRONG") == "WRONG"
    assert canonical_stage_status("") == "INSUFFICIENT_EVIDENCE"


def test_debugging_strength_is_semantic_not_length_based():
    """پاسخِ نیمه‌درستِ Q4، هر چقدر هم بلند، «قوی» نیست."""
    half = [{"order": 3, "status": "CORRECT"}, {"order": 4, "status": "HALF_CORRECT"}]
    assert compute_debugging_strength(half, {"relevant_semantic_answers": True}) is False

    full = [{"order": 3, "status": "CORRECT"}, {"order": 4, "status": "CORRECT"}]
    assert compute_debugging_strength(full, {"relevant_semantic_answers": True}) is True


def test_off_topic_answers_block_debugging_strength():
    full = [{"order": 3, "status": "CORRECT"}, {"order": 4, "status": "CORRECT"}]
    assert compute_debugging_strength(full, {"relevant_semantic_answers": False}) is False


def test_mastered_verdict_conflicts_with_half_correct_q4():
    per_q = [{"order": 3, "status": "CORRECT"}, {"order": 4, "status": "HALF_CORRECT"}]
    assert _verdict_conflict("MASTERED", per_q) is not None


def test_mastered_with_wrong_q3_is_a_conflict():
    per_q = [{"order": 3, "status": "WRONG"}, {"order": 4, "status": "CORRECT"}]
    assert _verdict_conflict("MASTERED", per_q) is not None


def test_mastered_with_correct_q3_q4_has_no_conflict():
    per_q = [{"order": 3, "status": "CORRECT"}, {"order": 4, "status": "CORRECT"}]
    assert _verdict_conflict("MASTERED", per_q) is None


# ── سناریوی واقعیِ کاربر ───────────────────────────────────────────────────
OHM_ROWS = [
    {"order": 1, "exam_type": "philosophy", "stage_title": "مرحله ۱: فلسفه",
     "text": "چرا به مفهوم مقاومت نیاز شد؟", "options": [],
     "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "نسبت ولتاژ به جریان در رسانای اهمی ثابت است"},
    {"order": 2, "exam_type": "mask_mcq", "stage_title": "مرحله ۲: تست",
     "text": "در مداری با $۱۲$ ولت و $۴$ اهم، جریان چند آمپر است؟",
     "options": ["$۳$", "$۴$", "$۸$", "$۱۶$"],
     "correct_option_index": 0, "forbidden_words": [],
     "expected_logic": "I = V/R = 3"},
    {"order": 3, "exam_type": "perturbation", "stage_title": "مرحله ۳: دستکاری",
     "text": "با ثابت بودن ولتاژ، کاهش مقاومت چه بر سر جریان و توان می‌آورد؟",
     "options": [], "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "جریان بیشتر می‌شود و توان هم بیشتر؛ P = VI"},
    {"order": 4, "exam_type": "debugging", "stage_title": "مرحله ۴: عیب‌یابی",
     "text": "امیر می‌گوید مقاومت خودش را تنظیم می‌کند تا جریان ثابت بماند.",
     "options": [], "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "مقاومت ویژگیِ ذاتیِ رسانا در دمای ثابت است و با ولتاژ عوض نمی‌شود"},
    {"order": 5, "exam_type": "feynman_synthesis", "stage_title": "مرحله ۵: فاینمن",
     "text": "برای بچهٔ ۱۰ ساله توضیح بده",
     "options": [], "correct_option_index": None,
     "forbidden_words": ["مقاومت", "ولتاژ", "جریان", "قانون اهم"],
     "expected_logic": "تمثیل شلنگ آب با معادل‌گیریِ واقعی"},
]

OHM_ANSWERS = {
    1: "راستش نمی‌دانم رسانای اهمی چه ساختاری دارد و چرا مقاومتش ثابت می‌ماند.",
    2: "گزینه ۱",
    3: "چون ولتاژ ثابت است و مقاومت کم شده، جریان بیشتر می‌شود و توان هم چون حاصل‌ضرب ولتاژ در جریان است بیشتر می‌شود.",
    4: "امیر اشتباه می‌کند، چون فقط حاصل‌ضرب ولتاژ در جریان تغییر می‌کند و مقاومت هم عوض می‌شود.",
    5: "مثل شلنگ باغبانی است؛ وقتی نوکش را تنگ می‌کنی آب تندتر بیرون می‌آید.",
}


class _Resp:
    model_name = "deepseek/deepseek-v4.1-flash-1017"
    cost_usd = 0.0

    def __init__(self, text: str) -> None:
        self.text = text


def _run(monkeypatch, payload):
    class _Router:
        async def generate(self, prompt, task_type, temperature=0.3):
            return _Resp(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    return asyncio.run(
        cross_check.analyze_stage_chain("قانون اهم", OHM_ROWS, OHM_ANSWERS)
    )


def test_real_scenario_model_says_mastered_but_q4_is_half_correct(monkeypatch):
    """قلبِ فاز ۸: مدل کلی MASTERED می‌دهد، ولی Q4 نیمه‌درست است.

    لایهٔ سازگارسازیِ کد باید حکم را اصلاح کند، نه اینکه حرفِ مدل را قبول کند.
    """
    result = _run(monkeypatch, {
        "mastery_status": "MASTERED",
        "persona_title": "مهندسی که ساعت را بست",
        "executive_summary": "مفهوم را کامل بلدی و هیچ چیز جا نمانده است.",
        "cross_check_findings": [],
        "improvement_suggestions": ["تمرین بیشتر"],
        "per_question": [
            {"order": 1, "status": "INSUFFICIENT_EVIDENCE",
             "cognitive_verdict": "نمی‌داند"},
            {"order": 2, "status": "CORRECT", "cognitive_verdict": "درست"},
            {"order": 3, "status": "CORRECT", "cognitive_verdict": "زنجیرهٔ علّی درست"},
            {"order": 4, "status": "HALF_CORRECT",
             "cognitive_verdict": "فقط گفت حاصل‌ضرب عوض می‌شود",
             "missing_gear": "چراییِ عدمِ خودتنظیمیِ مقاومت"},
            {"order": 5, "status": "HALF_CORRECT", "cognitive_verdict": "تمثیل بدون معادل"},
        ],
    })

    assert result["mastery_status"] != "MASTERED", "MASTERED کاذب صادر شد"
    # نشان و خلاصه نباید داستانِ متفاوت بگویند
    assert "ساعت را بست" not in str(result["persona_title"])
    assert "کامل بلدی" not in result["executive_summary"]
    # Q2+Q3 تنها کافی نیست — و سیگنالِ طول/کلمه دیگر وجود ندارد
    assert "debugging_strong" not in result["signals"]
    assert "substantive" not in result["signals"]
    assert "word_counts" not in result["signals"]


def test_honest_scenario_with_true_core_critique_can_be_mastered(monkeypatch):
    """Q3 و Q4 واقعاً درست ⇒ قواعدِ قطعی حکم را به MASTERED می‌رسانند.

    توجه: در این تست فقط پنج رکوردِ قدیمی (مرحله‌محور) داده شده و سؤال ۵
    هیچ رکوردی ندارد؛ پس مرحلهٔ ۵ «بی‌پاسخ» نیست بلکه اصلاً سنجیده نشده و
    مانعِ تسلط نمی‌شود. کالیبراسیونِ Q3+Q4+Q5 در تست‌های فاز ۱۱ سنجیده
    می‌شود که هر ده سؤال را می‌دهند.
    """
    result = _run(monkeypatch, {
        "mastery_status": "MASTERED",
        "persona_title": "مهندسی که ساعت را بست",
        "executive_summary": "مفهوم را عمیقاً بلدی.",
        "cross_check_findings": [],
        "improvement_suggestions": ["تمرین بیان ساده"],
        "per_question": [
            {"order": 1, "status": "INSUFFICIENT_EVIDENCE", "cognitive_verdict": "نمی‌داند"},
            {"order": 2, "status": "CORRECT"},
            {"order": 3, "status": "CORRECT", "cognitive_verdict": "زنجیرهٔ کامل"},
            {"order": 4, "status": "CORRECT",
             "cognitive_verdict": "هستهٔ نقد را دقیقاً گفت"},
            {"order": 5, "status": "HALF_CORRECT", "cognitive_verdict": "بیانِ ساده ضعیف"},
        ],
    })
    # در ورودیِ پنج‌رکوردیِ مرحله‌محور، مرحلهٔ ۵ رکوردی ندارد و مانع نمی‌شود.
    assert result["mastery_status"] == "MASTERED"


def test_verdict_persona_and_summary_are_one_story(monkeypatch):
    result = _run(monkeypatch, {
        "mastery_status": "MASTERED",
        "persona_title": "مهندسی که ساعت را بست",
        "executive_summary": "هیچ نقصی نداری.",
        "cross_check_findings": [],
        "per_question": [
            {"order": 3, "status": "CORRECT"},
            {"order": 4, "status": "WRONG", "missing_gear": "مفهومِ رسانای اهمی"},
        ],
    })
    assert result["mastery_status"] != "MASTERED"
    assert result["persona_title"] != "مهندسی که ساعت را بست"
    assert result["executive_summary"] != "هیچ نقصی نداری."


def test_empty_answer_is_never_scored_correct(monkeypatch):
    answers = dict(OHM_ANSWERS)
    answers.pop(4)
    class _Router:
        async def generate(self, prompt, task_type, temperature=0.3):
            return _Resp(json.dumps({
                "mastery_status": "MASTERED",
                "per_question": [{"order": 4, "status": "CORRECT"}],
                "cross_check_findings": [],
            }, ensure_ascii=False))
    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    result = asyncio.run(
        cross_check.analyze_stage_chain("قانون اهم", OHM_ROWS, answers)
    )
    q4 = next(r for r in result["per_question"] if r["order"] == 4)
    assert q4["status"] == "INSUFFICIENT_EVIDENCE"


def test_per_question_always_covers_all_five_stages(monkeypatch):
    result = _run(monkeypatch, {"mastery_status": "PARTIAL_FRAGMENTED", "per_question": []})
    assert [r["order"] for r in result["per_question"]] == [1, 2, 3, 4, 5]


# ═══════════════════════════════════════════════════════════════════════════
# ۴) گزارش — پیشنهادها، نشتِ انگلیسی، فارسیِ روان
# ═══════════════════════════════════════════════════════════════════════════
def test_suggestions_never_reach_the_ui_as_raw_dicts():
    raw = [
        {"suggestion": "قدمِ اول: تمرینِ تناقض"},
        {"text": "قدمِ دوم: بازگویی با تمثیل"},
        {"description": "قدمِ سوم"},
        "قدمِ چهارم",
        {"suggestion": "قدمِ اول: تمرینِ تناقض"},  # تکراری
        None,
        {},
    ]
    cleaned = normalize_suggestions(raw)
    assert cleaned == [
        "قدمِ اول: تمرینِ تناقض",
        "قدمِ دوم: بازگویی با تمثیل",
        "قدمِ سوم",
        "قدمِ چهارم",
    ]
    assert all(isinstance(s, str) for s in cleaned)
    assert not any("[object Object]" in s or "{" in s for s in cleaned)


def test_suggestions_accept_a_bare_string():
    assert normalize_suggestions("فقط یک پیشنهاد") == ["فقط یک پیشنهاد"]


def test_english_leaks_are_translated_but_math_is_preserved():
    out = scrub_english_leaks(
        "مقاومت یک ویژگیِ intrinsic رساناست و $R = V/I$ با ولتاژ عوض نمی‌شود."
    )
    assert "intrinsic" not in out
    assert "ذاتی" in out
    assert "$R = V/I$" in out


def test_english_leaks_in_short_persian_sentences_are_flagged():
    assert "analogy" not in scrub_english_leaks("این analogy خوبی برای فهم است.")


def test_fully_english_text_still_falls_back():
    fallback = "متنِ فارسیِ جانشین"
    assert fa_text("This whole sentence is in English and should not pass", fallback) == fallback


def test_stage_status_has_persian_labels():
    from models.question import STATUS_FA

    assert STATUS_FA["CORRECT"] == "درست"
    assert STATUS_FA["HALF_CORRECT"] == "نیمه‌درست"
    assert STATUS_FA["WRONG"] == "نادرست"
