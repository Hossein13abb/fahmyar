"""فاز ۱۷ — سپرِ اصطلاحاتِ متدولوژیِ داخلی.

این تست‌ها یک قرارداد را قفل می‌کنند: **هیچ رشته‌ای که به کاربر می‌رسد
نباید نامِ متدولوژیِ داخلی داشته باشد.** اگر فردا کسی فایلِ برچسب‌ها را
عوض کند یا مسیرِ سانسور را دور بزند، همین‌جا سرخ می‌شود.
"""

from __future__ import annotations

import pytest

from ai.brand_terms import (
    FORBIDDEN_LEAKS,
    PUBLIC_STAGE_BY_TYPE,
    PUBLIC_STAGE_TITLES,
    public_stage_title,
    scrub,
    scrub_deep,
)


# ── برچسب‌های عمومی ───────────────────────────────────────────────────

def test_public_titles_cover_five_stages():
    assert sorted(PUBLIC_STAGE_TITLES) == [1, 2, 3, 4, 5]


def test_every_exam_type_has_a_public_title():
    for exam_type in ("philosophy", "mask_mcq", "perturbation", "debugging", "feynman_synthesis"):
        assert PUBLIC_STAGE_BY_TYPE[exam_type]


@pytest.mark.parametrize("exam_type", list(PUBLIC_STAGE_BY_TYPE))
def test_public_labels_are_clean(exam_type):
    """برچسبِ منتشرشده نباید هیچ واژهٔ ممنوعه‌ای داشته باشد."""
    label = PUBLIC_STAGE_BY_TYPE[exam_type]
    for leak in FORBIDDEN_LEAKS:
        assert leak not in label, f"{exam_type} → «{label}» شاملِ «{leak}» است"


@pytest.mark.parametrize("stage,expected", list(PUBLIC_STAGE_TITLES.items()))
def test_public_stage_title_maps_stage_numbers(stage, expected):
    """کارنامه‌های قدیمی: هر رکورد خودش یک مرحله است."""
    assert public_stage_title(stage, ten_question_scale=False) == expected


def test_public_stage_title_maps_ten_question_orders():
    """ترتیبِ سؤال ۱..۱۰ → مرحلهٔ ۱..۵."""
    for order in range(1, 11):
        stage = (order - 1) // 2 + 1
        assert public_stage_title(order) == PUBLIC_STAGE_TITLES[stage]


# ── سانسورِ متن ───────────────────────────────────────────────────────

LEAKY_SAMPLES = [
    "در ۵ مرحله لغزیدی: «فلسفه و تصویر کلان» نیمه‌درست بود.",
    "تستِ لایهٔ نقاب را درست زدی ولی شهودت چیزِ دیگری می‌گوید.",
    "مرحلهٔ ۳: مونتاژ ذهنی و دستکاری سیستم را نیمه‌کاره رها کردی.",
    "عیب‌یابی ساعت خراب نشان داد استدلالت می‌شکند.",
    "چالش فاینمن: نتوانستی بدونِ اصطلاح توضیح بدهی.",
    "توضیح با دستِ بسته را نیمه‌کاره گذاشتی.",
    "تضادِ نقاب و شهود پیدا شد.",
]


@pytest.mark.parametrize("sample", LEAKY_SAMPLES)
def test_scrub_removes_internal_terms(sample):
    cleaned = scrub(sample)
    for leak in FORBIDDEN_LEAKS:
        assert leak not in cleaned, f"«{leak}» در «{cleaned}» باقی ماند"


def test_scrub_is_idempotent():
    once = scrub(LEAKY_SAMPLES[1])
    assert scrub(once) == once


def test_scrub_preserves_innocent_usage():
    """کلمهٔ مشترک با معنای روزمره نباید عوض شود."""
    text = "نقابِ ابوالهول در افسانه‌ها مانده است."
    assert scrub(text) == text


def test_scrub_ignores_non_strings():
    assert scrub(None) is None
    assert scrub(12) == 12


def test_scrub_deep_walks_nested_structures():
    payload = {
        "persona_title": "ساعتِ خراب",
        "per_question": [{"stage_title": "چالشِ فاینمن", "order": 1}],
        "tags": ["لایهٔ نقاب"],
    }
    cleaned = scrub_deep(payload)
    flat = str(cleaned)
    for leak in FORBIDDEN_LEAKS:
        assert leak not in flat
    assert cleaned["per_question"][0]["order"] == 1


# ── مسیرِ واقعیِ گزارش ────────────────────────────────────────────────

def test_stage_titles_in_stage_chain_are_public():
    from ai.stage_chain import STAGE_TITLES, STAGE_TITLES_FA

    for label in list(STAGE_TITLES.values()) + list(STAGE_TITLES_FA.values()):
        for leak in FORBIDDEN_LEAKS:
            assert leak not in label, f"برچسبِ «{label}» شاملِ «{leak}» است"


def test_cross_check_names_are_public():
    from ai import cross_check

    for mapping in (cross_check._NAMES, cross_check._STAGE_FA):
        for label in mapping.values():
            for leak in FORBIDDEN_LEAKS:
                assert leak not in label
