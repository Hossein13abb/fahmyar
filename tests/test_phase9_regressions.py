"""آزمون‌های فاز ۹ — ایرادهای آزمونِ زندهٔ «قانون اهم» روی ویندوز.

هر تست به یک ایرادِ واقعیِ مشاهده‌شده گره خورده است:

  ۱. نمایش پاسخِ دانش‌آموز در کارنامه (هرگز بازخوردِ مدل جای آن ننشیند)
  ۲. انتخابِ MCQ و نگاشتِ اندیس (توضیحِ حاوی عدد نباید انتخاب را عوض کند)
  ۳. حکمِ مسلط با شاهدِ معنایی (حذفِ کاملِ منطقِ طولِ پاسخ)
  ۴. سازگاریِ کارت‌ها و یافته‌ها (SYNERGY کاذب، برچسبِ متناقض)
  ۵. متنِ سؤال‌ها (لو نرفتنِ تله و پاسخ)
  ۶. ردیابیِ مدل/توکن/هزینه
"""
from __future__ import annotations

import asyncio
import json

import pytest

import ai.cross_check as cross_check
import ai.model_abstraction as ma
from ai.cross_check import (
    apply_q4_claim_guard,
    canonical_stage_status,
    derive_status,
    normalize_suggestions,
    wrong_q4_claim,
    _chosen_option,
    _filter_false_synergy,
)
from ai.stage_chain import (
    leaked_phrases,
    question_quality_issues,
    verify_mcq_key,
)


# ═══════════════════════════════════════════════════════════════════════════
# ۱) نمایشِ پاسخِ دانش‌آموز
# ═══════════════════════════════════════════════════════════════════════════
def test_report_response_is_only_what_the_student_typed():
    """«پاسخِ تو» هرگز نباید حاویِ حکم/بازخوردِ مدل باشد."""
    from reports.exam_report import _raw_student_answer

    entry = {
        "response": "مقاومت ویژگی ذاتی سیم است.",
        "evidence": [
            {
                "cognitive_verdict": "دانش‌آموز مفهوم را نفهمیده",
                "qualitative_feedback": "نیازمند مرور",
                "reasoning": "استدلال ناقص بود",
            }
        ],
    }
    assert _raw_student_answer(entry) == "مقاومت ویژگی ذاتی سیم است."


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_response_never_becomes_model_feedback(empty):
    from reports.exam_report import _raw_student_answer

    assert _raw_student_answer({"response": empty}) == ""


def test_model_output_leaked_into_response_is_not_shown():
    from reports.exam_report import _raw_student_answer

    leaked = '{"cognitive_verdict": "نفهمیده", "missing_gear": "مقاومت"}'
    assert _raw_student_answer({"response": leaked}) == ""


# ═══════════════════════════════════════════════════════════════════════════
# ۲) انتخابِ MCQ و نگاشتِ اندیس
# ═══════════════════════════════════════════════════════════════════════════
OHM_OPTIONS = ["۰/۳۳", "۳", "۴۸", "۸"]


def test_explicit_selection_wins_over_text_in_explanation():
    """(الف) انتخابِ «۳ آمپر» با توضیحِ حاوی «۳» و «۴» باید گزینهٔ دوم بماند."""
    answer = "چون ۱۲ تقسیم بر ۴ می‌شود ۳، و ۴ هم عدد مقاومت است"
    assert _chosen_option(answer, OHM_OPTIONS, 1) == 1


def test_free_text_alone_never_derives_a_selection():
    """(ب) توضیحِ حاوی عدد، بدونِ اندیسِ صریح، هیچ انتخابی نمی‌سازد."""
    assert _chosen_option("جواب ۳ است", OHM_OPTIONS, None) is None
    assert _chosen_option("۳", OHM_OPTIONS, None) == 1  # فقط تطبیقِ دقیقِ متنِ گزینه


def test_selected_index_out_of_range_is_rejected():
    assert _chosen_option("", OHM_OPTIONS, 9) is None
    assert _chosen_option("", OHM_OPTIONS, -1) is None


def test_api_accepts_selected_option_index_and_ignores_it_for_text_questions():
    from api.routes_assessment import _selected_map

    class _Q:
        def __init__(self, qid, rubric):
            self.id = qid
            self.rubric = rubric

    class _A:
        def __init__(self, qid, idx):
            self.question_id = qid
            self.selected_option_index = idx

    questions = [
        _Q(1, {"exam_type": "philosophy", "options": None}),
        _Q(2, {"exam_type": "mask_mcq", "options": OHM_OPTIONS}),
    ]
    assert _selected_map(questions, [_A(1, 0), _A(2, 1)]) == {2: 1}


