"""تولید سؤال «درست‌به‌وقت» (JIT) با محدودیت‌های سختِ پرامپت.

قواعد تضمین‌شده در پرامپت:
  ۱) سؤال MUST یک پدیده/موقعیت واقعی را مطرح کند (نه سؤال انتزاعی کتابی)
  ۲) همهٔ داده‌های لازم (مواد، شرایط، مشاهدات) در متن سؤال داده شود
  ۳) نامِ مفهوم هدف در سؤال دیده نشود
  ۴) پاسخ یا مسیر استدلالیِ مورد انتظار افشا نشود
  ۵) مشاهدات از تفسیرها جدا باشند («محلول کمرنگ شد» نه «ماده کاهیده شد»)
  ۶) خروجی فقط JSON ساخت‌یافته باشد

خروجی JSON: question_text, phenomenon_description, required_data, rubric,
             mapped_propositions, mapped_misconceptions (+ question_type, difficulty, cognitive_type)
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import settings
from models.concept import Concept
from models.question import Question, QUESTION_TYPES
from ai.model_abstraction import get_router, AIProviderError


class QuestionGenerationError(Exception):
    pass


BEHAVIOR_FA = {
    "recall": "یادآوری و بازشناسی (دانش پایه)",
    "explain": "توضیح چراییِ یک پدیده (استدلال علّی)",
    "convert_representation": "تبدیل بین نمایش‌ها (شکل ↔ فرمول ↔ کلام)",
    "identify_conditions": "تشخیص شرایط و استثناها",
    "predict": "پیش‌بینی نتیجهٔ یک تغییر",
    "solve": "حل مسئله با داده‌های مشخص",
    "apply_novel": "به‌کارگیری در موقعیت کاملاً نو",
    "identify_error": "شناسایی و نقد خطای یک پاسخ/استدلال دیگر",
    "connect": "اتصال مفهوم به مفاهیم دیگر (بین‌درسی)",
}

_SYSTEM = """شما یک طراح سؤال تشخیصیِ خبره برای سیستم «فهم‌یار» هستید.
تنها یک سؤال تشخیصی به زبان فارسی طراحی می‌کنید که هدفش سنجیدنِ فهمیدن است، نه حفظ کردن.

