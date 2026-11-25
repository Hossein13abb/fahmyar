"""آزمون‌های موتور فهم‌سنجی ۵ مرحله‌ای (فاز ۷).

پوشش:
  * `ai.prompt_safe` — جای‌گذاریِ امن و عدمِ تفسیرِ آکولادهای LaTeX
  * گاردِ «هیچ `.format()` روی پرامپت» برای ماژول‌های `ai/`
  * نرمال‌سازیِ خروجیِ مدل به پنج مرحلهٔ قطعی
  * قالبِ اضطراری: پنج سؤالِ کامل با ۴ گزینه و کلماتِ ممنوعه
  * تحلیلِ مقایسه‌ای: تضاد، نقضِ کلماتِ ممنوعه، حاکمیتِ عیب‌یابی، بازپرسی
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ai.prompt_safe import TemplateError, fill, assert_no_format_calls
from ai.stage_chain import (
    STAGE_ORDER,
    fallback_stages,
    normalize_stage_items,
    items_to_questions,
)
import ai.cross_check as cross_check


AI_DIR = Path(__file__).resolve().parent.parent / "ai"


class FakeConcept:
    id = 7
    name = "فشار در مایعات"
    subject = "علوم"
    grade = "هشتم"
    core_propositions = [
        "فشار در عمق معین به ارتفاع ستون مایع بستگی دارد و به شکل ظرف نه",
        "فشار برابر نیرو بر مساحت است",
    ]
    common_misconceptions = ["هر چه حجم مایع بیشتر باشد، فشار بیشتر است"]


# ───────────────────────── prompt_safe ─────────────────────────
def test_fill_keeps_latex_braces_intact():
    template = r"بیشینه در $\cos^{-1}(x)$ و $\frac{4}{9}$ و $\begin{bmatrix}1\\0\end{bmatrix}$ و $\vec{n}$"
    out = fill(template, unused="x")
    for fragment in (r"\cos^{-1}", r"\frac{4}{9}", r"\begin{bmatrix}", r"\vec{n}"):
        assert fragment in out


def test_fill_replaces_real_placeholders():
    assert fill("مفهوم {concept} برای پایهٔ {grade}", concept="فشار", grade="هشتم") == (
        "مفهوم فشار برای پایهٔ هشتم"
    )


def test_fill_raises_on_unfilled_placeholder():
    with pytest.raises(TemplateError):
        fill("سلام {grade} عزیز", concept="فشار")


def test_format_on_latex_prompt_would_have_exploded():
    """بازتولیدِ باگِ اصلی: `.format` روی همین متن KeyError('-1') می‌دهد."""
    template = r"زاویهٔ $\cos^{-1}(x)$ را حساب کن"
    with pytest.raises(KeyError):
        template.format(concept="x")
    assert "cos^{-1}" in fill(template, concept="x")


def test_no_format_calls_in_ai_package():
    """گاردِ رگرسیون: اگر روزی کسی دوباره `.format()` بنویسد، تست قرمز شود."""
    offenders = []
    for path in sorted(AI_DIR.glob("*.py")):
        if path.name == "prompt_safe.py":  # خودِ گارد مستثناست
            continue
        try:
            assert_no_format_calls(path.read_text(encoding="utf-8"), path.name)
        except AssertionError as exc:  # noqa: PERF203
            offenders.append(str(exc))
    assert not offenders, "\n".join(offenders)


# ───────────────────────── stage_chain ─────────────────────────
def test_normalize_orders_stages_and_one_based_index():
    raw = [
        {"exam_type": "feynman_synthesis", "text": "توضیح بده",
         "forbidden_words": "فشار، چگالی، ارتفاع، فرمول"},
        {"exam_type": "mask_mcq", "text": "کدام؟",
         "options": ["الف", "ب", "ج", "د"], "correct_option_index": "2"},
        {"exam_type": "philosophy", "text": "چرا؟"},
    ]
    items = normalize_stage_items(raw)
    assert [i["exam_type"] for i in items] == ["philosophy", "mask_mcq", "feynman_synthesis"]
    mcq = next(i for i in items if i["exam_type"] == "mask_mcq")
    # پرامپت یک‌پایه است: «۲» یعنی گزینهٔ دوم ⇒ اندیسِ صفر‌پایهٔ ۱
    assert mcq["correct_option_index"] == 1
    assert len(mcq["options"]) == 4
    feynman = next(i for i in items if i["exam_type"] == "feynman_synthesis")
    assert "فشار" in feynman["forbidden_words"]
    assert len(feynman["forbidden_words"]) >= 3


def test_normalize_drops_duplicate_stage_instead_of_mislabeling():
    raw = [
        {"exam_type": "mask_mcq", "text": "اول", "options": ["a", "b", "c", "d"], "correct_option_index": 1},
        {"exam_type": "mask_mcq", "text": "دوم", "options": ["a", "b", "c", "d"], "correct_option_index": 2},
        {"exam_type": "philosophy", "text": "چرا؟"},
    ]
    items = normalize_stage_items(raw)
    texts = {i["exam_type"]: i["text"] for i in items}
    assert texts["mask_mcq"] == "اول"
    assert "perturbation" not in texts


def test_fallback_has_all_five_complete_stages():
    stages = fallback_stages(FakeConcept())
    assert [s["exam_type"] for s in stages] == list(STAGE_ORDER)
    mcq = next(s for s in stages if s["exam_type"] == "mask_mcq")
    assert len(mcq["options"]) == 4
    assert mcq["correct_option_index"] is not None
    feynman = next(s for s in stages if s["exam_type"] == "feynman_synthesis")
    assert 4 <= len(feynman["forbidden_words"]) <= 6
    for stage in stages:
        assert len(stage["text"]) > 60
        assert stage["stage_title"]


def test_items_to_questions_puts_secrets_in_rubric_only():
    stages = fallback_stages(FakeConcept())
    rows = items_to_questions(FakeConcept(), stages, "test-model", 0.0)
    assert len(rows) == 5
    for row in rows:
        assert row.question_type in STAGE_ORDER
        assert row.rubric["stage_title"]
        assert "exam_type" in row.rubric
    mcq = next(r for r in rows if r.question_type == "mask_mcq")
    assert mcq.rubric["correct_option_index"] is not None
    assert mcq.rubric["options"] and len(mcq.rubric["options"]) == 4


# ───────────────────────── cross_check ─────────────────────────
ROWS = [
    {"question_id": 1, "order": 1, "exam_type": "philosophy", "stage_title": "مرحله ۱",
     "text": "چرا فشار زیر آب بیشتر است؟", "options": [], "correct_option_index": None,
     "forbidden_words": [], "expected_logic": "وزنِ ستونِ مایع"},
    {"question_id": 2, "order": 2, "exam_type": "mask_mcq", "stage_title": "مرحله ۲",
     "text": "کدام درست است؟",
     "options": ["در همهٔ عمق‌ها یکسان", "با حجم زیاد می‌شود", "با ارتفاع زیاد می‌شود", "ثابت است"],
     "correct_option_index": 2, "forbidden_words": [], "expected_logic": "ارتفاع"},
    {"question_id": 3, "order": 3, "exam_type": "perturbation", "stage_title": "مرحله ۳",
     "text": "روی ماه چه می‌شود؟", "options": [], "correct_option_index": None,
     "forbidden_words": [], "expected_logic": "کاهشِ شتابِ گرانش"},
    {"question_id": 4, "order": 4, "exam_type": "debugging", "stage_title": "مرحله ۴",
     "text": "سارا می‌گوید حجم مهم است", "options": [], "correct_option_index": None,
     "forbidden_words": [], "expected_logic": "استدلال غلط است"},
    {"question_id": 5, "order": 5, "exam_type": "feynman_synthesis", "stage_title": "مرحله ۵",
     "text": "برای بچهٔ ۱۰ ساله توضیح بده", "options": [], "correct_option_index": None,
     "forbidden_words": ["فشار", "چگالی", "ارتفاع", "جاذبه"], "expected_logic": "وزنِ ستون"},
]

ANSWERS = {
    1: "چون آب سنگین است و وزنش روی ما می‌ماند؛ هرچه پایین‌تر برویم بیشتر حس می‌شود.",
    2: "با ارتفاع زیاد می‌شود",
    3: "چون شتاب گرانش کمتر است، وزن ستون کمتر می‌شود پس فشار در همان عمق کمتر است.",
    4: "سارا اشتباه می‌کند چون حجم اثری ندارد؛ فقط ارتفاع ستون مادهٔ روی سر مهم است.",
    5: "وقتی می‌ری زیر آب، چگالی و ارتفاع باعث می‌شوند فشار زیاد شود چون آب روی شما وزن دارد.",
}


class _Resp:
    model_name = "fake-model"
    cost_usd = 0.0

    def __init__(self, text: str) -> None:
        self.text = text


def _router_returning(payload):
    class _Router:
        async def generate(self, prompt, task_type, temperature=0.3):
            _Router.last_prompt = prompt
            return _Resp(json.dumps(payload, ensure_ascii=False))

    return _Router


def _analyze_with(monkeypatch, answers, payload=None, raises=None):
    if raises is not None:
        class _Router:
            async def generate(self, *a, **k):
                raise RuntimeError(raises)
    else:
        _Router = _router_returning(payload)
    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    return asyncio.run(cross_check.analyze_stage_chain("فشار در مایعات", ROWS, answers))


def _analyze(monkeypatch, payload=None, raises=None):
    return _analyze_with(monkeypatch, ANSWERS, payload, raises)


def test_server_side_detects_forbidden_words_even_if_model_misses_them(monkeypatch):
    result = _analyze(monkeypatch, {"mastery_status": "MASTERED", "per_question": [],
                                    "cross_check_findings": [], "improvement_suggestions": []})
    types = {f["type"] for f in result["cross_check_findings"]}
    assert "JARGON_VIOLATION" in types
    assert set(result["signals"]["forbidden_hits"]) == {"فشار", "چگالی", "ارتفاع"}


def test_mcq_secret_is_sent_to_model_but_never_returned():
    from api.routes_assessment import _question_to_exam_dict  # noqa: PLC0415

    class _Q:
        id = 1
        concept_id = 1
        text = "کدام؟"
        question_type = "mask_mcq"
        difficulty = "medium"
        cognitive_type = "conceptual"
        rubric = {
            "exam_type": "mask_mcq",
            "stage_title": "مرحله ۲: تست لایه نقاب",
            "options": ["a", "b", "c", "d"],
            "correct_option_index": 2,
            "forbidden_words": [],
            "expected_logic": "راز",
        }

    payload = _question_to_exam_dict(_Q(), 2)
    assert payload["stage_title"].startswith("مرحله ۲")
    assert payload["options"] == ["a", "b", "c", "d"]
    assert "correct_option_index" not in payload
    assert "expected_logic" not in payload


def test_debugging_supremacy_upgrades_harsh_model_verdict(monkeypatch):
    # پاسخِ پنجم بدونِ کلمهٔ ممنوعه بازنویسی می‌شود؛ وگرنه شاهدِ سخت حکم را سقف می‌زند.
    clean_answers = dict(ANSWERS)
    clean_answers[5] = (
        "وقتی می‌ری زیر آب، وزن آبِ روی سرت زیاد می‌شود و همین سنگینی است که "
        "تو را می‌فشارد؛ هرچه پایین‌تر، آبِ بیشتری روی سرت است."
    )
    monkeypatch.setattr(
        cross_check, "analyze_stage_chain", cross_check.analyze_stage_chain
    )
    result = _analyze_with(monkeypatch, clean_answers, {
        "mastery_status": "UNSTRUCTURED",
        "persona_title": "بی‌ساختار",
        "cross_check_findings": [],
        "per_question": [],
        "improvement_suggestions": [],
    })
    assert result["mastery_status"] == "MASTERED"
    assert result["mastery_note"]


def test_jargon_verdict_survives_debugging_supremacy(monkeypatch):
    """نقضِ کلماتِ ممنوعه شاهدِ سخت است؛ عیب‌یابیِ خوب نباید آن را پاک کند."""
    result = _analyze(monkeypatch, {
        "mastery_status": "UNSTRUCTURED",
        "persona_title": "بی‌ساختار",
        "per_question": [],
        "cross_check_findings": [],
        "improvement_suggestions": [],
    })
    assert result["mastery_status"] == "JARGON_DEPENDENT"
    assert "زندانی" in result["persona_title"]
    assert any(f["type"] == "JARGON_VIOLATION" for f in result["cross_check_findings"])


def test_clarification_requires_mirror_prompt(monkeypatch):
    # مدل گفت بازپرسی لازم است ولی متنِ آینه‌ای نداده ⇒ نباید جلسه معلق بماند
    result = _analyze(monkeypatch, {
        "needs_clarification": True,
        "clarification_data": {"contradicting_questions": [1, 2]},
        "mastery_status": "PARTIAL_FRAGMENTED",
        "per_question": [],
        "cross_check_findings": [],
    })
    assert result["needs_clarification"] is False
    assert result["clarification_data"] is None


def test_clarification_blocks_mastered_verdict(monkeypatch):
    result = _analyze(monkeypatch, {
        "needs_clarification": True,
        "clarification_data": {
            "contradicting_questions": [1, 2],
            "mirror_prompt": "تو گفتی وزن مایع… اما در تست زدی همان عمق!",
        },
        "mastery_status": "MASTERED",
        "per_question": [],
        "cross_check_findings": [],
    })
    assert result["needs_clarification"] is True
    assert result["mastery_status"] != "MASTERED"
    assert result["clarification_data"]["mirror_prompt"].startswith("تو گفتی")


def test_model_crash_falls_back_to_deterministic_rules(monkeypatch):
    result = _analyze(monkeypatch, raises="boom")
    assert result["analyzer"] == "deterministic-fallback"
    assert len(result["per_question"]) == 5
    assert result["cross_check_findings"], "قواعدِ قطعی باید حداقل یک یافته بدهند"


def test_garbage_model_output_still_yields_five_records(monkeypatch):
    class _Router:
        async def generate(self, *a, **k):
            return _Resp("این JSON نیست، فقط یک جملهٔ معمولی است")

    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    result = asyncio.run(cross_check.analyze_stage_chain("فشار", ROWS, ANSWERS))
    assert [p["order"] for p in result["per_question"]] == [1, 2, 3, 4, 5]
    assert result["mastery_status"] in {
        "MASTERED", "ILLUSION_OF_COMPETENCE", "JARGON_DEPENDENT",
        "PARTIAL_FRAGMENTED", "UNSTRUCTURED",
    }


def test_forbidden_word_matching_is_whole_word():
    assert cross_check.find_forbidden_hits("فشارِ آب زیاد است", ["فشار"]) == ["فشار"]
    assert cross_check.find_forbidden_hits("فشارسنج را آوردم", ["فشار"]) == []
    # ی/ك عربی و نیم‌فاصله باید نرمال شوند
    assert cross_check.find_forbidden_hits("چگالي مهم است", ["چگالی"]) == ["چگالی"]


# ───────────────────── مسیر HTTP (رگرسیونِ ذخیره‌سازی JSON) ─────────────────────
def test_clarify_persists_slip_resolved(tmp_path, monkeypatch):
    """رگرسیون: تغییرِ درجا در ستون JSON ذخیره نمی‌شد و CONTRADICTION هرگز
    به SLIP_RESOLVED تبدیل نمی‌شد. این تست کلِ چرخه را از طریق ORM می‌سنجد."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from models.database import Base
    from models.question import AssessmentSession
    from api import routes_assessment

    engine = create_engine(f"sqlite:///{tmp_path / 'clarify.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    session = AssessmentSession(
        student_id=1, concept_id=1, status="awaiting_clarification",
        trigger_type="topic_selection", trigger_detail="x",
        time_limit_seconds=1800, current_hypotheses=[
            {"type": "exam_meta", "needs_clarification": True,
             "cross_check_findings": [
                 {"title": "تضادِ نقاب", "type": "CONTRADICTION", "description": "d"}
             ]},
            {"type": "root_cause", "concept_name": "c", "reasoning": "r"},
        ],
        evidence_log=[],
    )
    db.add(session)
    db.commit()
    session_id = session.id

    captured = {}

    def _fake_report(db_arg, session_arg):
        captured["hypotheses"] = [dict(h) for h in (session_arg.current_hypotheses or [])]
        captured["status"] = session_arg.status
        return {"session_id": session_arg.id, "status": session_arg.status,
                "cross_check_findings": captured["hypotheses"][0]["cross_check_findings"]}

    monkeypatch.setattr(routes_assessment, "build_exam_report", _fake_report)

    class _User:
        id = 1
        role = "student"

    class _Body:
        clarification_response = "در تست بی‌دقتی کردم؛ منظورم وزن آب بود."

    result = asyncio.run(
        routes_assessment.submit_clarification(session_id, _Body(), db=db, user=_User())
    )

    assert result["status"] == "completed"
    meta = next(h for h in captured["hypotheses"] if h["type"] == "exam_meta")
    assert meta["needs_clarification"] is False
    assert meta["clarification_data"] is None
    assert meta["cross_check_findings"][0]["type"] == "SLIP_RESOLVED"
    assert meta["cross_check_findings"][0]["resolution"].startswith("در تست بی‌دقتی")
    # حکم ریشه‌ای باید حفظ شود
    assert any(h["type"] == "root_cause" for h in captured["hypotheses"])

    # و در دیتابیس هم ماندگار باشد
    db.expire_all()
    reloaded = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    stored_meta = next(h for h in reloaded.current_hypotheses if h["type"] == "exam_meta")
    assert stored_meta["cross_check_findings"][0]["type"] == "SLIP_RESOLVED"
    assert reloaded.status == "completed"


