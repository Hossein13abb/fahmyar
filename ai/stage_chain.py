"""تولیدِ «زنجیرهٔ ۵ مرحله‌ای» آزمون فهم‌سنجی — از کل به جزء و دوباره به کل.

جایگزینِ کاملِ دفترچهٔ ۹ سؤالی. تفاوتِ بنیادی: این آزمون *یک زنجیره* است،
نه پنج سؤالِ مستقل. هر مرحله لایهٔ متفاوتی از ذهن را می‌سنجد و مرحلهٔ بعد
بدونِ مرحلهٔ قبل معنا ندارد — مخصوصاً سؤال ۵ که باید حرفِ سؤال ۲ را نقض کند
یا تأیید و بدونِ آن قابلِ تفسیر نیست.

**قانونِ فرمت‌بندی:** هرگز از `.format()` روی متنِ پرامپت استفاده نکنید.
متنِ پرامپت آکولادِ LaTeX دارد (`\\frac{4}{9}`، `\\cos^{-1}`) و `.format`
آن‌ها را فیلدِ جای‌گذاری می‌بیند و `KeyError: '-1'` می‌دهد. از
`ai.prompt_safe.fill` استفاده کنید.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ai.json_sanitize import extract_json_object
from ai.model_abstraction import get_router
from ai.prompt_safe import fill

#: ترتیبِ اجباریِ پنج مرحله — همان‌جا که سؤال ساخته می‌شود هم استفاده می‌شود.
STAGE_ORDER: tuple[str, ...] = (
    "philosophy",
    "mask_mcq",
    "perturbation",
    "debugging",
    "feynman_synthesis",
)

STAGE_TITLES: dict[str, str] = {
    "philosophy": "مرحله ۱: فلسفه و تصویر کلان",
    "mask_mcq": "مرحله ۲: تست لایه نقاب (با اطلاعات انحرافی)",
    "perturbation": "مرحله ۳: مونتاژ ذهنی و دستکاری سیستم",
    "debugging": "مرحله ۴: عیب‌یابی ساعت خراب (نقد استدلال)",
    "feynman_synthesis": "مرحله ۵: چالش فاینمن (توضیح با دستِ بسته!)",
}


# ---------------------------------------------------------------------------
# قالبِ پرامپت
# ---------------------------------------------------------------------------
_BOOKLET_PROMPT = r"""CRITICAL MATH FORMATTING RULE:
Every mathematical symbol, formula, vector, power or inverse function MUST be enclosed in inline math `$ ... $`.
Examples of CORRECT formatting:
- Inverse trig / functions: `$\cos^{-1}\left(\frac{4}{9}\right)$` (NOT `cos^-1(4/9)`)
- Powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)
- Vectors: `$\vec{n}_1 = (1, 2, 2)$`
Never output raw LaTeX commands outside `$ ... $`.
Even inside LaTeX blocks, use Persian numbers (۰۱۲۳۴۵۶۷۸۹): `$۲x + ۵ = ۱۲$`.
CRITICAL JSON ESCAPING RULE: double-escape all LaTeX in the JSON (`\\frac`, `\\sqrt`, `\\theta`, `\\vec`). Never escape the `$` delimiter.

CRITICAL SYLLABUS RULE (نظام جدید ۱۳۹۷ به بعد):
Only generate questions compliant with Iranian high-school textbooks published after 1397.
FORBIDDEN: integrals in حسابان ۲, general equations of ellipse/hyperbola, 3x3 matrix inverses, obsolete pre-1397 physics topics.

═══════════════════════════════════════════════════════════════
شما «طراحِ ارشدِ آزمونِ فهم‌سنجی شناختی» هستید. برای مفهوم «{concept}»
({subject} — پایه {grade}) **یک زنجیرهٔ ۵ مرحله‌ایِ به‌هم‌پیوسته** بسازید.

این آزمون ۹ سؤال مستقل نیست. **پنج مرحله است که هر کدام لایهٔ متفاوتی از
ذهن را می‌سنجد** و مرحلهٔ بعد بدون مرحلهٔ قبل معنا ندارد.
═══════════════════════════════════════════════════════════════

🔹 مرحله ۱ — «فلسفه و تصویر کلان» (exam_type: "philosophy")
   تشریحیِ کوتاه، **مطلقاً بدونِ هیچ فرمول و عدد**.
   یا دربارهٔ فلسفهٔ پیدایشِ مفهوم (دانشمندان به چه بن‌بستی خوردند و این
   مفهوم را ساختند؟) یا مکانیزمِ بنیادیِ پدیده در طبیعت — دیدنِ «کلِ ساعت»
   پیش از «چرخ‌دنده‌ها». هدف: شناساییِ کسانی که مفهومِ پایه را نمی‌دانند و
   با کلماتِ قلمبه‌سلمبه بلوف می‌زنند.

