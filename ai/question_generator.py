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
from ai.json_sanitize import extract_json_object


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


# استخراج مقاوم JSON — پیاده‌سازی مشترک در ai/json_sanitize.py
_extract_json = extract_json_object



_BOOKLET_PROMPT = """شما «متخصص طراحی آزمون تشخیصی» فهم‌یار هستید. برای مفهوم «{concept}» ({subject} — پایهٔ {grade}) یک دفترچهٔ آزمون تشخیصی ۹ سؤالی بسازید.

هدف: سنجش «فهمیدن» — نه حفظ کردن. هر ۹ سؤال باید دقیقاً این ابعاد را پوشش دهند (به همین ترتیب):
1. مفهومی/استدلالی — بدون عدد: باید بگوید «چرا» و علت را توضیح دهد.
2. سناریوی دنیای واقعی/کاربردی — یک گارگاه/کارگاه/زندگی واقعی.
3. نموداری/شکلی — شما باید برای این سؤال یک SVG سادهٔ درون‌خطی (inline, بدون ارجاع خارجی، پس‌زمینهٔ سفید، viewBox مناسب) در فیلد "diagram_svg" تولید کنید؛ مثلاً نمودار خطی، ستونی یا مدار ساده.
4. تلهٔ بدفهمی شایع (Misconception Trap) — دقیقاً «{misconception}» را به چالش بکشد؛ صورت سؤال باید طوری باشد که دانش‌آموز وسوسه شود همان اشتباه را تکرار کند.
5. محاسباتی/رویه‌ای — با دادهٔ عددی ساده؛ فقط ریاضیِ پایهٔ اصلی.
6. حفظی/تعریفی — تعریف دقیق و مرزبندی مفهوم.
7. مفهومی سطح‌بالا — «اگر X دو برابر شود چه می‌شود و چرا؟».
8. سناریوی واقعی بین‌درسی — پیوند با دروس ریاضی/شیمی.
9. نموداری/شکلی — این سؤال هم باید "diagram_svg" داشته باشد (نمودار متفاوت از سؤال ۳).

قواعد قطعی:
- فقط JSON معتبر برگردانید — هیچ متن توضیحی قبل یا بعد از JSON (حتی یک کلمه) ننویسید. پاسختان باید دقیقاً با «{{» شروع شود و با «}}» پایان یابد.
- همهٔ متن‌ها فارسی و روان باشند.
- exam_type یکی از این‌هاست: conceptual | real_world | diagram | misconception_trap | computational | definitional
- شماره order از ۱ تا ۹.
- فیلد rubric جدا ندهید؛ برای هر سؤال mapped_propositions را پر کنید.

خروجی دقیقاً این ساختار:
{{
  "questions": [
    {{
      "order": 1,
      "exam_type": "conceptual",
      "text": "...",
      "difficulty": "easy | medium | hard",
      "cognitive_type": "recall | conceptual | computational | combined",
      "mapped_propositions": ["دقیقاً یکی از گزاره‌های فهرست ورودی"],
      "diagram_svg": "<svg ...>...</svg>  (فقط برای سؤال‌های ۳ و ۹، بقیه null)",
      "misconception_targeted": "فقط برای misconception_trap، وگرنه null"
    }}
  ]
}}

<<<CONCEPT>>>{concept}<<<END>>>
<<<PROPOSITION>>>{proposition}<<<END>>>
<<<MISCONCEPTION>>>{misconception}<<<END>>>
<<<PROPOSITIONS>>>{propositions_json}<<<END>>>
<<<WRONG_ANSWER>>>{wrong_answer}<<<END>>>
"""


def _booklet_items_to_questions(concept, items, model_name: str, cost: float) -> list["Question"]:
    """اعتبارسنجی و ساخت اشیای Question دفترچه."""
    propositions = list(concept.core_propositions or [])
    misconceptions = list(concept.common_misconceptions or [])
    fallback_prop = propositions[0] if propositions else "گزارهٔ هدف"
    questions = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if len(text) < 15:
            continue  # سؤال بی‌معنی را دور بریز
        exam_type = str(raw.get("exam_type") or "conceptual").strip().lower()
        if exam_type not in {"conceptual", "real_world", "diagram", "misconception_trap", "computational", "definitional"}:
            exam_type = "conceptual"
        difficulty = str(raw.get("difficulty") or "medium").strip().lower()
        if difficulty not in {"easy", "medium", "hard"}:
            difficulty = "medium"
        cognitive = str(raw.get("cognitive_type") or "conceptual").strip().lower()
        mapped = [p for p in (raw.get("mapped_propositions") or []) if isinstance(p, str) and p.strip()]
        if not mapped:
            mapped = [fallback_prop]
        diagram = raw.get("diagram_svg")
        diagram_svg = diagram.strip() if isinstance(diagram, str) and "<svg" in diagram else None
        mis_trap = raw.get("misconception_targeted")
        mapped_mis = [mis_trap.strip()] if isinstance(mis_trap, str) and mis_trap.strip() else (
            [misconceptions[0]] if exam_type == "misconception_trap" and misconceptions else [])
        questions.append(Question(
            concept_id=concept.id,
            text=text,
            question_type=exam_type,
            difficulty=difficulty,
            cognitive_type=cognitive if cognitive in {"recall", "conceptual", "computational", "combined"} else "conceptual",
            rubric={
                "exam_type": exam_type,
                "diagram_svg": diagram_svg,
                "required_data": [],
                "correct_reasoning": f"دانش‌آموز باید با تکیه بر گزارهٔ «{mapped[0]}» استدلال علّی کند.",
                "misconception_indicators": {m: "نشانهٔ بدفهمی هدف" for m in mapped_mis},
            },
            mapped_propositions=mapped,
            mapped_misconceptions=mapped_mis,
            source="ai_generated",
            approval_status="pending",
            ai_model_used=model_name,
            generation_cost_usd=cost,
        ))
    return questions