def test_off_topic_verbose_answers_cannot_be_mastered(monkeypatch):
    """پاسخ‌های مفصلِ بی‌ربط نباید «مسلط» بگیرند — رگرسیونِ آزمونِ واقعی.

    در آزمونِ واقعیِ «عدد اکسیداسیون»، همهٔ پاسخ‌ها دربارهٔ فشار آب بود و مدل
    با یک SYNERGY حکمِ MASTERED داد؛ کارنامه با خلاصهٔ خودش تناقض داشت.
    """
    chem_rows = [dict(r) for r in ROWS]
    chem_rows[0]["mapped_propositions"] = ["عدد اکسیداسیون الکترون از دست رفته"]
    chem_rows[2]["expected_logic"] = "الکترونگاتیویته و کشش الکترون"
    chem_rows[3]["expected_logic"] = "فلز قلیایی الکترون می‌دهد"
    chem_rows[4]["expected_logic"] = "بار یون و الکترون"

    off_topic = {
        1: "چون آبِ بالای سر وزن دارد و این وزن روی ما فشار می‌آورد؛ هرچه پایین‌تر، آب بیشتری بالای سر ماست.",
        2: "با ارتفاع زیاد می‌شود",
        3: "روی ماه وزن ستون کمتر می‌شود چون گرانش کمتر است، پس همان عمق فشار کمتری می‌دهد؛ اما هندسهٔ ظرف عوض نمی‌شود.",
        4: "سارا اشتباه می‌کند: حجم کل مهم نیست، ستونِ آبی که بالای نقطه است وزنش را می‌آورد.",
        5: "وقتی شنا می‌کنی و می‌ری ته استخر، سنگینی آبِ روی سرت بیشتر می‌شود و بیشتر تو را می‌فشارد.",
    }

    class _Router:
        async def generate(self, prompt, task_type, temperature=0.3):
            return _Resp(json.dumps({
                "mastery_status": "MASTERED",
                "persona_title": "مهندسِ مسلط",
                "cross_check_findings": [
                    {"title": "هم‌افزایی", "type": "SYNERGY", "description": "x"}
                ],
                "per_question": [],
                "improvement_suggestions": [],
            }, ensure_ascii=False))

    monkeypatch.setattr(cross_check, "get_router", lambda: _Router())
    result = asyncio.run(
        cross_check.analyze_stage_chain("عدد اکسیداسیون", chem_rows, off_topic)
    )

    assert result["signals"]["mostly_off_topic"] is True
    assert result["mastery_status"] != "MASTERED"
    assert any(f["type"] == "BLUFF_DETECTED" for f in result["cross_check_findings"])