🔹 مرحله ۲ — «تست لایهٔ نقاب» (exam_type: "mask_mcq")
   **تستیِ ۴ گزینه‌ای.** فیلدهای لازم: "options" (آرایهٔ ۴ رشته) و
   "correct_option_index" (عددِ ۰ تا ۳).
   یک تستِ استانداردِ کتابی دربارهٔ قانونِ اصلی — اما **حتماً در صورتِ
   سؤال یک دادهٔ عددیِ انحرافی و بی‌ربط («چرخ‌دندهٔ اضافه») قرار بده** که در
   فرمول و جوابِ نهایی هیچ تأثیری ندارد (مثلاً دادنِ حجم و مساحتِ ظرف در
   سؤالی که فقط به ارتفاعِ مایع بستگی دارد). هدف: ثبتِ اینکه قانونِ رسمی
   را می‌داند یا نه، تا در مرحله ۵ با شهودش مقایسه شود.

🔹 مرحله ۳ — «مونتاژ ذهنی و دستکاری سیستم» (exam_type: "perturbation")
   تشریحیِ تحلیلی و **مطلقاً بدونِ عدد**.
   یک سناریوی پویا که در آن یکی از متغیرهای سیستم دستکاری می‌شود (یا کلِ
   سیستم به محیطِ تازه‌ای مثل ماه منتقل می‌شود) و دانش‌آموز باید زنجیرهٔ
   تغییراتِ سایر اجزا را پیش‌بینی و استدلال کند.

🔹 مرحله ۴ — «عیب‌یابی ساعت خراب» (exam_type: "debugging")
   **شاه‌کلیدِ تشخیص.** یک دانش‌آموزِ فرضی (امیر یا سارا) استدلالی مطرح
   می‌کند که ظاهرش بسیار منطقی و علمی است اما نتیجه‌اش غلط. این استدلال
   باید بر پایهٔ این بدفهمیِ رایج ساخته شود: «{misconception}»
   از دانش‌آموز بپرس: «استدلالِ او دقیقاً در کدام نقطه می‌شکند و سوتیِ
   منطقی‌اش کجاست؟» نامِ دانش‌آموزِ فرضی و یک نقلِ‌قولِ مستقیم از او در متن بیاور.

🔹 مرحله ۵ — «چالش فاینمن» (exam_type: "feynman_synthesis")
   از دانش‌آموز بخواه یک پدیدهٔ واقعی و ملموس مرتبط با همین مفهوم (مرتبط با
   منطقِ سؤال مرحله ۲) را برای یک **بچهٔ ۱۰ ساله** توضیح دهد.
   **قانونِ حیاتی:** فیلد "forbidden_words" باید آرایه‌ای از **۴ تا ۶** کلمهٔ
   تخصصی و فرمولیِ همین مبحث باشد که دانش‌آموز حق ندارد در پاسخش به کار ببرد.
   (نمونه — فشار: ["فرمول", "چگالی", "ارتفاع", "جاذبه"]؛ مشتق: ["شیب", "حد",
   "خط مماس", "فرمول"]). هدف: خلعِ سلاحِ حافظهٔ طوطی‌وار تا ببینیم آیا حرفِ
   درستِ خودش در مرحله ۲ را نقض می‌کند یا نه.

───────────────────────────────────────────────────────────────
قواعدِ قطعیِ خروجی
───────────────────────────────────────────────────────────────
۱. فقط JSON معتبر برگردانید — هیچ متنِ توضیحی قبل یا بعد از آن، حتی یک کلمه.
۲. تمام متن‌ها ۱۰۰٪ فارسیِ روان. اصطلاحاتِ ریاضی را ترجمه یا آوانویسی نکنید
   («فنکشن» و «مشduc» ممنوع)؛ از نمادِ LaTeX استفاده کنید.
۳. سؤال‌های ۱ و ۳ و ۴ و ۵ هیچ‌کدام نباید "options" داشته باشند (مقدار null).
۴. برای هر سؤال فیلد "expected_logic" را پر کنید: هستهٔ استدلالی که پاسخِ
   درست باید به آن اشاره کند. این فیلد فقط برای ارزیاب استفاده می‌شود و به
   دانش‌آموز نشان داده نمی‌شود.
