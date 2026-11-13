"""ماژول اختصاصی تولید آزمون کنکوری و شبیه‌سازی بانک سؤالات — منطبق با سرفصل‌های رسمی ایران.

این ماژول:
۱. پرامپت سیستم را با قید اکیدِ سرفصل‌های نظام جدید ایران و بخش BANNED TOPICS (بدون مباحث حذف‌شده مانند انتگرال در حسابان و معادلهٔ بیضی در هندسه دوازدهم) می‌سازد.
۲. نسبتِ «سؤالات بانک آزمون استاندارد» (`100 - ai_ratio`) به «سؤالات تشخیصی هوش مصنوعی» (`ai_ratio`) را اعمال می‌کند.
۳. قاعدهٔ اکیدِ Double-Escape برای بک‌اسلش‌های LaTeX درون رشته‌های JSON، منطق هوشمند/اختیاری برای `diagram_svg` و کالیبراسیون دقیق سطح سختی (`DIFFICULTY CALIBRATION`) را در پرامپت سیستم قرار می‌دهد.
۴. با حلقهٔ تلاش مجدد چندمدلی (`for attempt in range(3):`) و `safe_parse_json` در صورت شکست پارس JSON یا مدل اول، به‌طور خودکار با مدل رایگان بعدی تلاش می‌کند.
۵. پیش از ارسال پاسخ JSON به فرانت‌اند، تمام ارقام انگلیسی (`0123456789`) را با `to_persian_numbers` به ارقام فارسی (`۰۱۲۳۴۵۶۷۸۹`) تبدیل می‌کند.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from ai.json_sanitize import extract_json_array, restore_latex_commands, safe_parse_json
from ai.model_abstraction import get_router

logger = logging.getLogger(__name__)

# فهرست مدل‌های رایگان جایگزین برای حلقهٔ تلاش مجدد ۳ مرحله‌ای
FALLBACK_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "deepseek/deepseek-r1:free",
    "mistralai/mistral-7b-instruct:free",
]


def to_persian_numbers(text: Any) -> str:
    return str(text).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def persianize_svg_texts(svg: str) -> str:
    """درون تگ‌های <text> در SVG، همهٔ ارقام را فارسی می‌کند و خصیصه‌های مختصاتی SVG را سالم نگه می‌دارد."""
    if not svg:
        return svg
    return re.sub(
        r"(<text\b[^>]*>)([^<]*)(</text>)",
        lambda m: m.group(1) + to_persian_numbers(m.group(2)) + m.group(3),
        svg,
        flags=re.IGNORECASE,
    )


def persianize_json_values(obj: Any) -> Any:
    """تبدیل بازگشتی تمام رشته‌های موجود در خروجی JSON به ارقام فارسی و حفظ بک‌اسلش‌های LaTeX پیش از ارسال به فرانت‌اند."""
    obj = restore_latex_commands(obj)
    if isinstance(obj, str):
        if "<svg" in obj.lower():
            return persianize_svg_texts(obj)
        return to_persian_numbers(obj)
    if isinstance(obj, list):
        return [persianize_json_values(item) for item in obj]
    if isinstance(obj, dict):
        return {
            k: (persianize_svg_texts(v) if k == "diagram_svg" and isinstance(v, str) else persianize_json_values(v))
            for k, v in obj.items()
        }
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
    "CRITICAL SYLLABUS RULE (Nezam Jadid - نظام جدید 1397 onwards):\n"
    "You MUST generate questions exclusively compliant with the updated Iranian 6-3-3 high school textbooks published AFTER 1397 (2018).\n\n"
    "BANNED NEZAM-GHADIM TOPICS (STRICTLY FORBIDDEN):\n"
    "- Integrals (انتگرال) in Hesaban 2.\n"
    "- General & Standard Equations of Ellipse/Hyperbola (معادله بیضی و هذلولی) in Geometry 3 - Only focus on the definition/focal properties.\n"
    "- Matrix Inverses of 3x3 matrices (معکوس ماتریس 3x3).\n"
    "- Obsolete physics topics removed post-1397.\n\n"
    "Only include topics explicitly present in current 10th, 11th, and 12th grade Iranian textbooks.\n"
    "Do NOT use these banned concepts under any circumstances."
)

JSON_LATEX_ESCAPING_RULE = (
    r"CRITICAL JSON ESCAPING RULE: You MUST double-escape all LaTeX commands in the JSON. "
    r"Write \\begin{bmatrix}, \\frac, \\sqrt, \\theta, \\vec. Never use a single backslash for LaTeX commands, and NEVER escape the $ delimiter itself (write $ ... $, not \$). "
    r"For example, write \\begin{bmatrix} instead of \begin{bmatrix}, write \\frac{a}{b} instead of \frac{a}{b}, "
    r"and write \\cdot instead of \cdot. Failure to do this breaks JSON syntax."
)

LATEX_MATH_INSTRUCTION = (
    "CRITICAL MATH FORMATTING RULE:\n"
    "Every single mathematical symbol, formula, vector, power, matrix, variable, or inverse function "
    "MUST be enclosed in inline math `$ ... $` or block math `$$ ... $$`.\n"
    "Examples of CORRECT formatting:\n"
    "- Inverse trig / functions: `$\\cos^{-1}\\left(\\frac{4}{9}\\right)$` (NOT `cos^-1(4/9)`)\n"
    "- Matrix inverses & powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)\n"
    "- Vectors & subscripts: `$\\vec{n}_1 = (1, 2, 2)$` (NOT `n_1=(1,2,2)`)\n"
    "- Matrices: `$$\\begin{bmatrix} 2 & 1 \\\\ 1 & 3 \\end{bmatrix}$$`\n"
    "Never output raw LaTeX commands outside of `$` or `$$` delimiters!\n"
    "DO NOT write text like 'x be tavan 2'. Even inside LaTeX blocks, use Persian numbers (۰۱۲۳۴۵۶۷۸۹) where appropriate, e.g., $۲x + ۵ = ۱۲$."
)

SVG_DIAGRAM_INSTRUCTION = (
    "SVGs are OPTIONAL. Set `diagram_svg` to `null` if the question can be solved without a picture "
    "(e.g., standard algebra, matrices). NEVER attempt to draw precise intersecting coordinates "
    "(like a line tangent to a circle) because your coordinate math will be wrong. "
    "Only draw simple block diagrams, circuits, or abstract isolated shapes. "
    "If you are unsure about the visual alignment, return `null`.\n"
    "When you DO include an SVG diagram in `diagram_svg`, use font-family='Vazirmatn, Arial' for texts, "
    "and all numbers inside <text> tags MUST be Persian digits."
)

DIFFICULTY_CALIBRATION_INSTRUCTION = (
    "STRICT DIFFICULTY CALIBRATION:\n"
    "- آسان (Easy): Any question requiring direct substitution into a known formula "
    "(e.g., dot product for angle between vectors, single-step vector math). "
    "NEVER label a plug-and-chug question as Hard.\n"
    "- متوسط (Medium): Questions requiring 2 steps or basic concept connection.\n"
    "- سخت (Hard): Questions requiring deep multi-step synthesis or hidden traps."
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
{latex_instruction}
{json_escaping_rule}
{svg_instruction}
{difficulty_calibration}

شما «مؤلف ارشد سؤالات کنکوری» در سامانهٔ فهم‌یار هستید.

دستورات اکید:
۱. دقیقاً {count} سؤالِ چهارگزینه‌ایِ استاندارد نظام جدید ایران طراحی کن.
   - هشدار بسیار مهم: مباحث حذف‌شده از کتاب‌های درسی نظام جدید ایران (مانند «انتگرال» در حسابان، «معادلهٔ بیضی» و فرم استاندارد آن در هندسه دوازدهم — صرفاً تعریف و ویژگی‌های کانونی بیضی مجاز است — یا هر مبحث خارج از کتاب درسی) مطلقاً نباید در سؤالات یا گزینه‌ها بیاید.
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
   [{{"id": 1, "text": "متن سؤال با فرمول LaTeX و ارقام فارسی", "options": ["گزینهٔ ۱", "گزینهٔ ۲", "گزینهٔ ۳", "گزینهٔ ۴"], "correct_answer": 2, "subject": "فیزیک", "difficulty": "کنکوری", "source_tag": "تألیفی AI", "diagram_svg": null, "explanation": "یک خط استدلال کوتاه با ارقام فارسی"}}]

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
        latex_instruction=LATEX_MATH_INSTRUCTION,
        json_escaping_rule=JSON_LATEX_ESCAPING_RULE,
        svg_instruction=SVG_DIAGRAM_INSTRUCTION,
        difficulty_calibration=DIFFICULTY_CALIBRATION_INSTRUCTION,
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


async def generate_exam_questions(
    prompt: str,
    validator_fn: Optional[Callable[[Any], list[dict[str, Any]]]] = None,
    temperature: float = 0.8,
) -> tuple[list[dict[str, Any]], Optional[Exception]]:
    """حلقهٔ تلاش مجدد ۳ مرحله‌ای بین مدل‌های رایگان با پارس مقاوم JSON (safe_parse_json).

    خروجی: `(questions, last_provider_exc)`
    - اگر در هر یک از ۳ تلاش، آرایهٔ معتبر سؤال‌ها استخراج شود، بلافاصله برمی‌گرداند.
    - اگر تلاش اول با خطای پارس JSON یا خطای مدل مواجه شود، هشدار لاگ شده و بلافاصله با مدل بعدی در `FALLBACK_FREE_MODELS` تکرار می‌شود.
    """
    router = get_router()
    last_provider_exc: Optional[Exception] = None
    received_any_response = False

    for attempt in range(3):
        candidate_model = FALLBACK_FREE_MODELS[attempt % len(FALLBACK_FREE_MODELS)] if attempt > 0 else None
        try:
            try:
                response = await router.generate(
                    prompt,
                    "generate_konkur_preview",
                    temperature=temperature,
                    model_override=candidate_model,
                )
            except TypeError:
                response = await router.generate(
                    prompt,
                    "generate_konkur_preview",
                    temperature=temperature,
                )
            received_any_response = True
        except Exception as exc:
            last_provider_exc = exc
            logger.warning(
                "[ExamGenerator] Attempt %d/3 model call failed (model=%s): %s",
                attempt + 1,
                candidate_model or "default",
                exc,
            )
            print(f"[ExamGenerator] Attempt {attempt + 1}/3 model call failed (model={candidate_model or 'default'}): {exc}")
            continue

        try:
            raw_questions = extract_json_array(response.text or "")
            raw_questions = restore_latex_commands(raw_questions)
            questions = validator_fn(raw_questions) if validator_fn else raw_questions
            if questions:
                return restore_latex_commands(questions), None
            logger.warning(
                "[ExamGenerator] Attempt %d/3 returned empty validated questions (model=%s); retrying...",
                attempt + 1,
                getattr(response, "model_name", candidate_model or "default"),
            )
        except Exception as parse_exc:
            logger.warning(
                "[ExamGenerator] Attempt %d/3 JSON parse failed (model=%s): %s; retrying with next model...",
                attempt + 1,
                getattr(response, "model_name", candidate_model or "default"),
                parse_exc,
            )
            print(f"[ExamGenerator] Attempt {attempt + 1}/3 JSON parse failed: {parse_exc}")

    if not received_any_response and last_provider_exc is not None:
        return [], last_provider_exc
    return [], None
