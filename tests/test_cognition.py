# -*- coding: utf-8 -*-
"""آزمون‌های موتور فهم‌سنجی شناختی.

این تست‌ها روی *قواعد* تمرکز دارند، نه روی مدل: هر قانونِ شناختی باید
قطعاً و بدونِ شبکه قابلِ بازتولید باشد. اگر روزی مدل عوض شود، این‌ها
باید سبز بمانند — چون قانون در کد است، نه در پرامپت.
"""
from __future__ import annotations

import json

import pytest

from cognition.contract import (
    QUESTION_TYPES,
    ContractError,
    normalize_evaluation,
    normalize_generation,
)
from cognition.personas import status_label
from cognition.rules import (
    apply_jargon_flag,
    apply_supremacy_override,
    dedupe_findings,
    detect_jargon_violation,
    find_forbidden_words,
    rule_summary,
)


# ---------------------------------------------------------------------------
# قرارداد
# ---------------------------------------------------------------------------
def _raw_generation() -> dict:
    return {
        "topic_blueprint": {"core_mechanism": "m", "target_misconceptions": ["x"]},
        "questions": [
            {"id": 1, "type": "philosophy", "question_text": "q1", "forbidden_words": []},
            {
                "id": 2,
                "type": "mask_mcq",
                "question_text": "q2",
                "options": ["a", "b", "c", "d"],
                "correct_option_index": 2,
            },
            {"id": 3, "type": "perturbation", "question_text": "q3"},
            {"id": 4, "type": "debugging", "question_text": "q4"},
            {
                "id": 5,
                "type": "feynman_synthesis",
                "question_text": "q5",
                "forbidden_words": ["شیب", "حد", "مشتق"],
            },
        ],
    }


def test_generation_normalizes_to_five_ordered_questions():
    result = normalize_generation(_raw_generation())
    assert [q["type"] for q in result.questions] == list(QUESTION_TYPES)
    assert [q["id"] for q in result.questions] == [1, 2, 3, 4, 5]


def test_generation_reorders_shuffled_questions():
    """مدل ممکن است سؤال‌ها را بی‌ترتیب بدهد؛ ترتیبِ شناختی باید حفظ شود."""
    payload = _raw_generation()
    payload["questions"] = [payload["questions"][i] for i in (4, 0, 3, 1, 2)]
    result = normalize_generation(payload)
    assert [q["type"] for q in result.questions] == list(QUESTION_TYPES)


def test_generation_rejects_missing_question():
    payload = _raw_generation()
    payload["questions"] = payload["questions"][:3]
    with pytest.raises(ContractError):
        normalize_generation(payload)


def test_generation_fills_missing_forbidden_words():
    """اگر مدل کلماتِ ممنوعه ندهد، چالشِ فاینمن نباید حذف شود."""
    payload = _raw_generation()
    payload["questions"][4]["forbidden_words"] = []
    result = normalize_generation(payload)
    assert len(result.questions[4]["forbidden_words"]) >= 3


def test_generation_normalizes_string_option_index():
    payload = _raw_generation()
    payload["questions"][1]["correct_option_index"] = "2"
    result = normalize_generation(payload)
    assert result.questions[1]["correct_option_index"] == 2


def test_evaluation_cancels_clarification_without_mirror_text():
    """بازپرسیِ بی‌متن کاربر را در بن‌بست می‌گذارد؛ باید لغو شود."""
    report = normalize_evaluation(
        {
            "needs_clarification": True,
            "clarification_data": {"contradicting_questions": [1, 2], "mirror_prompt": ""},
            "evaluation_report": {"mastery_status": "MASTERED"},
        }
    )
    assert report.needs_clarification is False


def test_evaluation_accepts_clarification_with_mirror_text():
    report = normalize_evaluation(
        {
            "needs_clarification": True,
            "clarification_data": {"contradicting_questions": [1, 2], "mirror_prompt": "کدام درست است؟"},
            "evaluation_report": {"mastery_status": "MASTERED"},
        }
    )
    assert report.needs_clarification is True
    assert report.clarification.mirror_prompt == "کدام درست است؟"


def test_evaluation_falls_back_on_unknown_status():
    report = normalize_evaluation(
        {"evaluation_report": {"mastery_status": "SOMETHING_ELSE"}}
    )
    assert report.mastery_status == "PARTIAL_FRAGMENTED"


# ---------------------------------------------------------------------------
# قانون ۳ — کلماتِ ممنوعه
# ---------------------------------------------------------------------------
def test_forbidden_word_detected_with_arabic_yeh():
    """شکلِ عربیِ «ي» و «ك» نباید تشخیص را دور بزند."""
    assert find_forbidden_words("شيب خط را حساب کردم", ["شیب"]) == ["شیب"]


def test_forbidden_word_respects_word_boundaries():
    """«حد» نباید داخلِ «حدس» شمرده شود."""
    assert find_forbidden_words("حدس زدم", ["حد"]) == []
    assert find_forbidden_words("حد را گرفتم", ["حد"]) == ["حد"]


def test_jargon_violation_reports_hits():
    questions = [{"id": 5, "forbidden_words": ["فشار", "چگالی"]}]
    result = detect_jargon_violation({5: "چون چگالی آب زیاد است"}, questions)
    assert result["violated"] is True
    assert result["hits"] == ["چگالی"]