def test_key_must_match_the_actual_computation():
    """(د) کلید باید با ۱۲÷۴=۳ بخواند؛ هر چیزِ دیگر سؤال را رد می‌کند."""
    text = "در مداری با ولتاژ ۱۲ ولت و مقاومتِ ۴ اهم، جریان چند آمپر است؟"
    ok, _ = verify_mcq_key(text, OHM_OPTIONS, 1)
    assert ok is True

    for wrong_index in (0, 2, 3):
        ok, reason = verify_mcq_key(text, OHM_OPTIONS, wrong_index)
        assert ok is False and reason == "mcq_key_mismatch"


def test_duplicate_option_equals_key_is_rejected():
    text = "با ولتاژ ۱۲ ولت و مقاومت ۴ اهم، جریان چند آمپر است؟"
    ok, reason = verify_mcq_key(text, ["۳", "۳", "۴۸", "۸"], 0)
    assert ok is False and reason == "mcq_key_duplicated"


def test_key_mismatch_is_fatal_for_the_question():
    item = {
        "order": 2,
        "exam_type": "mask_mcq",
        "text": "با ولتاژ ۱۲ ولت و مقاومت ۴ اهم، جریان چند آمپر است؟",
        "options": OHM_OPTIONS,
        "correct_option_index": 3,
    }
    assert "mcq_key_mismatch" in question_quality_issues(item)


def test_verification_defers_when_no_arithmetic_is_present():
    """سؤالِ مفهومی محض (بدونِ محاسبهٔ عددی) نباید بی‌دلیل رد شود."""
    ok, _ = verify_mcq_key(
        "کدام گزاره دربارهٔ مقاومت درست است؟",
        ["ذاتی است", "به ولتاژ بستگی دارد", "با جریان زیاد می‌شود", "ثابت نیست"],
        0,
    )
    assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# ۳) حکمِ مسلط با شاهدِ معنایی
# ═══════════════════════════════════════════════════════════════════════════
def test_length_signals_are_gone_from_the_engine():
    from ai.cross_check import collect_signals

    signals = collect_signals(
        [{"order": 2, "exam_type": "mask_mcq", "options": OHM_OPTIONS,
          "correct_option_index": 1}],
        {1: "نمی‌دانم", 2: "۳", 3: "جریان زیاد می‌شود", 4: "غلط است", 5: "شلنگ"},
    )
    for legacy in ("substantive", "any_substantive", "debugging_strong", "word_counts"):
        assert legacy not in signals


def test_long_wrong_answer_is_not_mastered():
    """پاسخِ بلند دربارهٔ بدفهمی نباید «مسلط» بگیرد."""
    per_q = [
        {"order": 1, "status": "partial"},
        {"order": 2, "status": "correct"},
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "partial"},
    ]
    status, note = derive_status("MASTERED", per_q, {"mcq_correct": True})
    assert status != "MASTERED"
    assert note


def test_mastered_requires_both_q3_and_q4_correct():
    ok = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct"},
    ]
    assert derive_status("PARTIAL_FRAGMENTED", ok, {})[0] == "MASTERED"

    only_q3 = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "partial"},
    ]
    assert derive_status("MASTERED", only_q3, {})[0] != "MASTERED"


def test_wrong_claim_in_q4_caps_at_partial_even_if_model_said_correct():
    """ادعای «جریان تغییر می‌کند تا مقاومت ثابت بماند» ⇒ حداکثر partial."""
    answers = {4: "امیر اشتباه می‌کند، چون جریان تغییر می‌کند تا مقاومت ثابت بماند."}
    per_q = [{"order": 3, "status": "correct"}, {"order": 4, "status": "correct"}]

    assert wrong_q4_claim(answers[4]) is not None
    assert apply_q4_claim_guard(per_q, answers) is True

    q4 = next(r for r in per_q if r["order"] == 4)
    assert canonical_stage_status(q4["status"]) == "HALF_CORRECT"
    # و در نتیجه، حکمِ نهایی مسلط نیست
    assert derive_status("MASTERED", per_q, {})[0] != "MASTERED"


def test_correct_q4_reasoning_is_not_downgraded():
    answers = {
        4: "مقاومت یک ویژگیِ ذاتیِ رساناست و با ولتاژ عوض نمی‌شود، پس جریان زیاد می‌شود."
    }
    per_q = [{"order": 3, "status": "correct"}, {"order": 4, "status": "correct"}]
    assert apply_q4_claim_guard(per_q, answers) is False
    assert canonical_stage_status(per_q[1]["status"]) == "CORRECT"


