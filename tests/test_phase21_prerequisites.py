"""فاز ۲۱ — زنجیرهٔ ریشه‌یابی و گره‌های پیش‌نیاز.

فاز ۲۰ گرافِ قدیمی را حذف کرد چون برای دانش‌آموز خوانا نبود. فاز ۲۱ همان
ایده را با دادهٔ ساختاریافته برمی‌گرداند:

    root_cause_chains  → **چطور** به این خطا رسیدی (زنجیرهٔ علّی)
    learning_gaps      → **چه چیزی** را تمرین کن (گره‌های قابلِ‌اجرا)

این تست‌ها هم گاردهای داده را قفل می‌کنند، هم مرزِ فاز ۲۰ را نگه می‌دارند:
گرافِ گره‌ایِ قدیمی نباید برگردد، در حالی که این دو بخش باید باشند.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from ai.cross_check import (
    CHAIN_ROLES,
    GAP_SEVERITIES,
    normalize_learning_gaps,
    normalize_root_cause_chains,
)

REPO = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return io.open(REPO.joinpath(*parts), encoding="utf-8").read()


# ── گاردهای داده: زنجیره ──────────────────────────────────────────────

def _chain(n_nodes: int, roles: list[str] | None = None) -> dict:
    nodes = [
        {
            "concept_name": f"مفهومِ {i}",
            "grade_and_subject": f"پایه {i} • درس",
            "role": (roles[i] if roles and i < len(roles) else "bridge"),
        }
        for i in range(n_nodes)
    ]
    return {
        "current_error_title": "خطای فعلی",
        "diagnosis_summary": "توضیح",
        "chain_nodes": nodes,
    }


def test_single_node_chain_is_rejected():
    """یک گره = ادعای بی‌سند؛ زنجیره نیست."""
    assert normalize_root_cause_chains([_chain(1)]) == []


def test_two_node_chain_is_accepted():
    assert len(normalize_root_cause_chains([_chain(2)])) == 1


def test_chain_without_root_origin_gets_one():
    """زنجیرهٔ بدونِ ریشه، برای UI نقطهٔ برجسته ندارد."""
    out = normalize_root_cause_chains([_chain(3)])
    roles = [n["role"] for n in out[0]["chain_nodes"]]
    assert "root_origin" in roles


def test_chain_node_without_grade_is_dropped():
    """بدونِ پایه و کتاب، دانش‌آموز نمی‌تواند منبع را پیدا کند."""
    bad = _chain(2)
    bad["chain_nodes"][0]["grade_and_subject"] = ""
    assert normalize_root_cause_chains([bad]) == []


def test_at_most_two_chains_are_kept():
    assert len(normalize_root_cause_chains([_chain(2), _chain(2), _chain(2)])) == 2


def test_invalid_role_falls_back_to_bridge():
    out = normalize_root_cause_chains([_chain(2, ["weird", "root_origin"])])
    assert out[0]["chain_nodes"][0]["role"] in CHAIN_ROLES


# ── گاردهای داده: گره‌های پیش‌نیاز ─────────────────────────────────────

def test_vague_gap_title_is_rejected():
    """«ضعف در ریاضی» گره نیست، برچسب است — دانش‌آموز نمی‌داند از کجا شروع کند."""
    assert normalize_learning_gaps(
        [{"gap_title": "ضعف در ریاضی", "severity": "critical"}]
    ) == []


def test_specific_gap_is_kept():
    gaps = normalize_learning_gaps(
        [{"gap_title": "تفاوتِ کارِ برآیند با کارِ تک‌تکِ نیروها", "severity": "critical"}]
    )
    assert len(gaps) == 1
    assert gaps[0]["severity"] == "critical"


def test_unknown_severity_defaults_to_shaky():
    gaps = normalize_learning_gaps([{"gap_title": "یک گرهٔ مشخص", "severity": "بحرانی"}])
    assert gaps[0]["severity"] in GAP_SEVERITIES
    assert gaps[0]["severity"] == "shaky"


def test_gaps_are_capped_at_four():
    many = [{"gap_title": f"گرهٔ شمارهٔ {i}"} for i in range(9)]
    assert len(normalize_learning_gaps(many)) == 4


def test_duplicate_gap_titles_collapse():
    dup = [{"gap_title": "همان گره"}, {"gap_title": "همان گره"}]
    assert len(normalize_learning_gaps(dup)) == 1


def test_empty_input_is_safe():
    assert normalize_root_cause_chains(None) == []
    assert normalize_root_cause_chains("nonsense") == []
    assert normalize_learning_gaps(None) == []
    assert normalize_learning_gaps({"gap_title": "x"}) == []


# ── قراردادِ پرامپت ────────────────────────────────────────────────────

def test_prompt_asks_for_structured_chains():
    from ai.cross_check import _EXAM_PROMPT

    assert "root_cause_chains" in _EXAM_PROMPT
    assert "learning_gaps" in _EXAM_PROMPT
    assert "root_origin" in _EXAM_PROMPT
    assert "critical" in _EXAM_PROMPT


def test_prompt_forbids_the_old_dag():
    from ai.cross_check import _EXAM_PROMPT

    assert "گراف وابستگی" in _EXAM_PROMPT  # فقط در فهرستِ ممنوعه
    assert "root_cause_hypotheses" in _EXAM_PROMPT  # فقط به‌عنوان «تولید نکن»


# ── اندپوینتِ معلم ─────────────────────────────────────────────────────

def test_tutor_accepts_learning_gap_type():
    from api.routes_tutor import ExplainRequest

    body = ExplainRequest(session_id=1, type="learning_gap", gap_id="gap-1")
    assert body.type == "learning_gap"
    assert body.gap_id == "gap-1"


def test_tutor_has_a_gap_system_prompt():
    from api import routes_tutor

    assert "سه بخش" in routes_tutor._GAP_SYSTEM
    assert "ساعت" in routes_tutor._GAP_SYSTEM  # فقط در قانونِ ممنوعه


def test_gap_prompt_carries_the_context():
    from api.routes_tutor import _build_gap_prompt

    prompt = _build_gap_prompt(
        {
            "concept_title": "فیزیک دوازدهم",
            "gap_title": "کارِ برآیند",
            "source_topic": "فیزیک دهم • فصل ۳",
            "why_you_slipped": "چون نیروها را جدا جمع کردی",
            "quick_fix_tip": "اول برآیند بگیر",
        }
    )
    assert "کارِ برآیند" in prompt
    assert "فیزیک دهم • فصل ۳" in prompt


# ── فرانت‌اند ─────────────────────────────────────────────────────────

def test_frontend_renders_both_sections():
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "<RootCauseAnalysisSection" in src
    assert "<LearningGapsSection" in src


def test_frontend_keeps_the_old_dag_out():
    """مرزِ فاز ۲۰: گرافِ گره‌ایِ قدیمی نباید برگردد."""
    src = _read("frontend", "src", "pages", "ReportView.jsx")
    assert "<RootCauseDag" not in src
    assert "<DagArrow" not in src


def test_sections_skip_rendering_when_empty():
    """باکسِ خالی «یافت نشد» نباید ساخته شود."""
    src = _read("frontend", "src", "components", "cognitive", "PrerequisiteSections.jsx")
    assert "if (list.length === 0) return null" in src


def test_prerequisite_sections_have_no_internal_jargon():
    src = _read("frontend", "src", "components", "cognitive", "PrerequisiteSections.jsx")
    for banned in ("ساعت", "چرخ‌دنده", "نقاب", "فاینمن"):
        assert banned not in src


def test_unknown_gap_id_is_a_404_not_a_silent_first_gap():
    """اگر شناسهٔ گره پیدا نشد، نباید بی‌صدا گرهٔ اول را برگرداند.

    fallbackِ ساکت این توهم را می‌ساخت که دکمهٔ کارتِ دوم هم همان متنِ کارتِ
    اول را می‌دهد — یعنی پاسخِ درست به سؤالِ غلط.
    """
    src = _read("api", "routes_tutor.py")
    assert "این گره در کارنامهٔ این آزمون پیدا نشد" in src


# ══ فاز ۲۲: سخت‌گیریِ «همیشه رندر شو، ولی هرگز دروغ نگو» ══════════════════

def test_report_never_falls_back_to_hardcoded_foreign_content():
    """اسپکِ فاز ۲۲ نمونهٔ ثابتِ «کار نیروی متغیر» می‌خواست؛ این ممنوع است.

    دانش‌آموزی که از «قانون اهم» امتحان داده، اگر این متن را ببیند فکر می‌کند
    ریشهٔ خطایش چیزِ دیگری بوده. fallback باید از شواهدِ همین آزمون بیاید.
    """
    # کامنتِ توضیحی این عبارت‌ها را نقل می‌کند؛ پس روی خودِ تابعِ fallback
    # assert می‌کنیم، نه روی کلِ فایل (درسِ «تستِ ساختاری و کامنت»).
    import inspect

    from reports import exam_report as module

    source = inspect.getsource(module._fallback_chains) + inspect.getsource(
        module._fallback_gaps
    )
    for foreign in ("نیروی متغیر", "مساحت زیر منحنی", "کار نیروی خالص", "اصطکاک"):
        assert foreign not in source


def test_gap_fallback_is_built_from_this_concept():
    """گره‌ها از misconceptions همین مفهوم می‌آیند، نه از مفهومِ دیگر."""
    import json

    from models.concept import Concept
    from reports.exam_report import _fallback_gaps

    concept = Concept(
        id=7, name="قانون اهم", subject="physics", grade=11,
        chapter="فصل جریان الکتریکی", topic="ohm_law",
        common_misconceptions=json.dumps(
            [{"misconception": "مقاومت را تابعِ ولتاژ می‌داند",
              "root_cause": "خلطِ علت و معلول در I=V/R"}],
            ensure_ascii=False,
        ),
    )
    gaps = _fallback_gaps(concept, [{"order": 3, "status": "WRONG"}])
    assert gaps
    assert gaps[0]["generated_by"] == "fallback"
    assert "مقاومت" in gaps[0]["gap_title"]
    assert "فیزیک" in gaps[0]["source_topic"]


def test_fallback_without_evidence_stays_empty():
    """بدونِ شاهدِ واقعی، دروغ نمی‌سازیم — همان قراردادِ «باکسِ خالی ممنوع»."""
    from models.concept import Concept
    from reports.exam_report import _fallback_chains, _fallback_gaps

    assert _fallback_chains(None, None, []) == []
    assert _fallback_gaps(None, []) == []
    bare = Concept(id=99, name="مفهومِ بدونِ داده", subject="math", grade=10)
    assert _fallback_gaps(bare, []) == []


def test_chain_without_cross_grade_prerequisite_is_not_invented():
    """بدونِ پیش‌نیازِ واقعی در مقطعِ پایین‌تر، زنجیره ساخته نمی‌شود.

    دلیل: زنجیرهٔ تک‌مقطعی در واقع همان «خطای فعلی» است با ظاهرِ تحلیلِ
    ریشه‌ای. به دانش‌آموز می‌گوید ریشه‌ات پیدا شد، درحالی‌که فقط سؤالِ
    اشتباهش تکرار شده — بدتر از نبودن.
    """
    from models.database import SessionLocal
    from models.concept import Concept
    from reports.exam_report import _fallback_chains

    db = SessionLocal()
    try:
        # مفهومِ «توان‌های صحیح» (id=1) هیچ یالِ بین‌پایه‌ای ندارد
        concept = db.query(Concept).filter(Concept.id == 1).first()
        assert concept is not None
        chain = _fallback_chains(
            db, concept, [{"order": 1, "status": "WRONG", "wrong_claim": "یک ادعا"}]
        )
        assert chain == []
    finally:
        db.close()


def test_chain_uses_real_dependency_graph():
    """زنجیره باید از جدولِ ``concept_dependencies`` بیاید، نه از فهرستِ ثابت.

    برای «قانون اهم» (id=7) گراف، «نسبت و تناسب» و «معادلهٔ درجهٔ اول» را
    به‌عنوان ابزارِ بین‌درسی ثبت کرده است — همان چیزی که اسپک با متنِ نمونهٔ
    ساختگی می‌خواست نشان دهد، ولی این‌جا **دادهٔ واقعی** است.
    """
    from models.database import SessionLocal
    from models.concept import Concept
    from reports.exam_report import _fallback_chains

    db = SessionLocal()
    try:
        concept = db.query(Concept).filter(Concept.id == 7).first()
        chains = _fallback_chains(
            db, concept,
            [{"order": 3, "status": "WRONG", "wrong_claim": "ولتاژ بیشتر ⇒ مقاومت بیشتر"}],
        )
        assert len(chains) == 1
        nodes = chains[0]["chain_nodes"]
        assert nodes[0]["role"] == "root_origin"
        assert nodes[-1]["concept_name"] == "قانون اهم"
        # ریشه در مقطعِ پایین‌تر است — وگرنه «بین‌پایه‌ای» دروغ می‌شد
        assert "دهم" in nodes[0]["grade_and_subject"]
        assert all(n["grade_and_subject"] for n in nodes)
    finally:
        db.close()