async def generate_test_booklet(concept, wrong_answer: dict | None = None) -> tuple[list["Question"], str, float]:
    """دفترچهٔ آزمون تشخیصی ۹ سؤالی برای مفهوم می‌سازد (هرگز دفترچهٔ ناقص را رد نمی‌کند؛ حداقل ۸ سؤال لازم است).

    خروجی: (فهرست Questionهای ذخیره‌نشده, model_name, cost_usd)
    در شکستِ کاملِ مدل، یک دفترچهٔ اضطراریِ حداقلی از الگوهای قطعی ساخته می‌شود تا دانش‌آموز همیشه آزمونی داشته باشد.
    """
    propositions = list(concept.core_propositions or [])
    misconceptions = list(concept.common_misconceptions or [])
    wrong_text = ""
    if wrong_answer:
        wrong_text = f"مسئله: {wrong_answer.get('problem_text', '')} | پاسخ غلط دانش‌آموز: {wrong_answer.get('student_answer', '')}"
    prompt = _BOOKLET_PROMPT.format(
        concept=concept.name,
        subject=concept.subject,
        grade=concept.grade,
        proposition=propositions[0] if propositions else "گزارهٔ هدف",
        misconception=misconceptions[0] if misconceptions else "بدفهمی رایج مفهوم",
        propositions_json=json.dumps(propositions, ensure_ascii=False),
        wrong_answer=wrong_text or "—",
    )

    router = get_router()
    data = None
    model_name, cost = "", 0.0
    try:
        resp = await router.generate(prompt, "generate_test_booklet", temperature=0.7)
        model_name, cost = resp.model_name, resp.cost_usd
        data = extract_json_object(resp.text)
    except Exception as exc:
        print(f"[Booklet] model call failed: {exc}")

    items = (data or {}).get("questions") if isinstance(data, dict) else None
    questions = _booklet_items_to_questions(concept, items or [], model_name, cost) if items else []

    if len(questions) < 8:
        # دفترچهٔ اضطراریِ حداقلی — شش پوششِ اساسی به‌ترتیب
        print(f"[Booklet] only {len(questions)} valid questions from model; topping up with deterministic template bank.")
        fallback_prop = (propositions[0] if propositions else "گزارهٔ هدف")
        fallback_mis = (misconceptions[0] if misconceptions else "بدفهمی رایج مفهوم")
        template = [
            ("conceptual", f"«{concept.name}» را با کلمات خودتان توضیح دهید؛ چرا رخ می‌دهد و علت و معلول آن چیست؟", "medium", "conceptual"),
            ("real_world", f"یک سناریوی واقعی (کارگاه/خانه/بازار) بسازید که در آن «{concept.name}» نقش دارد و توضیح دهید چه می‌گذرد و چرا.", "medium", "conceptual"),
            ("misconception_trap", f"«{fallback_mis}» — آیا این استدلال درست است؟ با دلیل علمی رد یا تأیید کنید.", "hard", "conceptual"),
            ("computational", "با داده‌های فرضیِ ساده، مقدار خواسته‌شده را محاسبه کنید و مراحل را بنویسید.", "easy", "computational"),
            ("definitional", f"تعریف دقیق «{concept.name}» را بنویسید و آن را از مفاهیم نزدیک جدا کنید.", "easy", "recall"),
            ("conceptual", f"اگر یک کمیتِ کلیدیِ «{concept.name}» دو برابر شود چه می‌شود و چرا؟", "medium", "conceptual"),
            ("real_world", "مثالی از زندگی روزمره بیاورید که در آن این مفهوم به کار می‌رود و علت کارکردش را توضیح دهید.", "hard", "combined"),
            ("diagram", "اگر کمیت مستقل دو برابر شود، روند تغییرات کمیت وابسته را توصیف کنید و شکل ذهنی خود را رسم/شرح دهید.", "hard", "conceptual"),
            ("definitional", f"سه تفاوت اصلی «{concept.name}» با نزدیک‌ترین مفهومِ هم‌خانواده را فهرست کنید.", "medium", "recall"),
        ]
        have = len(questions)
        for i, (et, text, diff, cog) in enumerate(template):
            if have >= 9:
                break
            questions.append(Question(
                concept_id=concept.id, text=text, question_type=et, difficulty=diff, cognitive_type=cog,
                rubric={"exam_type": et, "diagram_svg": None, "correct_reasoning": f"با تکیه بر «{fallback_prop}»",
                        "misconception_indicators": {fallback_mis: "نشانهٔ بدفهمی هدف"} if et == "misconception_trap" else {}},
                mapped_propositions=[fallback_prop], mapped_misconceptions=[fallback_mis] if et == "misconception_trap" else [],
                source="ai_generated", approval_status="pending", ai_model_used=model_name or "template-fallback",
                generation_cost_usd=0.0,
            ))
            have += 1
    return questions[:10], model_name or "mixed", cost

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
