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
from ai.json_sanitize import extract_json_object, safe_parse_json
from ai.exam_generator import FALLBACK_FREE_MODELS, JSON_LATEX_ESCAPING_RULE


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

_SYSTEM = r"""شما یک طراح سؤال تشخیصیِ خبره برای سیستم «فهم‌یار» هستید.
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
}

CRITICAL MATH FORMATTING RULE:
Every single mathematical symbol, formula, vector, power, matrix, variable, or inverse function MUST be enclosed in inline math `$ ... $` or block math `$$ ... $$`.
Examples of CORRECT formatting:
- Inverse trig / functions: `$\cos^{-1}\left(\frac{4}{9}\right)$` (NOT `cos^-1(4/9)`)
- Matrix inverses & powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)
- Vectors & subscripts: `$\vec{n}_1 = (1, 2, 2)$` (NOT `n_1=(1,2,2)`)
- Matrices: `$$\begin{bmatrix} 2 & 1 \\ 1 & 3 \end{bmatrix}$$`
Never output raw LaTeX commands outside of `$` or `$$` delimiters!
Even inside LaTeX blocks, you MUST use Persian numbers (۰۱۲۳۴۵۶۷۸۹). For example: $۲x + ۵ = ۱۲$.
CRITICAL JSON ESCAPING RULE: You MUST double-escape all LaTeX commands in the JSON. Write \\begin{bmatrix}, \\frac, \\sqrt, \\theta, \\vec. Never use a single backslash for LaTeX commands, and NEVER escape the $ delimiter itself (write $ ... $, not \$).
CRITICAL SYLLABUS RULE (Nezam Jadid - نظام جدید 1397 onwards):
You MUST generate questions exclusively compliant with the updated Iranian 6-3-3 high school textbooks published AFTER 1397 (2018).

BANNED NEZAM-GHADIM TOPICS (STRICTLY FORBIDDEN):
- Integrals (انتگرال) in Hesaban 2.
- General & Standard Equations of Ellipse/Hyperbola (معادله بیضی و هذلولی) in Geometry 3 - Only focus on the definition/focal properties.
- Matrix Inverses of 3x3 matrices (معکوس ماتریس 3x3).
- Obsolete physics topics removed post-1397.

Only include topics explicitly present in current 10th, 11th, and 12th grade Iranian textbooks.
Do NOT use these concepts under any circumstances.
SVGs are OPTIONAL. Set `diagram_svg` to `null` if the question can be solved without a picture (e.g., standard algebra, matrices). NEVER attempt to draw precise intersecting coordinates (like a line tangent to a circle) because your coordinate math will be wrong. Only draw simple block diagrams, circuits, or abstract isolated shapes. If you are unsure about the visual alignment, return `null`.
STRICT DIFFICULTY CALIBRATION:
- آسان (Easy): Any question requiring direct substitution into a known formula (e.g., dot product for angle between vectors, single-step vector math). NEVER label a plug-and-chug question as Hard.
- متوسط (Medium): Questions requiring 2 steps or basic concept connection.
- سخت (Hard): Questions requiring deep multi-step synthesis or hidden traps.
"""


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



def _stringify_item(item) -> str:
    """گزاره/بدفهمی ممکن است متن ساده یا دیکشنریِ غنی باشد — همیشه رشتهٔ خوانا برمی‌گرداند."""
    if isinstance(item, dict):
        for key in ("misconception", "text", "label", "proposition", "root_cause", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item or "").strip()