def test_short_correct_answer_is_still_correct():
    """طول نباید باعثِ تنزیل شود."""
    per_q = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct"},
    ]
    assert derive_status("PARTIAL_FRAGMENTED", per_q, {})[0] == "MASTERED"


def test_all_empty_answers_are_unstructured_not_mastered():
    per_q = [
        {"order": o, "status": "insufficient"} for o in (1, 3, 4, 5)
    ]
    assert derive_status("MASTERED", per_q, {})[0] == "UNSTRUCTURED"


def test_forbidden_words_cap_the_verdict():
    per_q = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct"},
    ]
    status, _ = derive_status(
        "MASTERED", per_q, {"jargon_violated": True, "forbidden_hits": ["مقاومت"]}
    )
    assert status == "JARGON_DEPENDENT"


# ═══════════════════════════════════════════════════════════════════════════
# ۴) سازگاریِ کارت‌ها و یافته‌ها
# ═══════════════════════════════════════════════════════════════════════════
def test_synergy_is_dropped_when_a_stage_is_wrong():
    per_q = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "wrong"},
    ]
    findings = [
        {"title": "هم‌افزایی", "type": "SYNERGY", "description": "..."},
        {"title": "بدفهمی", "type": "BLUFF_DETECTED", "description": "..."},
    ]
    kept = _filter_false_synergy(findings, per_q)
    assert [f["type"] for f in kept] == ["BLUFF_DETECTED"]


def test_synergy_survives_when_both_stages_are_correct():
    per_q = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct"},
    ]
    findings = [{"title": "هم‌افزایی", "type": "SYNERGY", "description": "..."}]
    assert _filter_false_synergy(findings, per_q) == findings


def test_verdict_title_and_summary_come_from_one_status():
    """نشان/عنوان/خلاصه از یک وضعیت مشتق می‌شوند."""
    from ai.cross_check import _STATUS_PERSONA

    per_q = [
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct"},
    ]
    status, note = derive_status("UNSTRUCTURED", per_q, {})
    assert status == "MASTERED"
    assert note is None
    assert _STATUS_PERSONA[status] == "مهندسی که ساعت را بست"


# ═══════════════════════════════════════════════════════════════════════════
# ۵) متنِ سؤال‌ها
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    ["هیچ نقشی", "برای گمراه", "بی‌تأثیر", "ناچیز و بی‌اثر"],
)
def test_distractor_must_not_be_labelled(phrase):
    assert leaked_phrases(f"در این مدار {phrase} دارد.") != []


def test_answer_leak_in_philosophy_is_flagged():
    assert leaked_phrases("مقاومت ویژگی ذاتی رساناست", philosophy=True) != []
    # همین جمله در مرحلهٔ عیب‌یابی، لو رفتنِ پاسخ نیست
    assert leaked_phrases("مقاومت ویژگی ذاتی رساناست", philosophy=False) == []


def test_fallback_bank_contains_no_leaky_phrases():
    from ai.stage_chain import _FALLBACK_STAGES

    for stage in _FALLBACK_STAGES:
        assert leaked_phrases(stage["text"], philosophy=(stage["order"] == 1)) == [], (
            f"مرحلهٔ {stage['order']} عبارتِ لو‌دهنده دارد"
        )


def test_emotional_suggestions_are_removed():
    cleaned = normalize_suggestions(
        [
            "یک نفس عمیق بکش و آرام باش",
            "با ولتاژ ثابت، جریان را برای سه مقاومت حساب کن و جدول بساز",
        ]
    )
    assert cleaned == ["با ولتاژ ثابت، جریان را برای سه مقاومت حساب کن و جدول بساز"]


# ═══════════════════════════════════════════════════════════════════════════
# ۶) ردیابیِ مدل، توکن و هزینه
# ═══════════════════════════════════════════════════════════════════════════
def test_timeout_comes_from_settings_not_hardcoded():
    from config import settings

    provider = ma.OpenRouterProvider(api_key="x", model_name="m")
    assert provider.timeout == float(settings.OPENROUTER_TIMEOUT_SECONDS)


def test_retries_are_capped_at_two():
    # PINNED_MODEL_MAX_ATTEMPTS = retries + 1
    import os

    retries = int(os.getenv("OPENROUTER_PINNED_MAX_ATTEMPTS", "2"))
    assert retries <= 2
    assert ma.PINNED_MODEL_MAX_ATTEMPTS == retries + 1


