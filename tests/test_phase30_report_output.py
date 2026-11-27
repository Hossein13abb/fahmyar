"""فاز ۳۰ — دروازهٔ نهایی: کارنامهٔ کامل نباید هیچ زبانِ ساختاری داشته باشد.

تست‌های واحد هر جزء را می‌سنجند؛ این فایل خودِ **محصولِ خروجی** را می‌سنجد:
ساختارِ نهاییِ کارنامه همان‌طور که به فرانت می‌رسد. اگر روزی کسی بخشِ تازه‌ای
به گزارش اضافه کرد و زبانِ داخلی در آن چکید، این‌جا گرفته می‌شود.

علتِ وجود: در حینِ همین فاز دیدیم که خلاصهٔ ذخیره‌شده در ``cognitive_report``
از دروازه رد می‌شود ولی ``persona_title`` قدیمی می‌ماند، و نوارِ تسلط با
برچسبش نمی‌خواند. هر دو باگ فقط در خروجیِ *کامل* دیده می‌شدند، نه در تستِ
جزء‌به‌جزء.
"""
from __future__ import annotations

import re

import pytest

from ai.brand_terms import scrub_deep
from reports.dimensions import build_stage_dimensions

# الگوی زبانِ ساختاریِ آزمون در متنِ رو به دانش‌آموز.
# «مرحله» تنها، کلمهٔ فارسیِ سالمی است و در محتوای علمی می‌آید؛ این‌جا فقط
# صورت‌هایی گرفته می‌شود که به ساختارِ آزمون اشاره دارند.
_LEAKS = (
    re.compile(r"مرحلهٔ?\s*[۱-۹1-9]"),
    re.compile(r"مرحلهٔ?\s*(?:عیب‌یابی|ورودی|میانی)"),
    re.compile(r"در\s*[۰-۹0-9]+\s*مرحله"),
    re.compile(r"(?:پنج|۵|5)\s*مرحله"),
    re.compile(r"حلقهٔ?\s*زنجیره"),
    re.compile(r"زنجیرهٔ?\s*(?:فهم|استدلال)"),
    re.compile(r"دستکاریِ?\s*سیستم"),
    re.compile(r"ساعت‌ساز|چرخ‌دنده|مونتاژِ?\s*ذهنی|لایهٔ?\s*نقاب"),
)


def _assert_clean(text: str, where: str) -> None:
    assert isinstance(text, str)
    for pattern in _LEAKS:
        hit = pattern.search(text)
        assert not hit, f"{where}: «{hit.group()}» در متنِ دانش‌آموز ماند — {text[:160]}"


def _walk_strings(value, path="report"):
    """همهٔ رشته‌های یک ساختارِ تودرتو را با مسیرشان تولید می‌کند."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")


def _report_like_payload() -> dict:
    """حداقلِ ساختاری که کارنامه به فرانت می‌فرستد — با زبانِ قدیمیِ عمدی.

    عمداً متن‌های «کثیف» (نسخهٔ قبل از فاز ۳۰) در آن گذاشته شده تا دروازه
    واقعاً آزموده شود، نه اینکه با ورودیِ از پیش پاک، بی‌محتوا سبز شود.
    """
    dims = build_stage_dimensions(
        [
            {"order": 1, "status": "HALF_CORRECT"},
            {"order": 3, "status": "CORRECT"},
            {"order": 5, "status": "WRONG"},
            {"order": 7, "status": "CORRECT"},
            {"order": 9, "status": "CORRECT"},
        ]
    )
    return {
        "persona_title": "تفکرِ جزیره‌ای",
        "executive_summary": (
            "در ۵ مرحله لغزیدی: «سؤال مفهومی» نیمه‌درست. ضعیف‌ترین حلقهٔ زنجیره، "
            "مرحلهٔ عیب‌یابی بود. تسلط وقتی معنا دارد که همهٔ حلقه‌های زنجیره بسته شوند."
        ),
        "mastery_note": "زنجیرهٔ استدلال در مرحله ۳ ناقص ماند.",
        "stage_dimensions": dims,
        "suggestions": [
            "لایهٔ نقاب را با یک مثالِ تازه تمرین کن.",
            "مونتاژِ ذهنی را روی مسئلهٔ ساده‌تر امتحان کن.",
        ],
    }


def test_full_report_payload_is_free_of_structural_language():
    """خروجیِ نهاییِ کارنامه، بعد از دروازهٔ زبان، هیچ ارجاعِ ساختاری ندارد."""
    cleaned = scrub_deep(_report_like_payload())
    for path, text in _walk_strings(cleaned):
        if not text.strip():
            continue
        _assert_clean(text, path)


def test_gate_is_a_no_op_on_already_clean_text():
    """دروازه نباید کارنامهٔ سالم را دستکاری کند (پرهیز از تخریبِ متنِ خوب)."""
    clean = {
        "persona_title": "قطعه‌قطعه فهمیدی — تصویر کامل نشده",
        "executive_summary": (
            "در چند مهارت جا ماندی: «شهود و درک تصویر کلان» نیمه‌درست بود. "
            "در عوض، «ساده‌سازی و انتقال به زبان خودمانی» را محکم آوردی."
        ),
    }
    assert scrub_deep(clean) == clean


def test_dimension_titles_survive_the_full_gate():
    """عنوان‌های پنج بُعد از دروازهٔ کامل سالم بیرون می‌آیند."""
    dims = build_stage_dimensions([{"order": 1, "status": "CORRECT"}])
    cleaned = scrub_deep(dims)
    for before, after in zip(dims, cleaned):
        assert after["title"] == before["title"]
        assert after["subtitle"] == before["subtitle"]
        assert after["id"] == before["id"]


def test_dimension_findings_are_second_person():
    """تحلیلِ هر بُعد با فعلِ دوم‌شخص خطاب می‌شود، نه سوم‌شخصِ گزارش‌نویس."""
    # صورت‌های سوم‌شخصِ رایج در گزارش‌های قبلی
    THIRD_PERSON = ("دانش‌آموز", "او ", "وی ", "دانش آموز")
    for dim in build_stage_dimensions([{"order": 1, "status": "NEEDS_REVIEW"}]):
        finding = dim["finding"]
        for word in THIRD_PERSON:
            assert word not in finding, f"«{word}» در تحلیلِ {dim['id']}: {finding}"


@pytest.mark.parametrize(
    "key",
    [
        "conceptual_knowledge",
        "distractor_resistance",
        "causal_reasoning",
        "critical_debugging",
        "simple_communication",
    ],
)
def test_each_dimension_has_all_four_status_findings(key):
    """هر پنج بُعد برای هر چهار وضعیت جملهٔ اختصاصی دارند (نه fallbackِ مشترک)."""
    from reports.dimensions import _FINDINGS

    for status in ("mastered", "developing", "needs_work", "not_assessed"):
        assert (key, status) in _FINDINGS, f"{key}/{status} جمله ندارد"
        assert _FINDINGS[(key, status)].strip()