_BOOKLET_PROMPT = r"""CRITICAL MATH FORMATTING RULE:
Every single mathematical symbol, formula, vector, power, matrix, variable, or inverse function MUST be enclosed in inline math `$ ... $` or block math `$$ ... $$`.
Examples of CORRECT formatting:
- Inverse trig / functions: `$\cos^{-1}\left(\frac{4}{9}\right)$` (NOT `cos^-1(4/9)`)
- Matrix inverses & powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)
- Vectors & subscripts: `$\vec{n}_1 = (1, 2, 2)$` (NOT `n_1=(1,2,2)`)
- Matrices: `$$\begin{bmatrix} 2 & 1 \\ 1 & 3 \end{bmatrix}$$`
Never output raw LaTeX commands outside of `$` or `$$` delimiters!
Even inside LaTeX blocks, you MUST use Persian numbers (۰۱۲۳۴۵۶۷۸۹). For example: $۲x + ۵ = ۱۲$.
CRITICAL JSON ESCAPING RULE: You MUST double-escape all LaTeX commands in the JSON. Write \\begin{bmatrix}, \\frac, \\sqrt, \\theta, \\vec. Never use a single backslash for LaTeX commands, and NEVER escape the $ delimiter itself (write $ ... $, not \$).
CRITICAL SYLLABUS RULE (Nezam Jadid - نظام جدید 1397 onwards):
You MUST generate questions exclusively compliant with the updated Iranian 6-3-3 high school textbooks published AFTER 1397 (2018).

BANNED NEZAM-GHADIM TOPICS (STRICTLY FORBIDDEN):
- Integrals (انتگرال) in Hesaban 2.
- General & Standard Equations of Ellipse/Hyperbola (معادله بیضی و هذلولی) in Geometry 3 - Only focus on the definition/focal properties.
- Matrix Inverses of 3x3 matrices (معکوس ماتریس 3x3).
- Obsolete physics topics removed post-1397.

Only include topics explicitly present in current 10th, 11th, and 12th grade Iranian textbooks.
Do NOT use these concepts under any circumstances.
SVGs are OPTIONAL. Set `diagram_svg` to `null` if the question can be solved without a picture (e.g., standard algebra, matrices). NEVER attempt to draw precise intersecting coordinates (like a line tangent to a circle) because your coordinate math will be wrong. Only draw simple block diagrams, circuits, or abstract isolated shapes. If you are unsure about the visual alignment, return `null`.
STRICT DIFFICULTY CALIBRATION:
- آسان (Easy): Any question requiring direct substitution into a known formula (e.g., dot product for angle between vectors, single-step vector math). NEVER label a plug-and-chug question as Hard.
- متوسط (Medium): Questions requiring 2 steps or basic concept connection.
- سخت (Hard): Questions requiring deep multi-step synthesis or hidden traps.

شما «متخصص ارشد طراحی آزمون تشخیصی عمیق (Deep Diagnostic)» برای سیستم فهم‌یار هستید. برای مفهوم «{concept}» ({subject} — پایهٔ {grade}) یک دفترچهٔ آزمون تشخیصی ۹ سؤالی بسازید.

هدف: سنجشِ **فهم عمیق** — نه حفظ کردن، نه به‌خاطرسپاری، نه سؤالِ قابل‌جستجوی گوگل. هر سؤال باید لایهٔ دومِ تفکر را بسنجد: دانش‌آموز باید استدلال کند، استدلالِ غلط را نقد کند، یا تناقض شناختی را حل کند.

══════════════ بخش اول — ارتقای سطح شناختی (Deep Diagnostic) ══════════════
1. **مطلقاً ممنوع: سؤال سطحی و تعریفی (Googleable).** پرسیدنِ تعریف مستقیم («... چیست؟»)، حفظِ فرمول، یا سؤالاتی که با جستجو/حفظ جواب داده می‌شوند، مطلقاً ممنوع است. هر سؤال باید نیاز به استدلال اختصاصیِ همان موقعیت داشته باشد.
2. **تحلیل استدلال غلط (Flawed Argument) الزامی است.** حداقل دو سؤال (سؤال ۴ و یک سؤال دیگر) باید یک سناریوی واقعیِ مشخص بسازند که در آن یک دانش‌آموز فرضی یک استدلالِ منطقی‌نما اما **غلط** می‌آورد؛ سپس از دانش‌آموز خواسته شود **دقیقاً نقطهٔ فروپاشیِ آن استدلال** را پیدا و با دلیل علمی نقد کند. (مثلاً: «سَن دوستت می‌گوید چون جرم X دو برابر شده، پس اثرش هم دو برابر می‌شود — آیا این استدلال درست است؟ دقیقاً کجا می‌شکند؟»)
3. **طراحی تناقض شناختی (Cognitive Conflict) الزامی است.** حداقل دو سؤال باید موقعیتی بسازند که شهود اولیهٔ دانش‌آموز با قوانین علمی در تضاد باشد (مثلاً: پدیدهٔ خلاف انتظار روزمره — یک شیء سنگین و سبک هم‌زمان از یک ارتفاع می‌افتند / بادکنک در نیتروژن مایع / آب در خلاء می‌جوشد) و از دانش‌آموز بخواهند بگوید چه اتفاقی می‌افتد و چرا شهودش اشتباه بود.
4. **پیوند با دنیای واقعی باید عمیقاً ملموس باشد — نه مثال‌های کلیشه‌ای کتاب.** مثلاً در شیمی، تحلیلِ زنگ‌زدگیِ قطعهٔ خاصی در یک خط لولهٔ صنعتی؛ در فیزیک، طراحیِ مدار یک شارژر واقعی یا دمرنگه‌کاری یک آسانسور؛ در زیست، تصمیم‌سازی بالینی در یک کلینیک. حتماً نام موقعیت، شرایط، مواد/ابزار و مشاهدات مشخص باشند.
5. مشاهدات از تفسیرها جدا باشند: بنویسید «محلول کمرنگ شد» نه «ماده کاهیده شد». هرگز تفسیر علمی را به‌جای مشاهده جا نزنید.
6. نامِ مفهوم هدف و اصطلاح فنیِ همان مفهوم در متن سؤال نیاید — دانش‌آموز نباید بفهمد کدام بخش درس سنجیده می‌شود.
7. پاسخ، نیمه‌پاسخ یا مسیر استدلالیِ مورد انتظار در سؤال لو نرود.
8. سؤال تکراریِ پاسخ‌های قبلی نباشد.
9. **زبان: تمام صورت سؤالات (فیلد text) و همهٔ فیلدهای متنیِ خروجی باید ۱۰۰٪ فارسیِ روان باشند؛ حتی یک کلمهٔ انگلیسی در فیلد text مجاز نیست.** همهٔ فرمول‌ها و نمادهای ریاضی باید داخل `$ ... $` یا `$$ ... $$` نوشته شوند (مثل `$\\frac{۵\\sqrt{۱۴}}{۱۴}$`، `$\\vec{a}=(۱,۲)$`، `$\\cos^{-1}\\left(\\frac{۴}{۹}\\right)$`) و **داخل این بلوک‌های ریاضی تمام ارقام باید فارسی (۰۱۲۳۴۵۶۷۸۹) باشند** — رندرکنندهٔ تصویریِ PDF و KaTeX این ارقام را کامل پشتیبانی می‌کنند. هیچ فرمولی را با کلمات توصیف نکنید («رادیکال ۷» ممنوع؛ `$\\sqrt{۷}$` درست است). (نکته: اعتبارسنجِ خودکارِ سیستم هر سؤالِ غیر فارسی را رد می‌کند.)
10. **ممنوعیت ارجاع به شکلِ ناموجود:** در سؤالاتی که diagram_svg آن‌ها null است (یعنی سؤال‌های ۱، ۲، ۴، ۵، ۶، ۷ و ۸)، استفاده از عبارت‌هایی مانند «نمودار زیر»، «شکل زیر» یا «مدار زیر» مطلقاً ممنوع است؛ متن سؤال باید کاملاً مستقل و بدون نیاز به هیچ شکل و نموداری باشد.

══════════════ بخش دوم — مهندسی دقیق SVG و جداول ══════════════
**قوانین تولید SVG (diagram_svg):**
الف. فقط و فقط از تگ‌های پایه استفاده کنید: `<svg>`, `<rect>`, `<circle>`, `<line>`, `<polyline>`, `<text>`. استفاده از `<path>`، `<g>`، `<ellipse>`، `<image>`، `<script>` و هر تگ دیگری مطلقاً ممنوع است.
ب. تگ بازشونده باید دقیقاً این ساختار را داشته باشد (همین ترتیبِ خصیصه‌ها و همین مقادیر):
   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">`
ج. تمام شکل‌ها باید استایل درون‌خطیِ ساده داشته باشند (مثل `stroke="black" stroke-width="2" fill="none"`). از `class`، `style` و CSS خارجی پرهیز کنید.
د. از نوشته‌های فارسی در داخل SVG مطلقاً پرهیز کنید (مرورگرها آن را به‌هم می‌ریزند). فقط لیبل‌های انگلیسی/ریاضی استفاده کنید (A, B, F1, x, y, V, I, R).
هـ. **قانون عدم هم‌انباشتگی (No Overlap): هیچ عنصر `<text>` نباید روی همان مختصات y یک `<line>` یا داخل فضای یک `<rect>`/`<circle>` قرار گیرد؛ لیبل‌ها حتماً حداقل ۲۰ پیکسل بالاتر یا پایین‌تر از هر خط و کادر باشند.** (اعتبارسنجِ هندسیِ سیستم، SVGای که این فاصله را نقض کند حذف می‌کند.)
و. برای مرکزچین شدن لیبلِ بالای یک قطعه حتماً از ویژگی `text-anchor="middle"` استفاده کنید و x را برابرِ مرکزِ قطعه بگذارید (مثال: rect در x=180 و عرض 64 → لیبل «R» در x=212 با text-anchor="middle").
ز. حتماً تگ `</svg>` در انتها بسته شود و SVG کامل و معتبر باشد (تگ‌های self-closing با `/>`).
ح. نمودار باید واقعاً اطلاعاتی باشد: محورها یا مقادیر کلیدی مشخص، موقعیت‌ها و ابعاد درست.

**قوانین تولید جدول:**
الف. اگر سؤال نیاز به جدول دارد، از فرمت مارک‌داونِ کاملاً استاندارد با فاصله‌گذاری دقیق استفاده کنید.
ب. جدول را در فیلد `text` (متن سؤال) قرار دهید، نه در فیلد `diagram_svg`.
ج. خط جداکنندهٔ جدول حتماً حداقل سه خط تیره داشته باشد (مثل `|---|---|` یا `|----:|:---|`).
د. هر سطر جدول با `|` شروع و با `|` پایان یابد؛ تعداد خانه‌ها در همهٔ سطرها برابر باشد.

══════════════ ساختار دفترچه (۹ سؤال، به همین ترتیب) ══════════════
1. مفهومی/استدلالی عمیق — بدون عدد؛ باید زنجیرهٔ علّی را بگوید («چرا» پشت «چرا»).
2. سناریوی دنیای واقعیِ بسیار ملموس — یک موقعیت صنعتی/کارگاهی/بالینیِ مشخص و خاص (نه «یک گارگاه» کلی).
3. نموداری/شکلی — SVG در فیلد "diagram_svg" طبق قوانین بخش گرافیک (نمودار خطی/ستونی/مدار ساده)؛ از بخش‌های متن سؤال حتماً به داده‌های همان نمودار ارجاع دهید.
4. تلهٔ بدفهمی (misconception_trap) — «تحلیل استدلال غلط»: دانش‌آموز فرضی با استناد به یک مثال شهودیِ غلط استدلال می‌کند؛ از دانش‌آموز بخواهید نقطهٔ فروپاشی استدلال را پیدا کند. دقیقاً این بدفهمی را هدف بگیرید: «{misconception}»
5. محاسباتی/رویه‌ای — داده‌های عددی ساده؛ ریاضی پایهٔ اصلی؛ می‌توانید داده‌ها را در یک جدول مارک‌داونِ استاندارد ارائه کنید؛ هم محاسبه و هم «چرا این رابطه را استفاده کردی» را بخواند.
6. تناقض شناختی (Cognitive Conflict) — پدیدهٔ خلاف شهود؛ دانش‌آموز باید بگوید چه اتفاقی می‌افتد و چرا شهود اولیه‌اش غلط بود.
7. تحلیل خطای یک استدلال دیگر — یک پاسخِ نیمه‌کامل و گمراه‌کنندهٔ دانش‌آموز فرضی نشان داده می‌شود؛ دانش‌آموز باید بگوید چه چیزی درست، چه چیزی غلط و چرا.
8. سناریوی واقعی بین‌درسی — پیوند مشخص با درس پایه/ریاضی (مثلاً درصد و تناسب در شیمی، یا نمودار و شیب در فیزیک) در یک موقعیت واقعی.
9. نموداری/شکلی — SVG دوم (کاملاً متفاوت از سؤال ۳)؛ طبق قوانین بخش گرافیک.

قواعد قطعی:
- فقط JSON معتبر برگردانید — هیچ متن توضیحی قبل یا بعد از JSON (حتی یک کلمه) ننویسید. پاسختان باید دقیقاً با «{{» شروع شود و با «}}» پایان یابد.
- همهٔ متن‌ها فارسیِ روان باشند؛ ریاضی/نمادها و لیبل‌های SVG انگلیسی/لاتین مجازند.
- exam_type یکی از این‌هاست: conceptual | real_world | diagram | misconception_trap | computational (هیچ مقدار دیگری مجاز نیست).
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
      "diagram_svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 400 300\" width=\"100%\" height=\"100%\"><line x1=\"40\" y1=\"250\" x2=\"380\" y2=\"250\" stroke=\"black\" stroke-width=\"2\"/><polyline points=\"40,250 120,200 200,150 380,50\" fill=\"none\" stroke=\"black\" stroke-width=\"2\"/><text x=\"300\" y=\"45\" font-size=\"13\">y</text></svg>  (فقط برای سؤال‌های ۳ و ۹، بقیه null)",
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

_FA_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_EN_WORD_RE = re.compile(r"[A-Za-z]{4,}")   # کلمهٔ انگلیسیِ واقعی (فرمول‌ها و نمادهای تک‌حرفی مستثنا)
_LATIN_RUN_RE = re.compile(r"[A-Za-z]+")


_LATEX_BLOCK_RE = re.compile(r"\$\$[\s\S]*?\$\$|\$[^$]*\$|\\[A-Za-z]+(?:\{[^}]*\})?")


def is_persian_text(text) -> bool:
    """آیا متن، فارسی است؟ (فرمول‌های LaTeX مانند $...$ و $$...$$ و نمادهای علمی کوتاه استثنا هستند)"""
    s = str(text or "").strip()
    if not s:
        return False
    # حذف بلوک‌های فرمول LaTeX پیش از بررسی کلمات انگلیسی
    s_no_math = _LATEX_BLOCK_RE.sub(" ", s)
    fa = len(_FA_SCRIPT_RE.findall(s))
    if fa == 0:
        return False
    if _EN_WORD_RE.search(s_no_math):
        return False
    latin = sum(len(m.group(0)) for m in _LATIN_RUN_RE.finditer(s_no_math))
    return latin <= fa


# ══════════════ اعتبارسنجی هندسی SVG ══════════════
_SVG_ATTR_RE = lambda name: re.compile(rf'{name}\s*=\s*"([^"]*)"')


def _svg_attr(tag: str, name: str, default=None):
    m = _SVG_ATTR_RE(name).search(tag)
    return m.group(1) if m else default


def _svg_float(tag: str, name: str, default: float = 0.0) -> float:
    try:
        return float(_svg_attr(tag, name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _dist_point_seg(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = x1 + t * dx, y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _dist_bbox_seg(x0: float, y0: float, x1: float, y1: float, ax: float, ay: float, bx: float, by: float) -> float:
    """فاصلهٔ یک مستطیل (لیبل) تا پاره‌خط — با نمونه‌برداری از نقاطِ داخل/لبهٔ مستطیل."""
    pts = [(ax, ay), (bx, by)]
    for _ in range(40):
        t = _ / 39
        pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    best = float("inf")
    for px, py in pts:
        # نقطهٔ بیرون از مستطیل → فاصلهٔ مستقیم؛ داخل → ۰
        dx = max(x0 - px, 0.0, px - x1)
        dy = max(y0 - py, 0.0, py - y1)
        best = min(best, (dx * dx + dy * dy) ** 0.5)
    return best


def svg_geometry_ok(svg: str) -> bool:
    """قانون عدم هم‌انباشتگی: لیبل‌های <text> باید حداقل ۲۰ پیکسل از هر خط/کادر فاصله داشته باشند.

    - فاصلهٔ bbox هر <text> تا هر <line>/<rect>/<circle>/هر پاره‌خطِ <polyline> باید ≥ ۲۰ باشد.
    - text-anchor / x / y / font-size خوانده می‌شود؛ عرض متن تقریبی محاسبه می‌شود.
    """
    s = svg or ""
    shapes = []  # (kind, geometry)
    for m in re.finditer(r"<line\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        shapes.append(("seg", (_svg_float(t, "x1"), _svg_float(t, "y1"), _svg_float(t, "x2"), _svg_float(t, "y2"))))
    for m in re.finditer(r"<rect\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        x, y = _svg_float(t, "x"), _svg_float(t, "y")
        w, h = _svg_float(t, "width"), _svg_float(t, "height")
        shapes.append(("rect", (x, y, x + w, y + h)))
    for m in re.finditer(r"<circle\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        cx, cy, r = _svg_float(t, "cx"), _svg_float(t, "cy"), _svg_float(t, "r")
        shapes.append(("circle", (cx, cy, r)))
    for m in re.finditer(r"<polyline\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        pts_raw = _svg_attr(t, "points", "") or ""
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", pts_raw)]
        coords = list(zip(nums[::2], nums[1::2]))
        for i in range(len(coords) - 1):
            shapes.append(("seg", (coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])))

    texts = []
    for m in re.finditer(r"<text\b([^>]*)>([^<]*)</text>", s, re.IGNORECASE):
        attrs, content = m.group(1), m.group(2)
        x = _svg_float(attrs, "x")
        y = _svg_float(attrs, "y")
        fs = _svg_float(attrs, "font-size", 14.0)
        anchor = (_svg_attr(attrs, "text-anchor", "start") or "start").lower()
        width = max(1, len(content.strip())) * fs * 0.62
        if anchor == "middle":
            x0 = x - width / 2
        elif anchor == "end":
            x0 = x - width
        else:
            x0 = x
        texts.append((x0, y - fs, x0 + width, y + fs * 0.25))  # bbox تقریبی لیبل

    for (tx0, ty0, tx1, ty1) in texts:
        for kind, geom in shapes:
            if kind == "seg":
                ax, ay, bx, by = geom
                if _dist_bbox_seg(tx0, ty0, tx1, ty1, ax, ay, bx, by) < 20.0:
                    return False
            elif kind == "rect":
                rx0, ry0, rx1, ry1 = geom
                dx = max(rx0 - tx1, tx0 - rx1, 0.0)
                dy = max(ry0 - ty1, ty0 - ry1, 0.0)
                if (dx * dx + dy * dy) ** 0.5 < 20.0:
                    return False
            elif kind == "circle":
                cx, cy, r = geom
                dx = max(tx0 - (cx - r), (cx + r) - tx1, 0.0)
                dy = max(ty0 - (cy - r), (cy + r) - ty1, 0.0)
                inner_hit = tx0 >= (cx - r) and tx1 <= (cx + r) and ty0 >= (cy - r) and ty1 <= (cy + r)
                if inner_hit:
                    return False
                if (dx * dx + dy * dy) ** 0.5 < 20.0:
                    return False
    return True


_CANONICAL_SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
_ALLOWED_SVG_TAGS = {"svg", "rect", "circle", "line", "polyline", "text"}
_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)")
_FENCE_RE = re.compile(r"^```(?:[a-zA-Z]*)\s*|\s*```\s*$", re.MULTILINE)


def _sanitize_diagram_svg(raw) -> str | None:
    """سلامتِ SVGِ مدل را تضمین می‌کند؛ اگر الزامات بخش گرافیک را نداشته باشد، آن را دور می‌ریزد (None).

    قواعد اجباری:
      - فقط تگ‌های svg/rect/circle/line/polyline/text مجازند (path مطلقاً ممنوع).
      - تگ بازشونده با ساختار کانونیکالِ استاندارد جایگزین می‌شود.
      - تگ </svg> باید وجود داشته باشد؛ اسکریپت/هندلرهای on* رد می‌شوند.
    """
    s = raw if isinstance(raw, str) else ""
    s = s.strip()
    if not s:
        return None
    s = _FENCE_RE.sub("", s)  # فنس‌های مارک‌داون را از دور SVG بردار
    start = s.find("<svg")
    end = s.rfind("</svg>")
    if start == -1 or end == -1 or end < start:
        return None  # SVG ناتمام یا خراب
    s = s[start:end + len("</svg>")]
    # حذف عناصر خطرناک/غیرمجازِ جفتی
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<foreignObject[\s\S]*?</foreignObject>", "", s, flags=re.IGNORECASE)
    if re.search(r"\son[a-zA-Z]+\s*=", s):   # هندلرهای رویداد
        return None
    if re.search(r"javascript:", s, flags=re.IGNORECASE):
        return None
    # فقط تگ‌های مجاز — هر تگ دیگر (path, g, ellipse, image, ...) کل SVG را نامعتبر می‌کند
    for m in _TAG_RE.finditer(s):
        if m.group(1).lower() not in _ALLOWED_SVG_TAGS:
            return None
    # نرمال‌سازی تگ بازشونده به ساختار کانونیکال
    s = re.sub(r"<svg[^>]*>", _CANONICAL_SVG_OPEN, s, count=1, flags=re.IGNORECASE)
    # قانون عدم هم‌انباشتگی: لیبل‌ها باید ≥۲۰px از خطوط/کادرها فاصله داشته باشند
    if not svg_geometry_ok(s):
        return None
    return s


_FALLBACK_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                 '<line x1="44" y1="228" x2="372" y2="228" stroke="black" stroke-width="2"/>'
                 '<line x1="44" y1="228" x2="44" y2="40" stroke="black" stroke-width="2"/>'
                 '<rect x="96" y="176" width="36" height="52" fill="none" stroke="black" stroke-width="2"/>'
                 '<rect x="182" y="116" width="36" height="112" fill="none" stroke="black" stroke-width="2"/>'
                 '<rect x="268" y="56" width="36" height="172" fill="none" stroke="black" stroke-width="2"/>'
                 '<text x="114" y="268" font-size="12" text-anchor="middle">A</text>'
                 '<text x="200" y="268" font-size="12" text-anchor="middle">B</text>'
                 '<text x="286" y="268" font-size="12" text-anchor="middle">C</text></svg>')


_FIG_REF_PATTERNS = [
    ("در نمودار زیر", "در این نمودار"),
    ("به نمودار زیر", "به این نمودار"),
    ("در شکل زیر", "در یک شکل مفروض"),
    ("به شکل زیر", "به یک شکل مفروض"),
    ("در مدار زیر", "در یک مدار"),
    ("به مدار زیر", "به یک مدار"),
    ("با توجه به نمودار زیر", "با توجه به این نمودار"),
    ("با توجه به شکل زیر", "با توجه به یک شکل مفروض"),
    ("با توجه به مدار زیر", "با توجه به یک مدار"),
    # عبارت‌های برهنه — بعد از الگوهای بلندتر
    ("نمودار زیر", "این نمودار"),
    ("شکل زیر", "یک شکل مفروض"),
    ("مدار زیر", "یک مدار"),
]


def _replace_missing_figure_refs(text: str) -> str:
    """اگر سؤالی diagram_svg ندارد، هیچ ارجاعی به «شکل/نمودار/مدار زیر» نباید بماند."""
    s = text or ""
    for a, b in _FIG_REF_PATTERNS:
        s = s.replace(a, b)
    return s


def _booklet_items_to_questions(concept, items, model_name: str, cost: float) -> list["Question"]:
    """اعتبارسنجی و ساخت اشیای Question دفترچه."""
    propositions = [_stringify_item(p) for p in (concept.core_propositions or [])]
    propositions = [p for p in propositions if p]
    misconceptions = [_stringify_item(m) for m in (concept.common_misconceptions or [])]
    misconceptions = [m for m in misconceptions if m]
    fallback_prop = propositions[0] if propositions else "گزارهٔ هدف"
    questions = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if len(text) < 15:
            continue  # سؤال بی‌معنی را دور بریز
        if not is_persian_text(text):
            print(f"[Booklet] English/non-Persian question rejected: {text[:80]!r}")
            continue  # صورت سؤال باید ۱۰۰٪ فارسی باشد
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
        order_raw = raw.get("order")
        try:
            order_num = int(order_raw) if order_raw is not None else None
        except (TypeError, ValueError):
            order_num = None
        clean_svg = _sanitize_diagram_svg(raw.get("diagram_svg"))
        # سؤال‌های نموداری (آیتم ۳ و ۹ یا exam_type=diagram) هرگز بدون شکل نمی‌مانند
        if clean_svg is None and ((order_num in (3, 9)) or str(raw.get("exam_type") or "").strip().lower() == "diagram"):
            clean_svg = _FALLBACK_SVG
        diagram_svg = clean_svg
        # اگر نهایتاً شکلی وجود ندارد، هر ارجاع به «شکل/نمودار/مدار زیر» حذف/جایگزین شود
        if diagram_svg is None:
            text = _replace_missing_figure_refs(text)
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
    propositions = [_stringify_item(p) for p in (concept.core_propositions or [])]
    propositions = [p for p in propositions if p]
    misconceptions = [_stringify_item(m) for m in (concept.common_misconceptions or [])]
    misconceptions = [m for m in misconceptions if m]
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
    questions: list[Question] = []
    for attempt in range(3):
        candidate_model = FALLBACK_FREE_MODELS[attempt % len(FALLBACK_FREE_MODELS)] if attempt > 0 else None
        try:
            try:
                resp = await router.generate(
                    prompt, "generate_test_booklet", temperature=0.7, model_override=candidate_model
                )
            except TypeError:
                resp = await router.generate(prompt, "generate_test_booklet", temperature=0.7)
            model_name, cost = resp.model_name, resp.cost_usd
            data = extract_json_object(resp.text)
            items = (data or {}).get("questions") if isinstance(data, dict) else None
            questions = _booklet_items_to_questions(concept, items or [], model_name, cost) if items else []
            if questions:
                break
            print(f"[Booklet] Attempt {attempt + 1}/3 yielded no valid questions; retrying with next model...")
        except Exception as exc:
            print(f"[Booklet] Attempt {attempt + 1}/3 model call failed (model={candidate_model or 'default'}): {exc}")

    if len(questions) < 8:
        # دفترچهٔ اضطراریِ حداقلی — شش پوششِ اساسی به‌ترتیب
        print(f"[Booklet] only {len(questions)} valid questions from model; topping up with deterministic template bank.")
        fallback_prop = (propositions[0] if propositions else "گزارهٔ هدف")
        fallback_mis = (misconceptions[0] if misconceptions else "بدفهمی رایج مفهوم")
        template = [
            ("conceptual", f"یک تکنسین در کارگاه با پدیده‌ای دربارهٔ «{concept.name}» مواجه می‌شود: سیستم را بررسی می‌کند، داده‌ها را ثبت می‌کند و به نتیجهٔ A می‌رسد. شما نتیجهٔ B را درست می‌دانید. نقطهٔ دقیقِ شکستِ استدلالِ A را پیدا کنید و با زنجیرهٔ علّی توضیح دهید چرا اشتباه است.", "hard", "conceptual"),
            ("real_world", f"در یک خطِ تولید/تعمیرات صنعتی، قطعه‌ای که با «{concept.name}» مرتبط است به‌صورت تکرارشونده خراب می‌شود. شرایط (دما، بار، زمان، جنس) را خودتان فرض کنید، سیستم واقعی را توصیف کنید (چه چیزی مشاهده می‌شود، چه چیزی تفسیر است) و بگویید علت ریشه‌ای چیست و چرا.", "hard", "combined"),
            ("misconception_trap", f"هم‌کلاسی‌تان می‌گوید: «{fallback_mis}» — او با یک مثال شهودی استدلالش را تقویت می‌کند. دقیقاً بگویید کجای این استدلال می‌شکند و کدام مثالِ نقض آن را فرومی‌پاشد.", "hard", "conceptual"),
            ("computational", "جدول زیر را برای یک نمونهٔ واقعی بخوانید و مقدار خواسته‌شده را با ذکر تمام مراحل محاسبه کنید؛ سپس بنویسید این رابطه چرا برقرار است:\n| کمیت | مقدار | واحد |\n|---|---|---|\n| V | ۱۲ | ولت |\n| R | ۴ | اهم |", "medium", "computational"),
            ("conceptual", f"پدیده‌ای را تصور کنید که خلافِ انتظارِ روزمرهٔ شما دربارهٔ «{concept.name}» رخ می‌دهد (مثلاً چیزی که همه انتظار دارند افزایش یابد، ثابت می‌ماند). چه اتفاقی می‌افتد؟ و چرا شهود اولیه‌تان اشتباه بود؟", "medium", "conceptual"),
            ("conceptual", "یک پاسخِ نیمه‌کاملِ دانش‌آموز فرضی چنین است: «این اتفاق می‌افتد چون نیرو بیشتر می‌شود.» دقیقاً بگویید چه چیزی در این پاسخ درست است، چه چیزی غلط است، و چرا.", "medium", "conceptual"),
            ("conceptual", f"اگر یک کمیتِ کلیدیِ «{concept.name}» دو برابر شود چه می‌شود؟ پاسخِ «هر دو برابر می‌شوند» را با دلیل رد یا تأیید کنید و حدهای اعتبار این رابطه را بگویید.", "hard", "conceptual"),
            ("real_world", "پیوندی بین این مفهوم و یک مبحث ریاضی (درصد/تناسب/نمودار و شیب) در یک موقعیت واقعی بسازید؛ داده‌ها را فرض کنید و نشان دهید ابزار ریاضی چگونه به این تصمیم فنی کمک می‌کند.", "hard", "combined"),
            ("diagram", "مدار/نمودار داده‌شده (ولتاژ در برابر جریان) را بخوانید: شیب خط چه معنایی دارد؟ اگر مقاومت دو برابر شود خط چه تغییری می‌کند و چرا؟ استدلال خود را بنویسید.", "hard", "conceptual"),
        ]
        have = len(questions)
        for i, (et, text, diff, cog) in enumerate(template):
            if have >= 9:
                break
            diagram_svg = _FALLBACK_SVG if et == "diagram" else None
            questions.append(Question(
                concept_id=concept.id, text=text, question_type=et, difficulty=diff, cognitive_type=cog,
                rubric={"exam_type": et, "diagram_svg": diagram_svg, "correct_reasoning": f"با تکیه بر «{fallback_prop}»",
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
    if not is_persian_text(question_text):
        raise QuestionGenerationError("صورت سؤال تولیدی فارسی نیست — خروجی رد شد")

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

    for attempt in range(3):
        temp = 0.8 if attempt == 0 else 0.3
        extra = "" if attempt == 0 else "\n\nخروجی قبلی نامعتبر بود. فقط و فقط JSON خالص با بک‌اسلش‌های دوتایی (\\\\) برای LaTeX بده."
        candidate_model = FALLBACK_FREE_MODELS[attempt % len(FALLBACK_FREE_MODELS)] if attempt > 0 else None
        try:
            try:
                resp = await router.generate(
                    prompt + extra, "generate_question", temperature=temp, model_override=candidate_model
                )
            except TypeError:
                resp = await router.generate(prompt + extra, "generate_question", temperature=temp)
            model_name, cost = resp.model_name, resp.cost_usd
            data = _extract_json(resp.text)
            if data is not None:
                break
            last_error = "JSON استخراج نشد"
            print(f"[DiagnosticQuestion] Attempt {attempt + 1}/3 invalid JSON; retrying with next model...")
        except AIProviderError as exc:
            last_error = str(exc)
            print(f"[DiagnosticQuestion] Attempt {attempt + 1}/3 provider error: {exc}; retrying...")
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
