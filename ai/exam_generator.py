"""ماژول اختصاصی تولید آزمون کنکوری و شبیه‌سازی بانک سؤالات — منطبق با سرفصل‌های رسمی ایران.

این ماژول:
۱. پرامپت سیستم را با قید اکیدِ سرفصل‌های نظام جدید ایران (بدون مباحث حذف‌شده مانند انتگرال در حسابان) می‌سازد.
۲. نسبتِ «سؤالات بانک آزمون استاندارد» (`100 - ai_ratio`) به «سؤالات تشخیصی هوش مصنوعی» (`ai_ratio`) را اعمال می‌کند.
۳. پیش از ارسال پاسخ JSON به فرانت‌اند، تمام ارقام انگلیسی (`0123456789`) را با `to_persian_numbers` به ارقام فارسی (`۰۱۲۳۴۵۶۷۸۹`) تبدیل می‌کند.
"""
from __future__ import annotations

import json
from typing import Any


def to_persian_numbers(text: Any) -> str:
    return str(text).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def persianize_json_values(obj: Any) -> Any:
    """تبدیل بازگشتی تمام رشته‌های موجود در خروجی JSON به ارقام فارسی پیش از ارسال به فرانت‌اند."""
    if isinstance(obj, str):
        return to_persian_numbers(obj)
    if isinstance(obj, list):
        return [persianize_json_values(item) for item in obj]
    if isinstance(obj, dict):
        return {k: persianize_json_values(v) for k, v in obj.items()}
    return obj


DIFFICULTY_MAP_FA = {
    "easy": "آسان",
    "medium": "متوسط",
    "hard": "سخت",
    "challenging": "کنکوری",
    "konkuri": "کنکوری",
    "آسان": "آسان",
    "متوسط": "متوسط",
    "سخت": "سخت",
    "کنکوری": "کنکوری",
}


SYSTEM_SYLLABUS_WARNING = (
    "CRITICAL: You are generating questions for the IRANIAN national curriculum. "
    "DO NOT include removed topics like Integrals (انتگرال) in Hesaban. "
    "Stick strictly to the provided topics."
)


def build_ratio_instruction(ai_ratio: int) -> str:
    ai_r = max(0, min(100, int(ai_ratio)))
    return (
        f"You have been requested to generate questions where {100-ai_r}% are STANDARD INSTITUTION BANK format "
        f"(standard Konkur-style, calculation-heavy, typical patterns) and {ai_r}% are AI DIAGNOSTIC format "
        f"(creative, conceptual, trap-based). You must distinctively adopt these styles based on the required ratio."
    )


KONKUR_EXAM_SYSTEM_PROMPT = """{syllabus_warning}
{ratio_instruction}

شما «مؤلف ارشد سؤالات کنکوری» در سامانهٔ فهم‌یار هستید.

دستورات اکید:
۱. دقیقاً {count} سؤالِ چهارگزینه‌ایِ استاندارد نظام جدید ایران طراحی کن.
   - هشدار بسیار مهم: مباحث حذف‌شده از کتاب‌های درسی نظام جدید ایران (مانند «انتگرال» در حسابان یا هر مبحث خارج از کتاب درسی) مطلقاً نباید در سؤالات یا گزینه‌ها بیاید.
   - تمام اعداد، فرمول‌های عددی و ضرایب در متن سؤال، گزینه‌ها و پاسخ تشریحی باید با ارقام فارسی (۰۱۲۳۴۵۶۷۸۹) نوشته شوند.
۲. سؤالات را دقیقاً بر اساس پیکربندی هر درس (`SUBJECT_CONFIGS`) بین درس‌های انتخاب‌شده ({subjects_labels}) تقسیم کن:
   - برای هر درس، دقیقاً به تعداد `count` مشخص‌شده، با سطح دشواری `difficulty` آن درس (آسان / متوسط / سخت / کنکوری) و صرفاً از ریز‌مباحث انتخاب‌شده (`subTopics`) سؤال طرح کن.
   - اگر برای درسی ریز‌مبحث انتخاب نشده بود، از مباحث رسمی کتاب درسی همان پایه طرح کن.
   - هر سؤال باید فیلد «subject» داشته باشد که دقیقاً نام فارسی همان درس است.
۳. نسبت سبک سؤالات:
   - {bank_ratio}٪ سؤالات به سبک «بانک آزمون استاندارد مؤسسات» (کنکور سراسری / قلم‌چی / گاج — تیپ‌های استاندارد و محاسباتی) با `source_tag` مناسب («کنکور ۱۴۰۲»، «قلم‌چی»، «گاج»).
   - {ai_ratio}٪ سؤالات به سبک «تشخیصی هوش مصنوعی» (مفهومی، خلاقانه و دام‌محور برای کشف بدفهمی) با `source_tag` برابر «تألیفی AI».
۴. هر سؤال دقیقاً ۴ گزینه دارد و فقط یک گزینه درست است.
۵. خروجی را فقط و فقط به صورت یک آرایهٔ JSON خالص برگردان؛ هیچ توضیح، مقدمه یا Markdown اضافه ننویس:
   [{{"id": 1, "text": "متن سؤال (با ارقام فارسی)", "options": ["گزینهٔ ۱", "گزینهٔ ۲", "گزینهٔ ۳", "گزینهٔ ۴"], "correct_answer": 2, "subject": "فیزیک", "difficulty": "کنکوری", "source_tag": "تألیفی AI", "explanation": "یک خط استدلال کوتاه با ارقام فارسی"}}]

<<<FIELD>>>{field_label}<<<END>>>
<<<SUBJECTS>>>{subjects_slugs}<<<END>>>
<<<SUBJECT_LABELS>>>{subjects_labels}<<<END>>>
<<<SUBJECT_CONFIGS>>>{subject_configs_json}<<<END>>>
<<<SUB_TOPICS>>>{sub_topics_json}<<<END>>>
<<<AI_PERCENTAGE>>>{ai_ratio}<<<END>>>
<<<AI_RATIO>>>{ai_ratio}<<<END>>>
<<<GRADE>>>{grade_label}<<<END>>>
<<<TOPIC>>>{topic}<<<END>>>
<<<QUESTION_TYPE>>>{question_type_label}<<<END>>>
<<<DIFFICULTY>>>{difficulty_label}<<<END>>>
<<<COUNT>>>{count}<<<END>>>
<<<CUSTOM>>>{custom_prompt}<<<END>>>
"""


def build_exam_preview_prompt(
    *,
    count: int,
    field_label: str,
    subjects_slugs: str,
    subjects_labels: str,
    subject_configs: list[dict[str, Any]],
    sub_topics: list[str],
    ai_ratio: int,
    grade_label: str,
    topic: str,
    question_type_label: str,
    difficulty_label: str,
    custom_prompt: str,
) -> str:
    ai_r = max(0, min(100, int(ai_ratio)))
    bank_r = 100 - ai_r
    return KONKUR_EXAM_SYSTEM_PROMPT.format(
        syllabus_warning=SYSTEM_SYLLABUS_WARNING,
        ratio_instruction=build_ratio_instruction(ai_r),
        count=count,
        field_label=field_label,
        subjects_slugs=subjects_slugs,
        subjects_labels=subjects_labels,
        subject_configs_json=json.dumps(subject_configs, ensure_ascii=False),
        sub_topics_json=json.dumps(sub_topics, ensure_ascii=False),
        ai_ratio=ai_r,
        bank_ratio=bank_r,
        grade_label=grade_label,
        topic=topic or "—",
        question_type_label=question_type_label,
        difficulty_label=difficulty_label,
        custom_prompt=custom_prompt or "—",
    )