۵. شماره‌گذاری order از ۱ تا ۵ و exam_type دقیقاً مطابقِ بالا.

ساختارِ خروجی:
{
  "concept_blueprint": {
    "core_mechanism": "منطقِ اصلیِ مبحث در دو خط",
    "target_misconceptions": ["بدفهمی ۱", "بدفهمی ۲"]
  },
  "questions": [
    {"order": 1, "exam_type": "philosophy", "stage_title": "مرحله ۱: فلسفه و تصویر کلان",
     "text": "...", "difficulty": "medium", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 2, "exam_type": "mask_mcq", "stage_title": "مرحله ۲: تست لایه نقاب (با اطلاعات انحرافی)",
     "text": "...", "difficulty": "medium", "cognitive_type": "conceptual",
     "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"], "correct_option_index": 1,
     "forbidden_words": [], "expected_logic": "...", "mapped_propositions": []},

    {"order": 3, "exam_type": "perturbation", "stage_title": "مرحله ۳: مونتاژ ذهنی و دستکاری سیستم",
     "text": "...", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 4, "exam_type": "debugging", "stage_title": "مرحله ۴: عیب‌یابی ساعت خراب (نقد استدلال)",
     "text": "...", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 5, "exam_type": "feynman_synthesis", "stage_title": "مرحله ۵: چالش فاینمن (توضیح با دستِ بسته!)",
     "text": "...", "difficulty": "hard", "cognitive_type": "combined",
     "options": null, "correct_option_index": null,
     "forbidden_words": ["کلمه ۱", "کلمه ۲", "کلمه ۳", "کلمه ۴"],
     "expected_logic": "...", "mapped_propositions": []}
  ]
}

