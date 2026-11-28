"""فاز ۳۷ — تفکیک‌کنندهٔ دامنه و طرحِ ۵-ایستگاهیِ ریاضیات صوری."""
from __future__ import annotations

import pytest

from ai.stage_chain import MATH_SUBJECT_IDS, build_booklet_prompt, is_math_subject
from models.concept import Concept


@pytest.mark.parametrize("sid", sorted(MATH_SUBJECT_IDS))
def test_all_10_math_subject_ids_detected(sid: str):
    assert is_math_subject(sid, "") is True


@pytest.mark.parametrize("name", ["ریاضی ۱", "هندسه ۲", "حسابان ۱", "آمار و احتمال", "ریاضیات گسسته"])
def test_math_persian_keywords_detected(name: str):
    assert is_math_subject("", name) is True


@pytest.mark.parametrize("sid,name", [("physics", "فیزیک ۱"), ("chemistry", "شیمی ۲"), ("biology", "زیست‌شناسی ۳")])
def test_empirical_sciences_not_treated_as_math(sid: str, name: str):
    assert is_math_subject(sid, name) is False


def test_build_booklet_prompt_uses_math_blueprint_for_math_and_not_for_physics():
    math_concept = Concept(
        subject="geometry",
        grade=10,
        chapter="فصل ۱",
        topic="geom10-c1",
        name="تجانس مستقیم و معکوس",
        core_propositions=["جایگاهِ این مفهوم در کتابِ هندسه ۱"],
    )
    phy_concept = Concept(
        subject="physics",
        grade=10,
        chapter="فصل ۲",
        topic="phy10-c5",
        name="فشار در شاره‌ها",
        core_propositions=["جایگاهِ این مفهوم در کتابِ فیزیک ۱"],
    )
    math_prompt = build_booklet_prompt(math_concept, math_concept.core_propositions, [])
    phy_prompt = build_booklet_prompt(phy_concept, phy_concept.core_propositions, [])

    assert "زنجیره ۵ مرحله‌ای تفکر ریاضی (۱۰ سوال تشریحی)" in math_prompt
    assert "شکار مغالطه و تحلیل استدلال غلط" in math_prompt
    assert '"type": "open_ended"' in math_prompt
    assert "زنجیره ۵ مرحله‌ای تفکر ریاضی (۱۰ سوال تشریحی)" not in phy_prompt


def test_statistics_11_exists_in_curriculum():
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "curriculum" / "iranHighSchoolCurriculum.js").read_text(encoding="utf-8")
    assert "id: 'statistics-11'" in src
    assert "فصل ۱: آشنایی با مبانی ریاضیات" in src
    assert "فصل ۴: آمار استنباطی" in src
