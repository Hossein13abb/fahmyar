"""فاز ۳۰ — زبانِ انسانی در کارنامه: بدونِ ارجاعِ ساختاری و با نامِ مهارت.

این فایل سه چیز را قفل می‌کند که در کارنامه‌های پیشین شکسته بود:

  ۱. هیچ متنی به دانش‌آموز از «مرحله ۱/۲/…» حرف نمی‌زند — نه در خلاصهٔ
     کارنامه، نه در عنوانِ تیپ‌شناسی، نه در نگاشتِ یافته‌ها.
  ۲. پنج بُعدِ فهم عنوانِ دانش‌آموزپسند + سطحِ تسلط + امتیازِ شاهد‌محور دارند.
  ۳. امتیازِ نوارِ تسلط **ساختگی نیست**: بُعدِ بی‌پاسخ باید ``score_pct=None``
     بدهد تا فرانت‌اند نوارِ دروغین نکشد.
"""
from __future__ import annotations

import re

import pytest

from ai.brand_terms import scrub, scrub_deep
from ai.cross_check import _STATUS_PERSONA, _summary_from_stages
from reports.dimensions import (
    DIMENSION_SHORT_IDS,
    MASTERY_LEVELS,
    STAGE_DIMENSIONS,
    build_stage_dimensions,
)

# الگوی ارجاعِ ساختاری به مراحلِ آزمون. عمداً فقط «مرحله + رقم» را می‌گیرد؛
# «مرحلهٔ نوریِ فتوسنتز» (محتوای علمی) نباید گرفتار شود.
_STAGE_REF = re.compile(r"مرحلهٔ?\s*[۱-۹1-9]")


def _ten(stage_status: dict[int, str]) -> list[dict]:
    """ده رکوردِ سؤال از نگاشتِ {شمارهٔ مرحله: وضعیت}."""
    out = []
    for stage, status in stage_status.items():
        for offset in (0, 1):
            out.append(
                {
                    "order": (stage - 1) * 2 + 1 + offset,
                    "stage": stage,
                    "status": status,
                }
            )
    return out


# ─────────────────────────────────────────────────────────────────────────
# ۱) زبانِ کارنامه
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "stage_status",
    [
        {1: "CORRECT", 2: "CORRECT", 3: "CORRECT", 4: "CORRECT", 5: "CORRECT"},
        {1: "CORRECT", 2: "CORRECT", 3: "WRONG", 4: "CORRECT", 5: "CORRECT"},
        {1: "HALF_CORRECT", 2: "WRONG", 3: "WRONG", 4: "WRONG", 5: "HALF_CORRECT"},
        {
            1: "INSUFFICIENT_EVIDENCE",
            2: "CORRECT",
            3: "CORRECT",
            4: "CORRECT",
            5: "CORRECT",
        },
    ],
)
def test_summary_has_no_structural_stage_reference(stage_status):
    """خلاصهٔ کارنامه هرگز «مرحله ۲» یا «مرحلهٔ ۴» نمی‌نویسد."""
    summary = _summary_from_stages(_ten(stage_status), "PARTIAL_FRAGMENTED")
    assert not _STAGE_REF.search(summary), summary


def test_summary_names_the_cognitive_skill_not_the_stage():
    """بخشی که لنگ زده با **نامِ مهارت** صدا زده می‌شود، نه با شماره."""
    per_q = _ten({1: "CORRECT", 2: "CORRECT", 3: "WRONG", 4: "CORRECT", 5: "CORRECT"})
    summary = _summary_from_stages(per_q, "PARTIAL_FRAGMENTED")
    assert "پیش‌بینی علت‌ومعلولی رفتار پدیده" in summary


@pytest.mark.parametrize("title", list(_STATUS_PERSONA.values()))
def test_persona_titles_are_free_of_stage_references(title):
    """عنوان‌های تیپ‌شناسی هم ارجاعِ ساختاری ندارند."""
    assert not _STAGE_REF.search(title), title
    assert "دستکاری" not in title
    assert "ساعت‌ساز" not in title


@pytest.mark.parametrize(
    "raw",
    [
        "در مرحله ۲ گیج شدی.",
        "مرحلهٔ ۴ را ناقص گذاشتی",
        "الان در مرحله ۳ مشکل داری",
        "زنجیرهٔ علّی دستکاری را نچیدی",
    ],
)
def test_scrub_turns_stage_reference_into_plain_language(raw):
    """اگر مدل با وجودِ دستور، «مرحله ۲» بنویسد، دروازهٔ زبان پاکش می‌کند."""
    out = scrub(raw)
    assert not _STAGE_REF.search(out), out
    assert "دستکاری" not in out


