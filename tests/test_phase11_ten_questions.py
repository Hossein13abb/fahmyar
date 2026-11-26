"""فاز ۱۱ — آزمون ۱۰ سؤالی، بازپرسی، کالیبراسیون داوری و اقتصادِ توکن.

هر پنج بندِ درخواست این‌جا سنجیده می‌شود:
  ۱. ساختارِ ۱۰ سؤال (۲ سؤال در هر مرحله) با نگاشتِ درستِ order → stage
  ۲. مرحلهٔ «بازپرس / رفعِ ابهام» با فلگِ needs_interrogation
  ۳. کالیبراسیونِ برچسب‌ها (مسلط / فرمول‌محور / توهمِ دانایی)
  ۴. اقتصادِ توکن: یک Request، JSON سخت‌گیرانه، کش
  ۵. جمع‌بندی در سطحِ مرحله از ۱۰ سؤال

همهٔ تست‌ها mock هستند — هیچ فراخوانیِ واقعیِ مدل انجام نمی‌شود.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from ai.cross_check import (
    _answers_block,
    _normalize_per_question,
    _summary_from_stages,
    aggregate_stage_status,
    collapse_to_stages,
    collect_signals,
    derive_status,
)
from ai.booklet_cache import (
    booklet_cache_key,
    clear_cache,
    get_cached_booklet,
    put_cached_booklet,
)
from ai.stage_chain import (
    QUESTIONS_PER_STAGE,
    STAGE_ORDER,
    TOTAL_QUESTIONS,
    fallback_item_for_order,
    fallback_stages,
    items_to_questions,
    normalize_stage_items,
    orders_of_stage,
    stage_key,
    stage_of_order,
)


class FakeConcept:
    name = "قانون اهم"
    subject = "فیزیک"
    grade = "11"
    core_propositions = ["رابطهٔ ولتاژ، جریان و مقاومت"]
    common_misconceptions = ["مقاومت با ولتاژ عوض می‌شود"]


def _ten_rows() -> list[dict]:
    """ردیف‌های واقعیِ ده‌گانه — دو سؤال در هر مرحله."""
    rows = []
    for order in range(1, TOTAL_QUESTIONS + 1):
        exam_type = stage_key(order)
        row = {
            "order": order,
            "stage": stage_of_order(order),
            "stage_slot": (order - 1) % QUESTIONS_PER_STAGE + 1,
            "exam_type": exam_type,
            "stage_title": f"مرحله {stage_of_order(order)}",
            "text": f"سؤال شمارهٔ {order}",
            "options": [],
            "correct_option_index": None,
            "forbidden_words": [],
            "expected_logic": "منطقِ آزمون",
        }
        if exam_type == "mask_mcq":
            row["options"] = ["۰٫۳۳", "۳", "۱۶", "۴۸"]
            row["correct_option_index"] = 1
        if exam_type == "feynman_synthesis":
            row["forbidden_words"] = ["مقاومت", "ولتاژ"] if order == 9 else ["جریان", "اهم"]
        rows.append(row)
    return rows


def _answers_all(text: str = "پاسخِ کامل و درست") -> dict[int, str]:
    return {o: text for o in range(1, TOTAL_QUESTIONS + 1)}


# ═══════════════════════════════════════════════════════════════════════════
# بند ۱ — ساختارِ ۱۰ سؤال
# ═══════════════════════════════════════════════════════════════════════════
def test_total_is_ten_with_two_per_stage():
    assert TOTAL_QUESTIONS == 10
    assert QUESTIONS_PER_STAGE == 2
    assert len(STAGE_ORDER) * QUESTIONS_PER_STAGE == TOTAL_QUESTIONS


@pytest.mark.parametrize(
    "order,stage",
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3), (7, 4), (8, 4), (9, 5), (10, 5)],
)
def test_order_to_stage_mapping(order, stage):
    assert stage_of_order(order) == stage


def test_orders_of_each_stage():
    assert orders_of_stage(1) == (1, 2)
    assert orders_of_stage(3) == (5, 6)
    assert orders_of_stage(5) == (9, 10)


@pytest.mark.parametrize(
    "order,key",
    [
        (1, "philosophy"),
        (2, "philosophy"),
        (3, "mask_mcq"),
        (4, "mask_mcq"),
        (5, "perturbation"),
        (6, "perturbation"),
        (7, "debugging"),
        (8, "debugging"),
        (9, "feynman_synthesis"),
        (10, "feynman_synthesis"),
    ],
)
def test_exam_type_per_order(order, key):
    assert stage_key(order) == key


def test_fallback_covers_all_ten_orders():
    stages = fallback_stages(FakeConcept())
    assert len(stages) == 10
    assert [s["order"] for s in stages] == list(range(1, 11))
    # هر مرحله دقیقاً دو سؤال
    for stage in range(1, 6):
        assert len([s for s in stages if s["stage"] == stage]) == 2


def test_each_feynman_question_has_its_own_forbidden_list():
    """بندِ ۱: «لیست کلمات ممنوعه مستقل برای هر سؤال»."""
    stages = fallback_stages(FakeConcept())
    feynman = [s for s in stages if s["exam_type"] == "feynman_synthesis"]
    assert len(feynman) == 2
    assert feynman[0]["forbidden_words"] != feynman[1]["forbidden_words"]
    for item in feynman:
        assert 4 <= len(item["forbidden_words"]) <= 6


def test_both_mcq_questions_have_four_options_and_a_key():
    stages = fallback_stages(FakeConcept())
    mcqs = [s for s in stages if s["exam_type"] == "mask_mcq"]
    assert len(mcqs) == 2
    for mcq in mcqs:
        assert len(mcq["options"]) == 4
        assert 0 <= mcq["correct_option_index"] <= 3


def test_normalize_assigns_ten_slots_from_out_of_order_model_output():
    raw = [
        {"order": 10, "exam_type": "feynman_synthesis", "text": "دهم"},
        {"order": 1, "exam_type": "philosophy", "text": "اول"},
        {"order": 5, "exam_type": "perturbation", "text": "پنجم"},
    ]
    items = normalize_stage_items(raw)
    by_order = {i["order"]: i for i in items}
    assert by_order[1]["text"] == "اول"
    assert by_order[5]["text"] == "پنجم"
    assert by_order[10]["text"] == "دهم"
    assert by_order[10]["stage"] == 5


def test_normalize_never_lets_a_third_mcq_take_another_stage():
    raw = [
        {"exam_type": "mask_mcq", "text": "ت۱", "options": ["a", "b", "c", "d"], "correct_option_index": 0},
        {"exam_type": "mask_mcq", "text": "ت۲", "options": ["a", "b", "c", "d"], "correct_option_index": 1},
        {"exam_type": "mask_mcq", "text": "ت۳", "options": ["a", "b", "c", "d"], "correct_option_index": 2},
    ]
    items = normalize_stage_items(raw)
    mcqs = [i for i in items if i["exam_type"] == "mask_mcq"]
    assert [m["text"] for m in mcqs] == ["ت۱", "ت۲"]
    assert all(m["stage"] == 2 for m in mcqs)


def test_items_to_questions_yields_ten_rows_with_stage_metadata():
    stages = fallback_stages(FakeConcept())
    rows = items_to_questions(FakeConcept(), stages, "test-model", 0.0)
    assert len(rows) == 10
    assert [r.rubric["stage"] for r in rows] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert [r.rubric["stage_slot"] for r in rows] == [1, 2] * 5


# ═══════════════════════════════════════════════════════════════════════════
# بند ۲ — بازپرس / رفعِ ابهام
# ═══════════════════════════════════════════════════════════════════════════
class _Resp:
    def __init__(self, text):
        self.text = text
        self.model_name = "fake-model"
        self.total_cost_usd = 0.0
        self.total_tokens = 100
        self.prompt_tokens = 80
        self.completion_tokens = 20
        self.attempts = 1


def _run_analysis(monkeypatch, payload: dict, rows=None, answers=None):
    import ai.cross_check as cc

    class _Router:
        async def generate(self, *a, **k):
            return _Resp(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(cc, "get_router", lambda: _Router())
    return asyncio.run(
        cc.analyze_stage_chain(
            "قانون اهم",
            rows if rows is not None else _ten_rows(),
            answers if answers is not None else _answers_all(),
        )
    )


def test_needs_interrogation_flags_session(monkeypatch):
    payload = {
        "needs_interrogation": True,
        "interrogation": {
            "contradicting_questions": [3, 7],
            "mirror_prompt": "تو در سؤال ۳ گفتی X و در سؤال ۷ گفتی Y",
            "question": "کدام یک را واقعاً باور داری؟",
        },
        "mastery_status": "PARTIAL_FRAGMENTED",
        "per_question": [],
        "cross_check_findings": [],
        "improvement_suggestions": [],
    }
    result = _run_analysis(monkeypatch, payload)
    assert result["needs_interrogation"] is True
    assert result["interrogation"]["mirror_prompt"].startswith("تو در سؤال ۳")
    assert len(result["interrogation"]["contradicting_questions"]) == 2


def test_no_interrogation_when_no_contradiction(monkeypatch):
    payload = {
        "needs_interrogation": False,
        "mastery_status": "PARTIAL_FRAGMENTED",
        "per_question": [],
        "cross_check_findings": [],
        "improvement_suggestions": [],
    }
    result = _run_analysis(monkeypatch, payload)
    assert result["needs_interrogation"] is False
    assert result["interrogation"] is None


def test_interrogation_without_mirror_is_rejected(monkeypatch):
    """بازپرسی بدونِ متنِ آینه‌ای، دانش‌آموز را در بن‌بست می‌گذارد."""
    payload = {
        "needs_interrogation": True,
        "interrogation": {"contradicting_questions": [1], "mirror_prompt": ""},
        "mastery_status": "PARTIAL_FRAGMENTED",
        "per_question": [],
        "cross_check_findings": [],
        "improvement_suggestions": [],
    }
    result = _run_analysis(monkeypatch, payload)
    assert result["needs_interrogation"] is False


def test_backward_compatible_with_needs_clarification(monkeypatch):
    """کلیدِ قدیمی هم باید کار کند تا کلاینت‌های موجود نشکنند."""
    payload = {
        "needs_clarification": True,
        "clarification_data": {
            "contradicting_questions": [2, 8],
            "mirror_prompt": "دو حرفِ متناقض",
        },
        "mastery_status": "PARTIAL_FRAGMENTED",
        "per_question": [],
        "cross_check_findings": [],
        "improvement_suggestions": [],
    }
    result = _run_analysis(monkeypatch, payload)
    assert result["needs_interrogation"] is True
    assert result["interrogation"]["mirror_prompt"] == "دو حرفِ متناقض"


# ═══════════════════════════════════════════════════════════════════════════
# بند ۳ — کالیبراسیونِ داوری
# ═══════════════════════════════════════════════════════════════════════════
def _stages(statuses: dict[int, str]) -> list[dict]:
    return [{"order": o, "status": s} for o, s in sorted(statuses.items())]


def test_mastered_requires_stage3_and_stage4_and_stage5():
    base = {1: "CORRECT", 2: "CORRECT", 3: "CORRECT", 4: "CORRECT", 5: "CORRECT"}
    assert derive_status("X", _stages(base), {})[0] == "MASTERED"

    for missing in (3, 4, 5):
        broken = dict(base)
        broken[missing] = "HALF_CORRECT"
        assert derive_status("MASTERED", _stages(broken), {})[0] != "MASTERED", (
            f"مرحلهٔ {missing} نباید با تسلط جمع شود"
        )


def test_formula_heavy_but_understanding_is_yellow_not_red():
    """بندِ ۳: نقدِ فرمول‌محور با فهمِ درست ⇒ نه «توهمِ دانایی»، نه قرمز."""
    stages = _stages({
        1: "CORRECT", 2: "CORRECT",
        3: "CORRECT",              # زنجیرهٔ علّی درست
        4: "HALF_CORRECT",         # در نقد به فرمول تکیه کرده
        5: "HALF_CORRECT",         # بیانِ ساده ضعیف
    })
    status, note = derive_status("MASTERED", stages, {"mcq_correct": True})
    assert status == "PARTIAL_FRAGMENTED"
    assert status != "ILLUSION_OF_COMPETENCE"
    assert note and ("فرمول" in note or "بیان" in note)


def test_illusion_of_competence_is_strict():
    """فقط وقتی: تست‌ها درست + مرحلهٔ ۳ و ۴ استدلالِ غلط."""
    stages = _stages({
        1: "HALF_CORRECT", 2: "CORRECT",
        3: "WRONG", 4: "WRONG", 5: "WRONG",
    })
    status, _ = derive_status("PARTIAL_FRAGMENTED", stages, {"mcq_correct": True})
    assert status == "ILLUSION_OF_COMPETENCE"


def test_illusion_not_awarded_when_mcq_failed():
    """اگر خودِ تست غلط باشد، مهارتِ فرمولی هم نیست ⇒ توهمِ دانایی ممنوع."""
    stages = _stages({
        1: "HALF_CORRECT", 2: "WRONG",
        3: "WRONG", 4: "WRONG", 5: "WRONG",
    })
    status, _ = derive_status("ILLUSION_OF_COMPETENCE", stages, {"mcq_correct": False})
    assert status != "ILLUSION_OF_COMPETENCE"


def test_illusion_title_does_not_claim_a_trap_without_contradiction(monkeypatch):
    """بندِ ۳: تیتر نباید «تلهٔ فرمول» بزند وقتی تناقضی ثبت نشده."""
    import ai.cross_check as cc

    payload = {
        "mastery_status": "PARTIAL_FRAGMENTED",
        "persona_title": "شکارشده در تلهٔ فرمول و شهود",
        "executive_summary": "خلاصه",
        "per_question": [],
        "cross_check_findings": [],       # هیچ تناقضی
        "improvement_suggestions": [],
    }
    result = _run_analysis(monkeypatch, payload)
    assert "تله" not in result["persona_title"]


# ═══════════════════════════════════════════════════════════════════════════
# بند ۴ — اقتصادِ توکن: یک Request + کش
# ═══════════════════════════════════════════════════════════════════════════
def test_generation_is_a_single_request(monkeypatch):
    """شناسنامه و هر ده سؤال در یک فراخوانی — نه ده فراخوانی."""
    import ai.stage_chain as sc

    calls = {"n": 0}
    questions = [
        {
            "order": o,
            "exam_type": stage_key(o),
            "text": f"سؤال {o}",
            "options": ["a", "b", "c", "d"] if stage_key(o) == "mask_mcq" else None,
            "correct_option_index": 1 if stage_key(o) == "mask_mcq" else None,
            "forbidden_words": ["x", "y", "z", "w"] if stage_key(o) == "feynman_synthesis" else [],
            "expected_logic": "منطق",
        }
        for o in range(1, 11)
    ]
    payload = {
        "concept_blueprint": {"core_mechanism": "م", "target_misconceptions": ["ب"]},
        "questions": questions,
    }

    class _Router:
        async def generate(self, *a, **k):
            calls["n"] += 1
            return _Resp(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(sc, "get_router", lambda: _Router())
    monkeypatch.setenv("FAHMYAR_BOOKLET_CACHE", "0")
    clear_cache()

    rows, model, cost = asyncio.run(sc.generate_stage_chain(FakeConcept()))
    assert calls["n"] == 1, "تولید باید در یک Request انجام شود"
    assert len(rows) == 10


def test_booklet_cache_prevents_second_model_call(monkeypatch, tmp_path):
    import ai.stage_chain as sc

    monkeypatch.setenv("FAHMYAR_BOOKLET_CACHE", "1")
    monkeypatch.setenv("FAHMYAR_BOOKLET_CACHE_PATH", str(tmp_path / "b.json"))
    clear_cache()

    calls = {"n": 0}
    questions = [
        {
            "order": o,
            "exam_type": stage_key(o),
            "text": f"سؤال {o}",
            "options": ["a", "b", "c", "d"] if stage_key(o) == "mask_mcq" else None,
            "correct_option_index": 1 if stage_key(o) == "mask_mcq" else None,
            "forbidden_words": ["x", "y", "z", "w"] if stage_key(o) == "feynman_synthesis" else [],
            "expected_logic": "منطق",
        }
        for o in range(1, 11)
    ]

    class _Router:
        async def generate(self, *a, **k):
            calls["n"] += 1
            return _Resp(json.dumps({"questions": questions}, ensure_ascii=False))

    monkeypatch.setattr(sc, "get_router", lambda: _Router())

    asyncio.run(sc.generate_stage_chain(FakeConcept()))
    assert calls["n"] == 1
    asyncio.run(sc.generate_stage_chain(FakeConcept()))
    assert calls["n"] == 1, "تولیدِ دوم باید از کش بیاید، نه از مدل"
    clear_cache()


def test_cache_key_is_content_based_not_row_id():
    class A:
        name = "قانون اهم"
        subject = "فیزیک"
        grade = "11"
        core_propositions = []
        common_misconceptions = []

    class B(A):
        pass

    # دو مفهومِ هم‌محتوا ⇒ همان کلید (حتی اگر شناسهٔ دیتابیس متفاوت باشد)
    assert booklet_cache_key(A()) == booklet_cache_key(B())

    class C(A):
        grade = "12"

    assert booklet_cache_key(A()) != booklet_cache_key(C())


def test_cached_booklets_are_isolated_copies():
    """مصرف‌کننده نباید بتواند کشِ مشترک را تغییر دهد."""
    clear_cache()
    put_cached_booklet("k", [{"order": 1, "text": "اصل"}], "m", 0.0)
    got = get_cached_booklet("k")
    got[0][0]["text"] = "تغییر"
    again = get_cached_booklet("k")
    assert again[0][0]["text"] == "اصل"
    clear_cache()


# ═══════════════════════════════════════════════════════════════════════════
# بند ۵ — جمع‌بندی در سطحِ مرحله
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "pair,expected",
    [
        (("CORRECT", "CORRECT"), "CORRECT"),
        (("CORRECT", "HALF_CORRECT"), "HALF_CORRECT"),
        (("CORRECT", "WRONG"), "HALF_CORRECT"),
        (("CORRECT", "INSUFFICIENT_EVIDENCE"), "HALF_CORRECT"),
        (("HALF_CORRECT", "HALF_CORRECT"), "HALF_CORRECT"),
        (("HALF_CORRECT", "WRONG"), "WRONG"),
        (("WRONG", "WRONG"), "WRONG"),
        (("WRONG", "INSUFFICIENT_EVIDENCE"), "HALF_CORRECT"),
        (("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE"), "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_stage_aggregation_rules(pair, expected):
    assert aggregate_stage_status(list(pair)) == expected


def test_collapse_groups_ten_questions_into_five_stages():
    per_q = [
        {"order": o, "stage": stage_of_order(o), "status": "CORRECT"}
        for o in range(1, 11)
    ]
    # یک سؤالِ نادرست در مرحلهٔ ۳
    per_q[4]["status"] = "WRONG"
    stages = collapse_to_stages(per_q)
    assert len(stages) == 5
    assert [s["order"] for s in stages] == [1, 2, 3, 4, 5]
    assert stages[2]["status"] == "HALF_CORRECT"
    assert stages[2]["orders"] == [5, 6]
    assert stages[2]["question_count"] == 2


def test_consistent_pair_is_not_downgraded():
    """اگر هر دو سؤالِ یک مرحله درست باشند، مرحله درست می‌ماند."""
    per_q = [
        {"order": o, "stage": stage_of_order(o), "status": "CORRECT"}
        for o in range(1, 11)
    ]
    assert all(s["status"] == "CORRECT" for s in collapse_to_stages(per_q))


def test_summary_counts_stages_not_questions():
    """خلاصه باید از پنج مرحله حرف بزند، نه از ده سؤال."""
    per_q = [
        {"order": o, "stage": stage_of_order(o), "status": "CORRECT"}
        for o in range(1, 11)
    ]
    for o in (5, 6):   # مرحلهٔ ۳ نادرست
        per_q[o - 1]["status"] = "WRONG"
    summary = _summary_from_stages(per_q, "PARTIAL_FRAGMENTED")
    assert "سؤال" not in summary
    assert "مرحله" in summary


def test_all_ten_questions_answered_means_no_blanks():
    signals = collect_signals(_ten_rows(), _answers_all(), "قانون اهم", {3: 1, 4: 1})
    assert len(signals["answered_orders"]) == 10
    assert signals["total_questions"] == 10


def test_mcq_signals_track_both_questions():
    """مرحلهٔ ۲ دو تست دارد؛ «mcq_correct» فقط با درستیِ هر دو درست است."""
    rows = _ten_rows()
    answers = _answers_all()
    both_right = collect_signals(rows, answers, "قانون اهم", {3: 1, 4: 1})
    assert both_right["mcq_correct"] is True
    assert both_right["mcq_results"] == {"3": True, "4": True}

    one_right = collect_signals(rows, answers, "قانون اهم", {3: 1, 4: 0})
    assert one_right["mcq_correct"] is False
    assert one_right["mcq_any_correct"] is True


def test_forbidden_words_are_scoped_to_their_own_question():
    """کلمهٔ ممنوعهٔ سؤال ۹ نباید در پاسخِ سؤال ۱ تخلف شمرده شود."""
    rows = _ten_rows()
    answers = _answers_all()
    answers[1] = "مقاومت و ولتاژ را می‌شناسم"    # کلمهٔ ممنوعهٔ سؤال ۹، نه این‌جا
    answers[9] = "مثل شلنگِ آب است"               # پاسخِ تمیزِ سؤال ۹
    signals = collect_signals(rows, answers, "قانون اهم", {3: 1, 4: 1})
    assert signals["jargon_violated"] is False

    answers[9] = "مقاومت این‌جا نقش دارد"          # حالا واقعاً در سؤالِ خودش
    signals = collect_signals(rows, answers, "قانون اهم", {3: 1, 4: 1})
    assert signals["jargon_violated"] is True


def test_answers_block_covers_all_ten_and_never_blanks_an_mcq():
    block = _answers_block(_ten_rows(), _answers_all(), {3: 1, 4: 2})
    for order in range(1, 11):
        assert f"<<<STAGE {order}>>>" in block
    stage3 = block.split("<<<STAGE 3>>>")[1].split("<<<STAGE 4>>>")[0]
    stage4 = block.split("<<<STAGE 4>>>")[1].split("<<<STAGE 5>>>")[0]
    assert "بدون پاسخ" not in stage3
    assert "بدون پاسخ" not in stage4
    assert "گزینه [2]" in stage3
    assert "گزینه [3]" in stage4


def test_normalize_per_question_returns_all_ten():
    rows = _ten_rows()
    data = {"per_question": [{"order": o, "status": "CORRECT"} for o in range(1, 11)]}
    records = _normalize_per_question(data, rows, _answers_all(), {3: 1, 4: 1})
    assert len(records) == 10
    assert [r["order"] for r in records] == list(range(1, 11))


def test_both_mcq_records_are_decided_by_key_not_by_model():
    rows = _ten_rows()
    # مدل می‌گوید هر دو بی‌پاسخ؛ کلید می‌گوید یکی درست و یکی غلط
    data = {
        "per_question": [
            {"order": o, "status": "INSUFFICIENT_EVIDENCE"} for o in range(1, 11)
        ]
    }
    records = _normalize_per_question(data, rows, _answers_all(), {3: 1, 4: 0})
    by_order = {r["order"]: r for r in records}
    assert by_order[3]["status"] == "CORRECT"
    assert by_order[4]["status"] == "WRONG"