قواعد قطعی و غیرقابل‌نقض:
1. سؤال حتماً باید یک پدیده یا موقعیت واقعی مطرح کند (آزمایشگاه، کارگاه، زندگی روزمره، طبیعت).
2. همهٔ داده‌های لازم (مواد، شرایط، مقادیر، مشاهدات) در متن سؤال بیاید؛ دانش‌آموز نباید به منبع دیگری نیاز داشته باشد.
3. نامِ مفهوم هدف و اصطلاح فنیِ همان مفهوم در متن سؤال نیاید — دانش‌آموز نباید بفهمد کدام بخش درس سنجیده می‌شود.
4. پاسخ، نیمه‌پاسخ یا مسیر استدلالیِ مورد انتظار در سؤال لو نرود.
5. مشاهدات را از تفسیرها جدا کنید: بنویسید «محلول کمرنگ شد» نه «ماده کاهیده شد». هرگز تفسیر علمی را به‌جای مشاهده جا نزنید.
6. خروجی باید فقط یک شیء JSON معتبر باشد — بدون هیچ متن اضافه، بدون توضیح، بدون Markdown و بدون ```.
7. سؤال نباید بله/خیر باشد؛ پاسخ باید نیازمند استدلال باشد.
8. سؤال تکراریِ پاسخ‌های قبلی نباشد.

ساختار دقیق خروجی (همهٔ کلیدها الزامی):
{
  "question_text": "متن کامل سؤال به زبان فارسی",
  "phenomenon_description": "توصیف کوتاه موقعیتِ واقعی (فقط مشاهده)",
  "required_data": ["داده ۱", "داده ۲"],
  "question_type": "phenomenon_explain | compare_explanations | predict | categorize | error_identify | novel_application",
  "difficulty": "easy | medium | hard",
  "cognitive_type": "recall | conceptual | computational | combined",
  "rubric": {
    "correct_reasoning": "استدلال درست چیست (برای مصحح/تحلیل‌گر، نه برای دانش‌آموز)",
    "misconception_indicators": {"نشانهٔ بدفهمی به‌صورت نقل‌قول یا رفتار": "چرا این نشانهٔ آن بدفهمی است"},
    "partial_credit_signs": ["نشانهٔ فهمیدنِ ناقص"],
    "non_conceptual_errors": ["خطای صرفاً محاسباتی/بی‌دقتی که نباید به‌عنوان نفهمی تفسیر شود"]
  },
  "mapped_propositions": ["گزارهٔ ۱ که این سؤال می‌سنجد"],
  "mapped_misconceptions": ["بدفهمیِ هدف که این سؤال می‌تواند آشکارش کند"]
}"""


def _build_prompt(
    concept: Concept,
    target_proposition: str,
    target_misconception: Optional[str],
    behavior: str,
    previous_responses: list[str],
    cross_subject: bool,
) -> str:
    behavior_desc = BEHAVIOR_FA.get(behavior, behavior)
    previous = "\n".join(f"- {r[:300]}" for r in (previous_responses or [])[-5:]) or "(هیچ‌کدام)"
    cross_note = (
        "این سؤال باید موقعیت بین‌درسی باشد (مثال: کاربرد ابزار ریاضی در فیزیک/شیمی)."
        if cross_subject
        else "سؤال می‌تواند درون‌درسی باشد."
    )
    misconception_block = target_misconception or "(بدون بدفهمیِ هدف — فقط گزارهٔ مورد نظر)"
    return f"""{_SYSTEM}

=== مفهوم ===
<<<CONCEPT>>>{concept.name} ({concept.subject} — پایهٔ {concept.grade})<<<END>>>

=== گزارهٔ هدف (دانش‌آموز نباید این را ببیند) ===
<<<PROPOSITION>>>{target_proposition}<<<END>>>

=== بدفهمیِ هدف (دانش‌آموز نباید این را ببیند) ===
<<<MISCONCEPTION>>>{misconception_block}<<<END>>>

=== رفتار شناختیِ هدف ===
{behavior} → {behavior_desc}
{cross_note}

=== رفتارها و بدفهمی‌های رایج این مفهوم (فقط برای راهنمایی شما) ===
رفتارهای هدف مفهوم: {", ".join(concept.target_behaviors or [])}
بدفهمی‌های رایج: {json.dumps(concept.common_misconceptions or [], ensure_ascii=False)[:1500]}

=== پاسخ‌های قبلی این دانش‌آموز (از آن‌ها دوری کن) ===
{previous}

اکنون فقط JSON خروجی را بده."""


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """اولین شیء JSON معتبر در متن را استخراج می‌کند."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _validate_payload(data: dict[str, Any], target_proposition: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise QuestionGenerationError("خروجی مدل دیکشنری نیست")
    question_text = str(data.get("question_text") or "").strip()
    if len(question_text) < 20:
        raise QuestionGenerationError("متن سؤال تولیدی بیش از حد کوتاه است")

    qtype = str(data.get("question_type") or "phenomenon_explain")
    if qtype not in QUESTION_TYPES:
        qtype = "phenomenon_explain"

    difficulty = str(data.get("difficulty") or "medium")
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    cognitive = str(data.get("cognitive_type") or "conceptual")
    if cognitive not in {"recall", "conceptual", "computational", "combined"}:
        cognitive = "conceptual"

    rubric = data.get("rubric") if isinstance(data.get("rubric"), dict) else {}
    rubric = {
        "correct_reasoning": str(rubric.get("correct_reasoning", "")),
        "misconception_indicators": rubric.get("misconception_indicators") if isinstance(rubric.get("misconception_indicators"), dict) else {},
        "partial_credit_signs": list(rubric.get("partial_credit_signs") or []),
        "non_conceptual_errors": list(rubric.get("non_conceptual_errors") or []),
    }
    # داده‌های موقعیت را هم در rubric نگه می‌داریم تا تحلیل‌گر ببیند
    if data.get("phenomenon_description"):
        rubric["phenomenon_description"] = str(data["phenomenon_description"])
    if data.get("required_data"):
        rubric["required_data"] = list(data["required_data"]) if isinstance(data["required_data"], list) else [str(data["required_data"])]

    mapped_props = data.get("mapped_propositions")
    if not isinstance(mapped_props, list) or not mapped_props:
        mapped_props = [target_proposition]

    mapped_misc = data.get("mapped_misconceptions")
    if not isinstance(mapped_misc, list):
        mapped_misc = []

    return {
        "text": question_text,
        "question_type": qtype,
        "difficulty": difficulty,
        "cognitive_type": cognitive,
        "rubric": rubric,
        "mapped_propositions": [str(p) for p in mapped_props],
        "mapped_misconceptions": [str(m) for m in mapped_misc],
    }


async def generate_diagnostic_question(
    concept: Concept,
    target_proposition: str,
    target_misconception: str | None,
    behavior: str,
    previous_responses: list[str],
    cross_subject: bool = False,
) -> Question:
    """یک سؤال تشخیصیِ JIT می‌سازد و شیء Question (تأیید نشده، pending) برمی‌گرداند.

    توجه: سؤال تولیدی به‌طور پیش‌فرض approval_status='pending' دارد و تا تأیید معلم
    فقط در همان جلسهٔ جاری استفاده می‌شود (در گزارش پروژه قید شده است).
    """
    router = get_router()
    prompt = _build_prompt(concept, target_proposition, target_misconception,
                           behavior, previous_responses, cross_subject)

    data: Optional[dict[str, Any]] = None
    model_name, cost = "", 0.0
    last_error: str | None = None

    for attempt, (temp, extra) in enumerate([(0.8, ""), (0.2, "\n\nخروجی قبلی نامعتبر بود. فقط و فقط JSON خالص بده.")]):
        try:
            resp = await router.generate(prompt + extra, "generate_question", temperature=temp)
            model_name, cost = resp.model_name, resp.cost_usd
            data = _extract_json(resp.text)
            if data is not None:
                break
            last_error = "JSON استخراج نشد"
        except AIProviderError as exc:
            last_error = str(exc)
        except Exception as exc:  # بودجه و غیره
            last_error = str(exc)
            break

    if data is None:
        raise QuestionGenerationError(f"تولید سؤال شکست خورد: {last_error}")

    try:
        payload = _validate_payload(data, target_proposition)
    except QuestionGenerationError:
        raise
    except Exception as exc:
        raise QuestionGenerationError(f"اعتبارسنجی خروجی ناموفق بود: {exc}") from exc

    return Question(
        concept_id=concept.id,
        text=payload["text"],
        question_type=payload["question_type"],
        difficulty=payload["difficulty"],
        cognitive_type=payload["cognitive_type"],
        rubric=payload["rubric"],
        mapped_propositions=payload["mapped_propositions"],
        mapped_misconceptions=payload["mapped_misconceptions"],
        source="ai_generated",
        approval_status="pending",  # طبق الزام: سؤالات AI هرگز بدون تأیید معلم منتشر نمی‌شوند
        ai_model_used=model_name,
        generation_cost_usd=cost,
    )