<<<CONCEPT>>>{concept}<<<END>>>
<<<PROPOSITION>>>{proposition}<<<END>>>
<<<MISCONCEPTION>>>{misconception}<<<END>>>
<<<WRONG_ANSWER>>>{wrong_answer}<<<END>>>
"""

#: پنج سؤالِ اضطراری — اگر مدل در سه تلاش نتوانست بسازد.
#: عمداً برای هر مرحله یک متنِ کامل وجود دارد تا آزمونِ ناقص به دانش‌آموز نرسد.
_FALLBACK_STAGES: tuple[dict[str, Any], ...] = (
    {
        "order": 1,
        "exam_type": "philosophy",
        "text": (
            "بدونِ هیچ فرمول و عددی توضیح بده: چرا برای توصیفِ «{concept}» "
            "به یک مفهومِ تازه نیاز پیدا کردیم؟ انسان‌ها پیش از این مفهوم "
            "به چه بن‌بستی می‌خوردند؟ اگر بخواهی در یک جملهٔ ساده بگویی این "
            "مفهوم چه کارِ واقعی‌ای در دنیا انجام می‌دهد، چه می‌گویی؟"
        ),
        "difficulty": "medium",
        "cognitive_type": "conceptual",
    },
    {
        "order": 2,
        "exam_type": "mask_mcq",
        "text": (
            "یک دانش‌آموز می‌خواهد دربارهٔ «{concept}» تصمیم بگیرد. "
            "در صورتِ مسئله سه داده آمده است: یکی از آن‌ها متغیرِ مؤثر است و "
            "دو دادهٔ دیگر (شاملِ یک عددِ بزرگ و چشمگیر) هیچ نقشی در نتیجه "
            "ندارند و فقط برای گمراه کردن آمده‌اند. کدام گزاره دربارهٔ «{concept}» "
            "درست است؟"
        ),
        "difficulty": "medium",
        "cognitive_type": "conceptual",
        "options": [
            "گزارهٔ استانداردِ کتاب‌درسی درست است و همان متغیرِ اصلی تعیین‌کننده است؛ داده‌های اضافی بی‌تأثیرند.",
            "با بزرگ‌تر شدنِ مقدارِ دادهٔ اضافی، نتیجه هم به همان نسبت بزرگ‌تر می‌شود.",
            "هیچ‌کدام از متغیرها به‌تنهایی تعیین‌کننده نیست و باید میانگین گرفت.",
            "نمی‌توان گفت؛ چون داده‌های اضافی با هم در تضادند.",
        ],
        "correct_option_index": 0,
    },
    {
        "order": 3,
        "exam_type": "perturbation",
        "text": (
            "بدونِ هیچ عددی: فرض کن سیستمِ «{concept}» را از محیطِ همیشگی‌اش "
            "برمی‌داریم و در محیطی با شرایط متفاوت (مثلاً گرانشِ ضعیف‌تر یا "
            "دمای بالاتر) قرار می‌دهیم. زنجیرهٔ تغییرات را پیش‌بینی کن: اول چه "
            "چیزی عوض می‌شود؟ بعدش چه اتفاقی می‌افتد؟ و در نهایت خروجیِ نهایی "
            "چه تغییری می‌کند و چرا؟"
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
    },
    {
        "order": 4,
        "exam_type": "debugging",
        "text": (
            "امیر می‌گوید: «طبقِ آنچه در کلاس خواندیم، دربارهٔ «{concept}» "
            "قطعاً این‌طور باید باشد و این با تجربهٔ روزمره‌ام هم جور است.» "
            "او یک استدلالِ سه‌مرحله‌ای می‌آورد که هر مرحله‌اش به‌تنهایی درست "
            "به نظر می‌رسد. سوتیِ منطقیِ استدلالِ امیر دقیقاً کجاست؟ یک جمله‌ای "
            "از او را داخلِ گیومه نقل کن و بگو چرا آن جمله می‌لنگد."
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
    },
    {
        "order": 5,
        "exam_type": "feynman_synthesis",
        "text": (
            "این پدیده را برای یک بچهٔ ۱۰ ساله توضیح بده: «{concept}» در زندگیِ "
            "روزمره چطور اثر می‌گذارد و چرا؟ توضیحت باید طوری باشد که بچه خودش "
            "بتواند آن را برای دوستش تعریف کند — بدونِ اینکه چیزی را حفظ کرده باشد."
        ),
        "difficulty": "hard",
        "cognitive_type": "combined",
        "forbidden_words": ["فرمول", "قانون", "تعریف", "اصطلاح"],
    },
)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def build_booklet_prompt(
    concept,
    propositions: list[str],
    misconceptions: list[str],
    wrong_answer: dict | None = None,
) -> str:
    """پرامپتِ نهایی — با `fill`، نه `.format`."""
    wrong_text = ""
    if wrong_answer:
        wrong_text = (
            f"مسئله: {wrong_answer.get('problem_text', '')} | "
            f"پاسخِ غلطِ دانش‌آموز: {wrong_answer.get('student_answer', '')}"
        )
    return fill(
        _BOOKLET_PROMPT,
        concept=concept.name,
        subject=concept.subject,
        grade=concept.grade,
        proposition=propositions[0] if propositions else "گزارهٔ هدف",
        misconception=misconceptions[0] if misconceptions else "بدفهمیِ رایجِ این مفهوم",
        wrong_answer=wrong_text or "—",
    )


# ---------------------------------------------------------------------------
# نرمال‌سازیِ خروجیِ مدل
# ---------------------------------------------------------------------------
def _coerce_options(raw: Any) -> Optional[list[str]]:
    if not isinstance(raw, list):
        return None
    options = [str(x).strip() for x in raw if str(x).strip()]
    return options if len(options) >= 2 else None


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _coerce_index(raw: Any, options_count: int, *, one_based: bool = False) -> int:
    """اندیسِ گزینه را ۰-پایه و در محدودهٔ معتبر برمی‌گرداند.

    ``one_based=True`` یعنی سؤال صریحاً گفته «۱ تا ۴» — پس ۱ ⇒ اندیس ۰.
    بدونِ این پرچم، ۱ در بازهٔ ۰..۳ هم معتبر است و مبهم می‌ماند؛ تصمیمِ
    محافظه‌کارانه: مقدار را همان‌طور که آمده بپذیر.
    """
    text = str(raw).strip().translate(_DIGITS)
    try:
        value = int(text)
    except (TypeError, ValueError):
        return 0
    if one_based:
        value -= 1
    if 0 <= value < options_count:
        return value
    if value == options_count:  # مدل یک‌پایه داده (۴ برای چهار گزینه)
        return options_count - 1
    return 0


_WORD_SPLIT = re.compile(r"[,،;؛|\n]")


def _coerce_forbidden(raw: Any) -> list[str]:
    """کلماتِ ممنوعه — هم لیست، هم رشتهٔ جداشده با ویرگول را می‌پذیرد."""
    if isinstance(raw, str):
        raw = [p for p in _WORD_SPLIT.split(raw)]
    if not isinstance(raw, (list, tuple)):
        return []
    words: list[str] = []
    for item in raw:
        word = _stringify(item)
        if word and word not in words:
            words.append(word)
    return words


def normalize_stage_items(items: Any) -> list[dict[str, Any]]:
    """خروجیِ خامِ مدل را به پنج مرحلهٔ قطعی تبدیل می‌کند.

    مقاوم در برابرِ انحراف‌های رایج: بی‌ترتیبی، type اشتباه، گزینهٔ کم،
    ایندکسِ یک‌پایه، forbidden_words غایب.
    """
    if isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list):
        return []

    slots: list[Optional[dict]] = [None] * len(STAGE_ORDER)
    spare: list[dict] = []

    for position, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        exam_type = _stringify(raw.get("exam_type") or raw.get("type")).lower()
        order = raw.get("order")
        try:
            order_num = int(order) if order is not None else position + 1
        except (TypeError, ValueError):
            order_num = position + 1

        slot: Optional[int] = None
        if exam_type in STAGE_ORDER:
            slot = STAGE_ORDER.index(exam_type)
        elif 1 <= order_num <= len(STAGE_ORDER):
            slot = order_num - 1

        if slot is not None and slots[slot] is None:
            slots[slot] = raw
        elif exam_type not in STAGE_ORDER:
            # آیتمِ بی‌نوع یا با ترتیبِ نامعتبر: تنها جایی که می‌تواند بنشیند
            spare.append(raw)
        # تکرارِ یک مرحلهٔ موجود (مثلاً دو MCQ) دور ریخته می‌شود؛ نباید
        # جای مرحلهٔ دیگری را بگیرد و برچسبِ اشتباه بخورد.

    for slot, value in enumerate(slots):
        if value is None and spare:
            slots[slot] = spare.pop(0)

    normalized: list[dict[str, Any]] = []
    for index, exam_type in enumerate(STAGE_ORDER):
        raw = slots[index]
        if not isinstance(raw, dict):
            continue
        text = _stringify(raw.get("text") or raw.get("question_text"))
        if not text:
            continue

        item: dict[str, Any] = {
            "order": index + 1,
            "exam_type": exam_type,
            "stage_title": _stringify(raw.get("stage_title")) or STAGE_TITLES[exam_type],
            "text": text,
            "difficulty": _stringify(raw.get("difficulty")).lower() or "medium",
            "cognitive_type": _stringify(raw.get("cognitive_type")).lower() or "conceptual",
            "options": None,
            "correct_option_index": None,
            "forbidden_words": _coerce_forbidden(raw.get("forbidden_words")),
            "expected_logic": _stringify(raw.get("expected_logic")),
            "mapped_propositions": [
                p for p in (raw.get("mapped_propositions") or []) if isinstance(p, str) and p.strip()
            ],
        }
        if item["difficulty"] not in {"easy", "medium", "hard"}:
            item["difficulty"] = "medium"
        if item["cognitive_type"] not in {"recall", "conceptual", "computational", "combined"}:
            item["cognitive_type"] = "conceptual"

        if exam_type == "mask_mcq":
            options = _coerce_options(raw.get("options"))
            if options:
                item["options"] = options[:4]
                # پرامپت صریحاً «۱ تا ۴» می‌خواهد ⇒ ایندکسِ مدل یک‌پایه است.
                item["correct_option_index"] = _coerce_index(
                    raw.get("correct_option_index"), len(item["options"]), one_based=True
                )
        elif exam_type == "feynman_synthesis" and len(item["forbidden_words"]) < 3:
            item["forbidden_words"] = ["فرمول", "قانون", "تعریف", "اصطلاح"]

        normalized.append(item)

    return normalized


def fallback_stages(concept) -> list[dict[str, Any]]:
    """پنج مرحلهٔ اضطراریِ کامل — هرگز آزمونِ ناقص به دانش‌آموز نمی‌رسد."""
    out: list[dict[str, Any]] = []
    for template in _FALLBACK_STAGES:
        item = dict(template)
        item["text"] = fill(item["text"], concept=concept.name)
        item["stage_title"] = STAGE_TITLES[item["exam_type"]]
        item.setdefault("options", None)
        item.setdefault("correct_option_index", None)
        item.setdefault("forbidden_words", [])
        item.setdefault("expected_logic", "")
        item.setdefault("mapped_propositions", [])
        out.append(item)
    return out


def items_to_questions(concept, items: list[dict[str, Any]], model_name: str, cost: float) -> list:
    """آیتم‌های پنج‌گانه را به ردیف‌های ``Question`` تبدیل می‌کند.

    اطلاعاتِ اختصاصیِ هر مرحله داخلِ ستونِ JSONِ ``rubric`` می‌رود تا نیازی
    به تغییرِ ستون‌های جدول نباشد.
    """
    from ai.question_generator import _sanitize_diagram_svg
    from models.question import Question

    propositions = [_stringify(p) for p in (getattr(concept, "core_propositions", None) or [])]
    propositions = [p for p in propositions if p]
    fallback_prop = propositions[0] if propositions else "گزارهٔ هدف"

    rows: list[Question] = []
    for item in items:
        exam_type = item["exam_type"]
        text = item["text"]
        diagram_svg = _sanitize_diagram_svg(item.get("diagram_svg"))
        mapped = item.get("mapped_propositions") or [fallback_prop]

        rubric = {
            "exam_type": exam_type,
            "stage_title": item.get("stage_title") or STAGE_TITLES[exam_type],
            "options": item.get("options") if exam_type == "mask_mcq" else None,
            "correct_option_index": item.get("correct_option_index") if exam_type == "mask_mcq" else None,
            "forbidden_words": item.get("forbidden_words") or [],
            "expected_logic": item.get("expected_logic") or "",
            "diagram_svg": diagram_svg,
        }
        rows.append(
            Question(
                concept_id=getattr(concept, "id", None),
                text=text,
                question_type=exam_type,
                difficulty=item.get("difficulty") or "medium",
                cognitive_type=item.get("cognitive_type") or "conceptual",
                rubric=rubric,
                mapped_propositions=mapped,
                mapped_misconceptions=[],
                source="ai_generated",
                approval_status="pending",
                ai_model_used=model_name,
                generation_cost_usd=cost,
            )
        )
    return rows


async def generate_stage_chain(
    concept, wrong_answer: dict | None = None
) -> tuple[list[Any], str, float]:
    """زنجیرهٔ ۵ مرحله‌ای را تولید می‌کند.

    سه تلاش با مدل‌های متفاوت؛ اگر هیچ‌کدام پنج مرحلهٔ کامل نداد،
    زنجیرهٔ اضطراریِ قطعی برمی‌گردد. آزمونِ ناقص هرگز تحویل نمی‌شود.
    """
    propositions = [_stringify(p) for p in (getattr(concept, "core_propositions", None) or [])]
    propositions = [p for p in propositions if p]
    misconceptions = [_stringify(m) for m in (getattr(concept, "common_misconceptions", None) or [])]
    misconceptions = [m for m in misconceptions if m]

    prompt = build_booklet_prompt(concept, propositions, misconceptions, wrong_answer)
    router = get_router()

    model_name, cost = "", 0.0
    best_items: list[dict[str, Any]] = []

    for attempt in range(3):
        try:
            resp = await router.generate(prompt, "generate_test_booklet", temperature=0.7)
            model_name, cost = resp.model_name, resp.cost_usd
            data = extract_json_object(resp.text)
            items = normalize_stage_items((data or {}).get("questions") if isinstance(data, dict) else None)
            if len(items) >= 4 and any(i["exam_type"] == "mask_mcq" and i["options"] for i in items):
                if len(items) > len(best_items):
                    best_items = items
                if len(items) == 5:
                    break
            print(
                f"[StageChain] attempt {attempt + 1}/3 gave {len(items)} usable stages "
                f"(model={resp.model_name})"
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            print(f"[StageChain] attempt {attempt + 1}/3 failed: {message[:200]}")
            # ۴۲۹ یعنی همهٔ مدل‌های رایگان الان سیر شده‌اند. تلاشِ بعدی و بعدتر
            # فقط کاربر را معطل می‌کند و هیچ‌وقت به سؤال نمی‌رسد. همان جا قطع کن
            # و زنجیرهٔ اضطراری بده.
            if "429" in message or "rate-limited" in message:
                print("[StageChain] upstream rate limit — going straight to the deterministic chain")
                break

    if len(best_items) < 5:
        # هر مرحلهٔ موجود را نگه دار، جای خالی را با قالبِ اضطراری پر کن
        fallback = fallback_stages(concept)
        by_type = {i["exam_type"]: i for i in best_items}
        merged = [by_type.get(t) or fallback[STAGE_ORDER.index(t)] for t in STAGE_ORDER]
        print("[StageChain] completed missing stages from the deterministic template bank")
        best_items = merged
        model_name = model_name or "template-fallback"

    return items_to_questions(concept, best_items, model_name or "mixed", cost), model_name or "mixed", cost