def test_usage_ledger_sums_costs_instead_of_overwriting():
    from ai.model_abstraction import record_usage, reset_usage_ledger, usage_summary

    reset_usage_ledger()
    record_usage({
        "task_type": "generate_test_booklet", "model": "deepseek/x",
        "total_tokens": 1000, "prompt_tokens": 800, "completion_tokens": 200,
        "cost_usd": 0.0015,
    })
    record_usage({
        "task_type": "analyze_exam", "model": "deepseek/x",
        "total_tokens": 500, "prompt_tokens": 400, "completion_tokens": 100,
        "cost_usd": 0.0025,
    })
    summary = usage_summary()
    assert summary["call_count"] == 2
    assert summary["total_cost_usd"] == pytest.approx(0.004)
    assert summary["total_tokens"] == 1500
    assert summary["prompt_tokens"] == 1200
    assert summary["completion_tokens"] == 300
    reset_usage_ledger()


def test_usage_entries_carry_model_task_time_and_tokens(monkeypatch):
    from ai.model_abstraction import (
        record_usage, reset_usage_ledger, usage_summary, _log_usage,
    )

    reset_usage_ledger()
    response = ma.AIResponse(
        text="x", model_name="deepseek/deepseek-v4.1-flash-1017",
        token_count=1200, cost_usd=0.003, attempts=2,
        prompt_tokens=1000, completion_tokens=200, failed_cost_usd=0.0001,
    )
    _log_usage("openrouter", response, "generate_test_booklet", success=True)

    summary = usage_summary()
    entry = summary["calls"][0]
    assert entry["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert entry["task_type"] == "generate_test_booklet"
    assert entry["prompt_tokens"] == 1000
    assert entry["completion_tokens"] == 200
    assert entry["timestamp"]
    # هزینهٔ تلاش‌های شکست‌خورده هم جمع می‌شود
    assert summary["total_cost_usd"] == pytest.approx(0.0031)
    reset_usage_ledger()


def test_no_hidden_fallback_to_a_free_model():
    calls: list[str] = []

    class _Provider(ma.OpenRouterProvider):
        def __init__(self):
            self.model_name = "deepseek/deepseek-v4.1-flash-1017"

        def _post_chat_completion(self, prompt, temperature, model):
            calls.append(model)
            raise ma.AIProviderError("500 upstream", retryable=True)

        def fetch_active_free_models(self, force_refresh=False):
            return ["free/a", "free/b"]

        def _model_supports_json(self, model):
            return False

        def _throttle(self):
            pass

    provider = _Provider()
    with pytest.raises(ma.AIProviderError):
        provider._generate_with_fallback(
            "p", "generate_test_booklet", 0.7, model_override="deepseek/deepseek-v4.1-flash-1017"
        )
    # هیچ مدلِ دیگری امتحان نشد
    assert set(calls) == {"deepseek/deepseek-v4.1-flash-1017"}
    assert "free/a" not in calls


# ═══════════════════════════════════════════════════════════════════════════
# ۷) سناریوی واقعیِ کاربر (سرتاسری، mock)
# ═══════════════════════════════════════════════════════════════════════════
OHM_ROWS = [
    {"order": 1, "exam_type": "philosophy", "stage_title": "مرحله ۱: فلسفه",
     "text": "چرا به مفهوم مقاومت نیاز شد؟", "options": [],
     "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "نسبت V به I در رسانای اهمی ثابت است"},
    {"order": 2, "exam_type": "mask_mcq", "stage_title": "مرحله ۲: تست",
     "text": "در مداری با ولتاژ ۱۲ ولت و مقاومت ۴ اهم، جریان چند آمپر است؟",
     "options": OHM_OPTIONS, "correct_option_index": 1, "forbidden_words": [],
     "expected_logic": "I = V/R = 3"},
    {"order": 3, "exam_type": "perturbation", "stage_title": "مرحله ۳: دستکاری",
     "text": "با ثابت بودن ولتاژ، کاهش مقاومت چه می‌کند؟", "options": [],
     "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "جریان بیشتر، توان بیشتر"},
    {"order": 4, "exam_type": "debugging", "stage_title": "مرحله ۴: عیب‌یابی",
     "text": "امیر می‌گوید مقاومت خودش را تنظیم می‌کند.", "options": [],
     "correct_option_index": None, "forbidden_words": [],
     "expected_logic": "مقاومت ویژگیِ ذاتی است"},
    {"order": 5, "exam_type": "feynman_synthesis", "stage_title": "مرحله ۵: فاینمن",
     "text": "برای بچهٔ ۱۰ ساله توضیح بده", "options": [],
     "correct_option_index": None,
     "forbidden_words": ["مقاومت", "ولتاژ", "جریان", "قانون"],
     "expected_logic": "تمثیل با نگاشت"},
]

REAL_ANSWERS = {
    1: "نمی‌دانم.",
    2: "توضیحِ من: ۱۲ تقسیم بر ۴ می‌شود ۳ و ۴ هم مقاومت است",  # ← حاوی ۳ و ۴
    3: "چون ولتاژ ثابت است، جریان بیشتر می‌شود و توان هم بیشتر.",
    4: "امیر اشتباه می‌کند، چون جریان تغییر می‌کند تا مقاومت ثابت بماند.",
    5: "مثل شلنگ باغبانی است؛ نوکش را تنگ کنی آب تندتر بیرون می‌آید.",
}


class _Resp:
    model_name = "deepseek/deepseek-v4.1-flash-1017"
    cost_usd = 0.0
    attempts = 1
    total_cost_usd = 0.002
    total_tokens = 900
    prompt_tokens = 800
    completion_tokens = 100

    def __init__(self, text: str) -> None:
        self.text = text


def _run(monkeypatch, payload, answers=None, selections=None):
    class _Router:
        async def generate(self, prompt, task_type, temperature=0.3):
            return _Resp(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    return asyncio.run(
        cross_check.analyze_stage_chain(
            "قانون اهم", OHM_ROWS, answers or REAL_ANSWERS, selected_indices=selections
        )
    )


MASTERED_PAYLOAD = {
    "mastery_status": "MASTERED",
    "persona_title": "مهندسی که ساعت را بست",
    "executive_summary": "همه چیز کامل است.",
    "cross_check_findings": [{"title": "هم‌افزایی", "type": "SYNERGY", "description": "s"}],
    "improvement_suggestions": ["تمرین بیشتر"],
    "per_question": [
        {"order": 1, "status": "insufficient"},
        {"order": 2, "status": "correct"},
        {"order": 3, "status": "correct"},
        {"order": 4, "status": "correct", "cognitive_verdict": "هسته را گفت"},
        {"order": 5, "status": "partial"},
    ],
}


def test_real_scenario_never_reaches_mastered(monkeypatch):
    """سناریوی واقعی: مدل MASTERED می‌دهد، ولی Q4 ادعای غلط دارد."""
    result = _run(monkeypatch, MASTERED_PAYLOAD, selections={2: 1})

    assert result["mastery_status"] != "MASTERED"
    assert "ساعت را بست" not in str(result["persona_title"])
    assert "همه چیز کامل" not in result["executive_summary"]

    q4 = next(q for q in result["per_question"] if q["order"] == 4)
    assert canonical_stage_status(q4["status"]) == "HALF_CORRECT"
    # SYNERGY کاذب حذف شده چون Q4 دیگر correct نیست
    assert not any(f["type"] == "SYNERGY" for f in result["cross_check_findings"])


def test_real_scenario_selection_is_read_from_index_not_explanation(monkeypatch):
    result = _run(monkeypatch, MASTERED_PAYLOAD, selections={2: 1})
    assert result["signals"]["chosen_option"] == 1
    assert result["signals"]["mcq_correct"] is True

    # همین پاسخ بدونِ اندیسِ صریح ⇒ انتخابی استخراج نمی‌شود
    no_idx = _run(monkeypatch, MASTERED_PAYLOAD, selections=None)
    assert no_idx["signals"]["chosen_option"] is None


def test_short_unknown_answer_gets_no_mastery(monkeypatch):
    """سؤال ۱ کوتاه/ندانستن ⇒ partial یا insufficient، نه تسلط."""
    answers = dict(REAL_ANSWERS)
    answers[1] = "نمی‌دانم"
    payload = json.loads(json.dumps(MASTERED_PAYLOAD))
    payload["per_question"][0] = {"order": 1, "status": "insufficient"}
    result = _run(monkeypatch, payload, answers=answers, selections={2: 1})
    q1 = next(q for q in result["per_question"] if q["order"] == 1)
    assert canonical_stage_status(q1["status"]) in ("INSUFFICIENT_EVIDENCE", "HALF_CORRECT")
    assert result["mastery_status"] != "MASTERED"


def test_usage_is_attached_to_the_result(monkeypatch):
    from ai.model_abstraction import reset_usage_ledger

    reset_usage_ledger()
    result = _run(monkeypatch, MASTERED_PAYLOAD, selections={2: 1})
    assert "ai_usage" in result
    assert isinstance(result["ai_usage"], dict)
