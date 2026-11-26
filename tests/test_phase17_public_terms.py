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


# ── فاز ۱۹ — استعارهٔ ساعت و چرخ‌دنده ──────────────────────────────────

METAPHOR_SAMPLES = [
    "رمز طلایی ساعت‌ساز را یادت باشه.",
    "فهمیدم! ساعت رو بستم.",
    "چرخ‌دنده‌های گمشدهٔ کارنامه.",
    "مهندسی که ساعت را بست.",
    "«ساعت» را در ذهنت بسته‌ای.",
    "چرخ‌دندهٔ اضافه در صورتِ سؤال.",
]


@pytest.mark.parametrize("sample", METAPHOR_SAMPLES)
def test_scrub_removes_clock_metaphor(sample):
    cleaned = scrub(sample)
    for leak in ("ساعت‌ساز", "چرخ‌دنده", "چرخ دنده", "ساعت خراب"):
        assert leak not in cleaned, f"«{leak}» در «{cleaned}» باقی ماند"


def test_scrub_keeps_real_clock():
    """«ساعتِ کلاس» استعارهٔ محصول نیست و نباید عوض شود."""
    text = "زنگِ ساعتِ کلاس ده است."
    assert scrub(text) == text


def test_missing_gear_prompt_asks_for_the_concept_not_a_metaphor():
    """فیلدِ گره‌های کلیدی باید اصلِ مفهوم را بخواهد، نه استعاره.

    «چرخ‌دنده» در پرامپت هست، ولی فقط در فهرستِ ممنوعه و مثالِ ❌ — نه در
    دستورِ تولید. پس وجودش در کلِ متن کافی نیست؛ باید مطمئن شویم تعریفِ
    خودِ فیلد استعاره نمی‌خواهد.
    """
    from ai.cross_check import _EXAM_PROMPT

    assert "اصلِ مفهومِ علمی" in _EXAM_PROMPT
    # تعریفِ فیلد (خطِ JSON schema) نباید استعاره داشته باشد
    field_line = next(
        line for line in _EXAM_PROMPT.splitlines() if '"missing_gear"' in line
    )
    assert "چرخ‌دنده" not in field_line
    assert "اصلِ مفهومِ علمی" in field_line


def test_metaphor_only_appears_in_the_ban_section():
    """«چرخ‌دنده» فقط باید در بلوکِ ممنوعه یا مثالِ ❌ باشد، نه در دستور.

    بلوکِ ممنوعه با ⛔ شروع می‌شود و تا خطِ خالیِ بعدی ادامه دارد؛ خطوطِ
    داخلِ آن علامتِ ⛔ جداگانه ندارند.
    """
    from ai.cross_check import _EXAM_PROMPT

    in_ban_block = False
    for line in _EXAM_PROMPT.splitlines():
        if "⛔" in line:
            in_ban_block = True
        elif not line.strip():
            in_ban_block = False
        if "چرخ‌دنده" not in line:
            continue
        ok = in_ban_block or ("❌" in line)
        assert ok, f"«چرخ‌دنده» در دستورِ مثبت آمده: {line.strip()[:80]}"


def test_assessment_prompt_has_the_writing_law():
    from ai.cross_check import _EXAM_PROMPT

    assert "قانون اکیدِ نگارش" in _EXAM_PROMPT
    for banned in ("ساعت‌ساز", "چرخ‌دنده", "فاینمن", "نقاب"):
        assert banned in _EXAM_PROMPT  # فقط در فهرستِ ممنوعه، نه در دستورِ تولید


def test_tutor_prompts_have_the_writing_law():
    from api import routes_tutor

    for prompt in (routes_tutor._QUESTION_SYSTEM, routes_tutor._CONTRADICTION_SYSTEM):
        assert "قانون اکیدِ نگارش" in prompt


def test_stage_chain_prompt_examples_use_public_titles():
    """نمونه‌های JSON داخلِ پرامپت نباید نامِ متدولوژی به مدل نشان دهند."""
    from ai import stage_chain

    prompt = stage_chain._BOOKLET_PROMPT
    for banned in ("چرخ‌دنده", "ساعت خراب", "لایه نقاب", "چالش فاینمن", "مونتاژ ذهنی"):
        assert banned not in prompt, f"«{banned}» در پرامپتِ ساختِ سؤال هست"


def test_scrub_removes_golden_password_label():
    """«رمز طلایی» برچسبِ ثابتِ محصول بود و باید عمومی شود."""
    assert "رمز طلایی" not in scrub("رمز طلایی: قبل از هر محاسبه…")
    assert "رمزِ طلایی" not in scrub("رمزِ طلاییِ ساعت‌ساز")