def test_contradiction_without_clarification_is_dropped(monkeypatch):
    """تناقضی که از دانش‌آموز پرسیده نمی‌شود نباید در کارنامه بماند."""
    result = _analyze(monkeypatch, {
        "needs_clarification": False,
        "mastery_status": "PARTIAL_FRAGMENTED",
        "cross_check_findings": [
            {"title": "ناپایداری", "type": "CONTRADICTION", "description": "d"},
            {"title": "عیب‌یابی خوب", "type": "SYNERGY", "description": "s"},
        ],
        "per_question": [],
        "improvement_suggestions": [],
    })
    types = [f["type"] for f in result["cross_check_findings"]]
    assert "CONTRADICTION" not in types
    assert "SYNERGY" in types


def test_contradiction_is_kept_when_clarification_happens(monkeypatch):
    result = _analyze(monkeypatch, {
        "needs_clarification": True,
        "clarification_data": {
            "contradicting_questions": [2, 4],
            "mirror_prompt": "در تست گفتی بار، در عیب‌یابی گفتی شمارش!",
        },
        "mastery_status": "PARTIAL_FRAGMENTED",
        "cross_check_findings": [
            {"title": "ناپایداری", "type": "CONTRADICTION", "description": "d"},
        ],
        "per_question": [],
        "improvement_suggestions": [],
    })
    assert result["needs_clarification"] is True
    assert any(f["type"] == "CONTRADICTION" for f in result["cross_check_findings"])