def test_scrub_keeps_spacing_when_replacing():
    """جایگزینی نباید کلمه‌ها را به هم بچسباند («تستِ چهارگزینه‌ایگیج»)."""
    assert scrub("در مرحله ۲ گیج شدی.") == "در تستِ چهارگزینه‌ای گیج شدی."


def test_scrub_does_not_touch_scientific_stage_words():
    """«مرحلهٔ نوریِ فتوسنتز» محتوای علمی است و نباید سانسور شود."""
    text = "در مرحلهٔ نوری فتوسنتز، نور به انرژی شیمیایی تبدیل می‌شود."
    assert scrub(text) == text


def test_scrub_deep_reaches_nested_narrative():
    payload = {
        "persona_title": "در مرحله ۳ گیر کردی",
        "per_question": [{"cognitive_verdict": "مرحله ۴ را رد کردی"}],
    }
    cleaned = scrub_deep(payload)
    assert not _STAGE_REF.search(cleaned["persona_title"])
    assert not _STAGE_REF.search(cleaned["per_question"][0]["cognitive_verdict"])


# ─────────────────────────────────────────────────────────────────────────
# ۲) ابعادِ پنج‌گانه — عنوان، سطح و امتیاز
# ─────────────────────────────────────────────────────────────────────────
def test_five_dimensions_have_student_facing_titles():
    dims = build_stage_dimensions([])
    assert len(dims) == 5
    for dim in dims:
        assert dim["title"].strip()
        assert dim["subtitle"].strip()
        assert not _STAGE_REF.search(dim["title"])
        # عنوانِ تازه نباید همان نامِ درونیِ سنجشِ قبلی باشد (فاز ۱۰–۲۹).
        _OLD_TITLES = {
            "دانش مفهومی",
            "مقاومت در برابر دادهٔ انحرافی",
            "استدلال علّی",
            "نقد استدلال",
            "انتقال ساده",
        }
        assert dim["title"] not in _OLD_TITLES


def test_dimension_ids_match_frontend_contract():
    """شناسه‌های کوتاه باید دقیقاً همان‌هایی باشند که کامپوننت انتظار دارد."""
    dims = {d["key"]: d for d in build_stage_dimensions([])}
    assert dims["conceptual_knowledge"]["id"] == "intuition"
    assert dims["distractor_resistance"]["id"] == "noise_filter"
    assert dims["causal_reasoning"]["id"] == "causal"
    assert dims["critical_debugging"]["id"] == "critical"
    assert dims["simple_communication"]["id"] == "teaching"
    # و جدولِ نگاشت باید با خروجی یکی باشد
    for key, short in DIMENSION_SHORT_IDS.items():
        assert dims[key]["id"] == short


def test_mastery_level_maps_every_status_to_three_levels():
    dims = build_stage_dimensions(
        _ten(
            {
                1: "CORRECT",
                2: "WRONG",
                3: "HALF_CORRECT",
                4: "INSUFFICIENT_EVIDENCE",
                5: "CORRECT",
            }
        )
    )
    by_key = {d["key"]: d for d in dims}
    assert by_key["conceptual_knowledge"]["mastery_level"] == "mastered"
    assert by_key["distractor_resistance"]["mastery_level"] == "needs_work"
    assert by_key["causal_reasoning"]["mastery_level"] == "shaky"
    for dim in dims:
        assert dim["mastery_level"] in MASTERY_LEVELS


def test_score_is_evidence_based_not_invented():
    """امتیاز = میانگینِ واقعیِ پاسخ‌ها؛ نه عددِ تزئینی."""
    dims = {
        d["key"]: d
        for d in build_stage_dimensions(
            _ten({1: "CORRECT", 2: "HALF_CORRECT", 3: "WRONG", 4: "CORRECT", 5: "CORRECT"})
        )
    }
    assert dims["conceptual_knowledge"]["score_pct"] == 100
    assert dims["distractor_resistance"]["score_pct"] == 50
    assert dims["causal_reasoning"]["score_pct"] == 0


def test_unanswered_dimension_has_no_score():
    """بُعدی که هیچ شاهدی ندارد نباید نوارِ تسلط بگیرد (جلوگیری از دادهٔ ساختگی)."""
    dims = build_stage_dimensions([])
    for dim in dims:
        assert dim["score_pct"] is None
        assert dim["status"] == "not_assessed"
        assert dim["has_evidence"] is False


def test_unanswered_dimension_finding_is_second_person_and_self_contained():
    """جملهٔ بُعدِ بی‌پاسخ باید خودش روشن باشد، نه «به این مرحله پاسخ ندادی»."""
    dims = build_stage_dimensions([])
    for dim in dims:
        finding = dim["finding"]
        assert "این مرحله" not in finding
        assert not _STAGE_REF.search(finding)


