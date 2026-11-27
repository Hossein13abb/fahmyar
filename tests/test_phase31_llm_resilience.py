"""فاز ۳۱ — کارنامه نباید به‌خاطرِ یک آکولادِ باز به حالتِ اضطراری بیفتد.

سابقهٔ باگ (آزمونِ واقعیِ کاربر):
مدلِ ارزیابی (deepseek-v4.1-flash) به سقفِ ``max_tokens`` خورد و خروجی
وسطِ JSON بریده شد. ``extract_json_object`` برای ساختارِ ناقص ``None``
داد، پس **همهٔ** تحلیل — که تا ۹۰٪ درست تولید شده بود — دور ریخته شد و
کارنامه پیامِ «تحلیل‌گرِ هوش مصنوعی این بار خروجیِ قابل‌اتکایی نداد» را
نشان داد. مشکل از مدل نبود؛ از این بود که یک پرانتزِ بسته‌نشده کافی
بود تا کلِ خروجی دور انداخته شود.

این فایل سه چیز را قفل می‌کند:
  ۱. ترمیمِ JSONِ بریده‌شده در هر نقطه‌ای از بریدگی.
  ۲. عدمِ تخریبِ JSONِ سالم (دروازه نباید خروجیِ درست را خراب کند).
  ۳. لاگِ دقیق در مسیرِ شکست — «model call failed» بی‌جزئیات کافی نیست.
"""
from __future__ import annotations

import json

import pytest

from ai.json_sanitize import (
    close_truncated_json,
    extract_json_object,
    extract_json_object_resilient,
)

# نمونهٔ واقعی‌شکل از خروجیِ ارزیابی — همان ساختاری که مدل تولید می‌کند.
FULL = {
    "needs_clarification": False,
    "clarification_data": {"contradicting_questions": [], "mirror_prompt": ""},
    "mastery_status": "PARTIAL_FRAGMENTED",
    "persona_title": "قطعه‌قطعه فهمیدی — تصویر کامل نشده",
    "executive_summary": "تو در سؤالِ چهارم چند بار مکث کردی؛ دلیلش این است که رابطه را حفظ کرده‌ای.",
    "cross_check_findings": [
        {"title": "تناقض میان دو پاسخ", "type": "CONTRADICTION", "description": "..."}
    ],
    "per_question": [
        {
            "question_id": i,
            "order": i,
            "stage_title": "سؤال مفهومی",
            "status": "correct",
            "evidence_quote": "بریدهٔ پاسخ",
            "student_answer_summary": "خلاصه",
            "diagnostic_insight": "تشخیص",
            "wrong_claim": None,
            "cognitive_verdict": "یک جمله",
            "tutor_hint": "اشاره",
            "expected_logic_missed": None,
            "evidence_type": "strong_confirming",
            "confidence": 0.8,
        }
        for i in range(1, 11)
    ],
    "dimension_findings": [],
    "improvement_suggestions": ["قدمِ اول", "قدمِ دوم"],
}


def _as_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────
# ۱) پایداری در برابرِ بریدگی
# ─────────────────────────────────────────────────────────────────────────
def test_complete_json_parses_without_repair():
    """JSONِ سالم نباید «ترمیم‌شده» علامت بخورد."""
    obj, repaired = extract_json_object_resilient(_as_text(FULL))
    assert repaired is False
    assert obj == FULL


@pytest.mark.parametrize("keep_pct", [100, 99, 95, 90, 80, 70, 60, 50, 40, 30, 20])
def test_truncated_json_is_repaired_at_any_cut_point(keep_pct):
    """خروجیِ بریده‌شده در هر درصدی باید حداقل یک دیکشنریِ قابلِ استفاده بدهد.

    مهم‌ترین سنجه: در بریدگی‌های نزدیک به انتها (۹۰٪+)، فیلدهای کلیدی مثلِ
    ``mastery_status`` و ``persona_title`` باید نجات پیدا کنند — چون همان‌ها
    کارنامه را از حالتِ اضطراری بیرون می‌آورند.
    """
    text = _as_text(FULL)
    cut = text[: max(1, int(len(text) * keep_pct / 100))]
    obj, _ = extract_json_object_resilient(cut)
    assert isinstance(obj, dict), f"بریدگی در {keep_pct}% ترمیم نشد"


def test_repair_preserves_leading_fields():
    """ترمیم نباید فیلدهای ابتداییِ سالم را از دست بدهد."""
    text = _as_text(FULL)
    cut = text[: int(len(text) * 0.75)]
    obj, repaired = extract_json_object_resilient(cut)
    assert repaired is True
    assert obj["mastery_status"] == "PARTIAL_FRAGMENTED"
    assert obj["persona_title"] == FULL["persona_title"]


def test_repair_recovers_partial_per_question_list():
    """لیستِ نیمه‌کارهٔ per_question باید همان تعدادِ سؤالِ کامل‌شده را بدهد."""
    text = _as_text(FULL)
    cut = text[: int(len(text) * 0.7)]
    obj, _ = extract_json_object_resilient(cut)
    assert isinstance(obj.get("per_question"), list)
    assert len(obj["per_question"]) >= 1
    for item in obj["per_question"]:
        assert isinstance(item, dict)
        assert "order" in item