def test_jargon_clean_answer_is_not_flagged():
    questions = [{"id": 5, "forbidden_words": ["فشار", "چگالی"]}]
    result = detect_jargon_violation({5: "چون آبِ بالای سر سنگین است"}, questions)
    assert result["violated"] is False


# ---------------------------------------------------------------------------
# قانون ۲ — حاکمیتِ عیب‌یابی
# ---------------------------------------------------------------------------
def test_supremacy_override_upgrades_unstructured():
    report = {"evaluation_report": {"mastery_status": "UNSTRUCTURED", "cross_check_findings": []}}
    signals = {"debugging_supremacy": {"strong": True}}
    out = apply_supremacy_override(report, signals)
    assert out["evaluation_report"]["mastery_status"] == "MASTERED"
    assert len(out["evaluation_report"]["cross_check_findings"]) == 1


def test_supremacy_does_not_duplicate_existing_finding():
    report = {
        "evaluation_report": {
            "mastery_status": "PARTIAL_FRAGMENTED",
            "cross_check_findings": [
                {"title": "عیب‌یابیِ درست، بیانِ کم‌حوصله", "type": "SYNERGY", "description": "d"}
            ],
        }
    }
    out = apply_supremacy_override(report, {"debugging_supremacy": {"strong": True}})
    titles = [f["title"] for f in out["evaluation_report"]["cross_check_findings"]]
    assert len(titles) == 1


def test_supremacy_leaves_strong_status_untouched():
    report = {"evaluation_report": {"mastery_status": "MASTERED", "cross_check_findings": []}}
    out = apply_supremacy_override(report, {"debugging_supremacy": {"strong": True}})
    assert out["evaluation_report"]["mastery_status"] == "MASTERED"
    assert out["evaluation_report"]["cross_check_findings"] == []


# ---------------------------------------------------------------------------
# قانون ۴ — بی‌دقتی
# ---------------------------------------------------------------------------
def _questions() -> list[dict]:
    return [
        {"id": 1, "type": "philosophy"},
        {"id": 2, "type": "mask_mcq", "options": ["a", "b", "c", "d"], "correct_option_index": 1},
        {"id": 3, "type": "perturbation"},
        {"id": 4, "type": "debugging"},
        {"id": 5, "type": "feynman_synthesis", "forbidden_words": []},
    ]


def test_mcq_answer_by_option_text_is_unambiguous():
    """قرارداد: فرانت‌اند متنِ کاملِ گزینه را می‌فرستد.

    چرا متن و نه شماره؟ چون «۲» هم می‌تواند گزینهٔ دوم باشد و هم گزینهٔ سوم
    (بسته به صفرپایه یا یک‌پایه بودن) و همین ابهام یک بار آزمونِ درست را
    «نادرست» شمرد.
    """
    questions = _questions()
    questions[1]["options"] = ["الف", "ب", "ج", "د"]
    signals = rule_summary({2: "ب"}, questions)
    assert signals["mask_vs_intuition"]["chosen_option"] == 1
    assert signals["mask_vs_intuition"]["mcq_correct"] is True


def test_mcq_numeric_answer_is_one_based():
    """عددِ خالی یک‌پایه تفسیر می‌شود (UI از ۱ تا ۴ شماره می‌زند)."""
    signals = rule_summary({2: "2"}, _questions())
    assert signals["mask_vs_intuition"]["chosen_option"] == 1


def test_rich_answers_are_detected_as_substantive():
    answers = {
        1: "چون نیرو بدونِ سطح معنا ندارد و می‌خواهیم دو وضعیت را مقایسه کنیم",
        3: "شکل ظرف عوض می‌شود پس عمق زیاد می‌شود و فشار بیشتر می‌شود",
        4: "امیر وزن کل آب را با وزن ستون بالای واحد سطح قاطی کرده است",
    }
    signals = rule_summary(answers, _questions())
    assert signals["slip_candidate"]["any_substantive"] is True


def test_short_answers_are_not_substantive():
    signals = rule_summary({1: "نمی‌دانم"}, _questions())
    assert signals["slip_candidate"]["any_substantive"] is False


# ---------------------------------------------------------------------------
# dedupe و برچسب‌ها
# ---------------------------------------------------------------------------
def test_dedupe_removes_identical_findings():
    report = {
        "evaluation_report": {
            "cross_check_findings": [
                {"title": "الف", "type": "SYNERGY", "description": "1"},
                {"title": "الف", "type": "SYNERGY", "description": "2"},
                {"title": "ب", "type": "CONTRADICTION", "description": "3"},
            ]
        }
    }
    out = dedupe_findings(report)
    assert len(out["evaluation_report"]["cross_check_findings"]) == 2


def test_jargon_flag_is_always_surfaced():
    report = {"evaluation_report": {"cross_check_findings": []}}
    signals = {"jargon": {"violated": True, "hits": ["شیب"]}}
    out = apply_jargon_flag(report, signals)
    types = [f["type"] for f in out["evaluation_report"]["cross_check_findings"]]
    assert "JARGON_VIOLATION" in types


def test_status_labels_are_persian():
    for status in ("MASTERED", "JARGON_DEPENDENT", "ILLUSION_OF_COMPETENCE"):
        label = status_label(status)
        assert label and not label.isascii()