def test_every_dimension_tuple_has_four_fields():
    """اسکیمای STAGE_DIMENSIONS باید هم‌زمان با فیلدهای نمایشی به‌روز بماند."""
    for entry in STAGE_DIMENSIONS:
        assert len(entry) == 4
        order, key, title, subtitle = entry
        assert isinstance(order, int) and 1 <= order <= 5
        assert key and title and subtitle


def test_label_and_title_stay_in_sync():
    """``label`` برای سازگاریِ قبلی مانده و باید با ``title`` یکی باشد."""
    for dim in build_stage_dimensions([]):
        assert dim["label"] == dim["title"]


# ─────────────────────────────────────────────────────────────────────────
# ۳) متنِ ذخیره‌شده در DB — مسیرِ دومِ تولید گزارش
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "stored",
    [
        "در ۵ مرحله لغزیدی: «سؤال مفهومی» نیمه‌درست.",
        "ضعیف‌ترین حلقهٔ زنجیره، مرحلهٔ عیب‌یابی بود.",
        "هر پنج مرحله با استدلالِ درست بسته شد.",
        "تسلط وقتی معنا دارد که همهٔ حلقه‌های زنجیره بسته شوند.",
    ],
)
def test_persisted_summary_never_leaks_stage_language(stored):
    """کارنامه‌های قدیمی متنِ قدیمی را در DB دارند؛ دروازهٔ خروج باید پاکش کند.

    این تست دقیقاً همان مسیری را می‌سنجد که ``build_exam_report`` طی می‌کند:
    خواندن از ``cognitive_report`` ذخیره‌شده و عبور از ``scrub_deep``.
    """
    cleaned = scrub_deep({"executive_summary": stored})["executive_summary"]
    assert "مرحله" not in cleaned, cleaned
    assert "زنجیره" not in cleaned, cleaned


def test_dimension_title_survives_the_language_gate():
    """عنوانِ رسمیِ بُعد نباید قربانیِ سانسورِ «تصویرِ کلان» شود."""
    titles = [d["title"] for d in build_stage_dimensions([])]
    for title in titles:
        assert scrub_deep(title) == title, f"{title} → {scrub_deep(title)}"


def test_scrub_keeps_plain_stage_word_for_science_content():
    """«مرحله» در محتوای علمی (بدونِ رقم/شمارش) دست‌نخورده می‌ماند."""
    for text in (
        "مرحلهٔ نوری فتوسنتز",
        "در کدام مرحلهٔ میتوز کروماتیدها جدا می‌شوند؟",
    ):
        assert scrub(text) == text, scrub(text)


# ─────────────────────────────────────────────────────────────────────────
# ۴) هم‌خوانیِ نوارِ تسلط با برچسبِ سطح
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "s1,s2",
    [
        ("CORRECT", "CORRECT"),
        ("CORRECT", "INSUFFICIENT_EVIDENCE"),
        ("CORRECT", "WRONG"),
        ("HALF_CORRECT", "HALF_CORRECT"),
        ("WRONG", "WRONG"),
        ("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_progress_bar_never_contradicts_the_badge(s1, s2):
    """نوارِ تسلط و برچسبِ سطح باید یک داستان بگویند.

    رگرسیونِ واقعیِ فاز ۳۰: از «درست + بی‌پاسخ» امتیازِ ۱۰۰ ساخته می‌شد ولی
    وضعیتِ تجمیعی «نیمه‌درست» بود؛ کارت نوارِ ۱۰۰٪ سبز نشان می‌داد با برچسبِ
    «نیازمند تثبیت». هر امتیازِ ≥ ۹۰ باید برچسبِ «تسلط کامل» داشته باشد و هر
    امتیازِ ۰ باید «نیازمند تقویت».
    """
    dim = build_stage_dimensions(
        [{"order": 7, "status": s1}, {"order": 8, "status": s2}]
    )[3]
    score = dim["score_pct"]
    level = dim["mastery_level"]
    assert score is not None
    if score >= 90:
        assert level == "mastered", f"score={score} but level={level}"
    if score == 0:
        assert level == "needs_work", f"score={score} but level={level}"
    assert 0 <= score <= 100


def test_score_is_never_full_when_a_question_went_blank():
    """یک سؤالِ بی‌پاسخ یعنی شاهدِ ناقص، نه تسلطِ کامل."""
    dim = build_stage_dimensions(
        [{"order": 7, "status": "CORRECT"}, {"order": 8, "status": "INSUFFICIENT_EVIDENCE"}]
    )[3]
    assert dim["score_pct"] < 100
    assert dim["mastery_level"] != "mastered"