# ─────────────────────────────────────────────────────────────────────────
# ۲) جلوگیری از تخریب
# ─────────────────────────────────────────────────────────────────────────
def test_repair_does_not_touch_valid_nested_structures():
    """ساختارِ تودرتوی سالم (لیست در لیست) باید دست‌نخورده بماند."""
    payload = {"a": [{"b": [1, 2, {"c": "د"}]}], "e": "و"}
    obj, repaired = extract_json_object_resilient(_as_text(payload))
    assert obj == payload
    assert repaired is False


def test_garbage_input_returns_none_not_exception():
    """ورودیِ بی‌ربط نباید استثنا پرتاب کند — فقط None بدهد."""
    for junk in ("", "   ", "سلام", "null", "[1,2,3]"):
        obj, repaired = extract_json_object_resilient(junk)
        assert obj is None or isinstance(obj, dict)
        assert repaired in (True, False)


def test_still_works_when_model_wraps_json_in_markdown():
    """```json ... ``` نباید مانعِ پارس شود."""
    fenced = "```json\n" + _as_text(FULL) + "\n```"
    obj, _ = extract_json_object_resilient(fenced)
    assert obj == FULL


def test_close_truncated_json_returns_none_for_unrecoverable():
    """وقتی اصلاً شیئی شروع نشده، ترمیم باید None بدهد نه ساختارِ جعلی."""
    assert close_truncated_json("هیچ آکولادی این‌جا نیست") is None


# ─────────────────────────────────────────────────────────────────────────
# ۳) قراردادِ قبلی نمی‌شکند
# ─────────────────────────────────────────────────────────────────────────
def test_legacy_extract_still_returns_none_for_truncated():
    """``extract_json_object`` سخت‌گیر می‌ماند؛ رفتارِ قبلی حفظ شده است."""
    text = _as_text(FULL)
    cut = text[: int(len(text) * 0.6)]
    # این تابع عمداً خروجیِ ناقص را قبول نمی‌کند — ترمیم کارِ لایهٔ تازه است.
    assert extract_json_object(cut) is None


def test_repaired_output_is_marked_so_caller_can_log():
    """خروجیِ ترمیم‌شده باید علامت بخورد تا مسیرِ عیب‌یابی گم نشود."""
    text = _as_text(FULL)
    cut = text[: int(len(text) * 0.85)]
    obj, repaired = extract_json_object_resilient(cut)
    assert repaired is True
    assert isinstance(obj, dict)


# ─────────────────────────────────────────────────────────────────────────
# ۴) قفلِ نوشتنِ SQLite
# ─────────────────────────────────────────────────────────────────────────
def test_sqlite_engine_waits_instead_of_failing_on_lock():
    """نوشتنِ هم‌زمان نباید فوراً «database is locked» بدهد.

    سابقه: در آزمونِ زنده، ذخیرهٔ لاگِ مصرفِ مدل در پس‌زمینه با نوشتنِ
    درخواستِ اصلی برخورد کرد و قفل شد. در حالتِ پیش‌فرض SQLite منتظر
    نمی‌ماند؛ با ``timeout`` و ``WAL`` باید صبر کند.
    """
    from sqlalchemy import text

    from models.database import engine

    if not str(engine.url).startswith("sqlite"):
        pytest.skip("این تست مخصوصِ SQLite است")

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert int(conn.execute(text("PRAGMA busy_timeout")).scalar()) >= 10000


def test_connect_args_request_a_timeout():
    """``timeout`` باید در connect_args باشد — نه صفرِ پیش‌فرض."""
    from models import database

    if not str(database.engine.url).startswith("sqlite"):
        pytest.skip("این تست مخصوصِ SQLite است")
    assert database.connect_args.get("timeout", 0) >= 10
    assert database.connect_args.get("check_same_thread") is False


# ─────────────────────────────────────────────────────────────────────────
# ۵) پرامپت: سقف و دستورِ ایجاز
# ─────────────────────────────────────────────────────────────────────────
def test_eval_prompt_asks_for_brevity():
    """پرامپت باید مدل را از تولیدِ خروجیِ بی‌پایان باز دارد."""
    from ai.cross_check import _EXAM_PROMPT

    assert "ایجاز" in _EXAM_PROMPT
    assert "حداکثر" in _EXAM_PROMPT


def test_eval_prompt_demands_bare_json():
    """دستورِ «بدونِ بلوکِ ``` و بدونِ متنِ اضافه» باید در انتهای پرامپت باشد."""
    from ai.cross_check import _EXAM_PROMPT

    assert "فقط شیء JSON معتبر" in _EXAM_PROMPT
    # مهم است که *آخرین* دستور باشد، نه وسطِ پرامپت
    tail = _EXAM_PROMPT[-1400:]
    assert "آکولاد" in tail


def test_max_tokens_cap_is_generous_enough():
    """سقفِ توکن باید بالاتر از خروجیِ مشاهده‌شدهٔ واقعی (~۱۴٬۰۰۰) باشد."""
    from config import settings

    assert settings.OPENROUTER_MAX_TOKENS >= 24000
