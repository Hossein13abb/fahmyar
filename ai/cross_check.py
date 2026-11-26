"""موتور تحلیلِ مقایسه‌ای (Cross-Checking) برای زنجیرهٔ ۵ مرحله‌ای.

**تفاوتِ بنیادی با تحلیلگرِ قدیمی:** تحلیلگرِ قدیمی هر سؤال را جدا نمره
می‌داد و پاسخ‌ها را جمع می‌زد. این ماژول هرگز سؤال را تنها نمی‌بیند؛ پاسخِ
مرحله ۲ را با مرحله ۵، و پاسخِ تشریحی را با انتخابِ تستی مقایسه می‌کند تا
تناقض‌های ذهن را شکار کند.

پنج قانون:

1. **تضادِ نقاب و شهود** (۲ در برابر ۵): تست را درست زد، ولی وقتی کلماتِ
   تخصصی را گرفتیم حرفِ خودش را نقض کرد ⇒ توهمِ دانایی.
2. **نقضِ کلماتِ ممنوعه** (۵): با کد و با مدل هر دو بررسی می‌شود.
3. **ضدِ بلوف** (۱): قلمبه‌سلمبه‌گویی به‌جای اشاره به علتِ ریشه‌ای.
4. **حاکمیتِ عیب‌یابی** (۳ و ۴): اگر این دو درست بود، حکمِ «نفهمیده» نادرست است.
5. **بی‌دقتی در برابرِ بدفهمی** (♦): تشریحیِ درست + تستِ متضاد ⇒ بازپرسی.

قواعد در کد هم اجرا می‌شوند، نه فقط در پرامپت: مدل می‌تواند تناقضی را که
دیده نادیده بگیرد، یا تناقضی بسازد که در داده نیست.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ai.json_sanitize import extract_json_object
from ai.model_abstraction import get_router
from ai.stage_chain import (
    QUESTIONS_PER_STAGE,
    STAGE_TITLES_FA,
    TOTAL_QUESTIONS,
    stage_key,
    stage_of_order,
)
from ai.prompt_safe import fill

# ---------------------------------------------------------------------------
# قالبِ پرامپت — بدونِ .format()
# ---------------------------------------------------------------------------
_EXAM_PROMPT = r"""شما «کارآگاهِ علوم شناختیِ فهم‌یار» هستید.
وظیفهٔ شما تصحیحِ تک‌به‌تکِ سؤالات مثل یک معلمِ سنتی نیست.
وظیفهٔ شما **مقایسهٔ پاسخ‌های دانش‌آموز با یکدیگر (Cross-Checking)** و کشفِ تناقض‌های پنهان در ذهنِ اوست.

این آزمون یک «زنجیرهٔ ۵ مرحله‌ای با **۱۰ سؤال**» است — هر مرحله دو سؤال
دارد و سؤال‌ها مستقل نیستند:
  مرحله ۱ (philosophy، سؤال ۱ و ۲):       فلسفهٔ وجودی و تصویرِ کلان
  مرحله ۲ (mask_mcq، سؤال ۳ و ۴):         دو تستِ استاندارد با دادهٔ انحرافی
  مرحله ۳ (perturbation، سؤال ۵ و ۶):     مونتاژِ ذهنی و دستکاریِ سیستم
  مرحله ۴ (debugging، سؤال ۷ و ۸):        نقدِ دو استدلالِ غلط — شاه‌کلید
  مرحله ۵ (feynman_synthesis، سؤال ۹ و ۱۰): توضیحِ ساده با کلماتِ ممنوعهٔ جدا

⚠️ **داوری در سطحِ سؤال، جمع‌بندی در سطحِ مرحله.** برای **هر ده سؤال** جداگانه
در ``per_question`` رکورد بده (order از ۱ تا ۱۰). کد خودش دو سؤالِ هر مرحله را
تلفیق می‌کند؛ تو فقط صادقانه وضعیتِ هر سؤال را بگو.

══════ قواعدِ قضاوت ══════

قانون ۱ — شکارِ تضادِ نقاب و شهود (مرحله ۲ در برابر مرحله ۵):
  اگر دانش‌آموز در تستِ مرحله ۲ گزینهٔ درست را زد، اما در مرحله ۵ وقتی
  کلماتِ تخصصی را از او گرفتیم به شهودِ غلطِ اولیه‌اش برگشت و حرفِ خودش را
  نقض کرد (مثلاً در تست گفت حجم مهم نیست، در مرحله ۵ گفت چون حجم بیشتره)
  ⇒ یافتهٔ CONTRADICTION با عنوانی دربارهٔ «توهمِ دانایی».

قانون ۲ — نقضِ کلماتِ ممنوعه (مرحله ۵):
  اگر از فهرستِ forbidden_words استفاده کرد ⇒ یافتهٔ JARGON_VIOLATION.
  یعنی فهمش در زندانِ ادبیاتِ کتاب حبس شده و بدونِ اصطلاح نمی‌تواند توضیح دهد.

قانون ۳ — فیلترِ ضدِ بلوف (مرحله ۱):
  گولِ کلماتِ قلمبه‌سلمبه را نخور. اگر به‌جای اشاره به علتِ ریشه‌ای
  (expected_logic) آسمان و ریسمان به هم بافته ⇒ یافتهٔ BLUFF_DETECTED.

قانون ۴ — حاکمیتِ عیب‌یابی (مرحله ۳ و ۴):
  این دو بالاترین وزنِ شناختی را دارند، **به شرطِ درستیِ محتوایی**.
  MASTERED فقط وقتی مجاز است که:
    (الف) مرحله ۳ زنجیرهٔ علّی را درست و کامل گفته باشد (نه فقط نتیجهٔ نهایی)،
    (ب) مرحله ۴ هستهٔ نقد را دقیقاً زده باشد — یعنی گفته باشد استدلالِ غلط
        *کجا* و *چرا* می‌شکند، نه اینکه فقط بگوید «نتیجه غلط است».
  اگر مرحله ۴ نیمه‌درست است (مثلاً فقط گفته «حاصل‌ضرب عوض می‌شود» ولی
  توضیح نداده چرا مقاومت خودش را تنظیم نمی‌کند) ⇒ MASTERED **ممنوع**؛
  حکمِ حداکثر PARTIAL_FRAGMENTED یا ILLUSION_OF_COMPETENCE است.
  ⚠️ طولِ پاسخ یا تعدادِ کلمات هرگز شاهدِ درستی نیست. پاسخِ بلند و
  نیمه‌درست، از پاسخِ کوتاه و درست ضعیف‌تر است. پاسخِ بلندِ بی‌ربط، صفر است.
  استثنای حفظ‌شده: اگر Q3 و Q4 واقعاً درست بودند و ضعف فقط در بیانِ
  Q1/Q5 بود، دانش‌آموز را رد نکن — بگو «مفهوم را عمیقاً بلدی، فقط در
  انتقالِ ساده کمی بی‌حوصلگی». ولی «واقعاً درست» باید در شواهد دیده شود.

قانون ۵ — تشخیصِ بی‌دقتی در برابرِ بدفهمی (ایستگاهِ بازپرسی):
  اگر در یک سؤالِ تشریحی (۱، ۳ یا ۴) مفهومی را کاملاً درست توضیح داد، اما
  در تستِ مرحله ۲ گزینه‌ای را انتخاب کرد که مستقیماً با توضیحِ خودش در تضاد
  است (یا برعکس) — فوراً حکم نده!
  ⚠️ بازپرسی فقط برای **تناقضِ محتواییِ واقعی** است. تفاوتِ لحن، کوتاهیِ
  پاسخ، یا ساده‌تر نوشتنِ همان حرف، تناقض نیست و نباید جلسه را معلق کند.
  needs_clarification را true کن و در mirror_prompt دو حرفِ متناقضِ خودِ
  او را مثل آینه کنار هم بگذار و با لحنی صمیمی و تیزبینانه بپرس:
  «یه لحظه صبر کن! تو در سؤالِ [X] خیلی قشنگ گفتی [...]، اما در سؤالِ [Y]
   زدی [...]! این دو تا حرفت با هم تناقض داره. توی تست بی‌دقتی کردی و دستت
   خورد، یا واقعاً فکر می‌کنی...؟»

══════ لحن ══════
هوشمندانه، خودمانی، محترمانه و دقیق — طوری که دانش‌آموز حس کند ذهنش خوانده
شده. هرگز تحقیر یا نمره/درصد/رتبه.

══════ خروجی ══════
فقط JSON معتبر؛ هیچ متنِ توضیحی قبل یا بعد. ساختار:

{
  "needs_clarification": false,
  "clarification_data": {"contradicting_questions": [1, 2], "mirror_prompt": "..."},
  "mastery_status": "MASTERED | ILLUSION_OF_COMPETENCE | JARGON_DEPENDENT | PARTIAL_FRAGMENTED | UNSTRUCTURED",
  "persona_title": "عنوانِ جذابِ وضعیتِ ذهنی",
  "executive_summary": "خلاصهٔ کارآگاهی و صمیمی، ۲ تا ۳ جمله",
  "cross_check_findings": [
    {"title": "...", "type": "CONTRADICTION | SYNERGY | JARGON_VIOLATION | BLUFF_DETECTED | SLIP_RESOLVED", "description": "..."}
  ],
  "per_question": [
    {"question_id": 1, "order": 1, "stage_title": "...",
     "status": "correct | partial | incorrect | insufficient",
     "evidence_quote": "بریدهٔ عیناً از متنِ دانش‌آموز",
     "student_answer_summary": "خلاصهٔ یک‌خطیِ پاسخِ خودِ دانش‌آموز",
     "diagnostic_insight": "تشخیصِ یک‌خطی: در ذهنِ او چه اتفاقی افتاد",
     "wrong_claim": "ادعای غلطِ مشخص یا null",
     "cognitive_verdict": "یک جمله: چه چیزی را فهمیده و چه چیزی را نه",
     "tutor_teaching": {
       "misconception_root": "ریشهٔ خطای فکری، دلسوزانه و کوتاه",
       "intuitive_explanation": "آموزشِ گام‌به‌گامِ مفهوم، بدونِ اصطلاحِ پیچیده",
       "golden_tip": "یک تمثیلِ روزمره یا کلیدواژهٔ طلایی برای تثبیت"
     },
     "expected_logic_missed": "کدام بخشِ منطقِ موردانتظار غایب است (اگر کامل است، null)",
     "evidence_type": "strong_confirming | weak_confirming | contradicting | none",
     "missing_gear": "چرخ‌دندهٔ غایب در ذهن (یا null)",
     "confidence": 0.0}
  ],
  "dimension_findings": [],
  "root_cause_hypotheses": [],
  "improvement_suggestions": []
}

قواعدِ status (اجباری، برای همان پنج مرحله) — **چهار حالت، بدونِ استثنا**:
  - correct: پاسخ همان هستهٔ منطقیِ expected_logic را دارد.
  - partial: بخشی از استدلال درست است ولی هستهٔ منطقِ موردانتظار غایب یا
    ناقص است. **پاسخِ درست در نتیجه ولی با استدلالِ نادرست = partial.**
  - incorrect: پاسخ به نتیجهٔ نادرست می‌رسد یا بدفهمی را تأیید می‌کند.
  - insufficient: پاسخی نیست، یا پاسخ هیچ ادعای قابلِ‌سنجش ندارد.

**معلمِ هوشمند (`tutor_teaching`) — برای هر ده سؤال اجباری است:**
  هر سؤال یک آبجکتِ ``tutor_teaching`` با سه فیلد دارد که همان کتابِ درسیِ
  کوچکِ دانش‌آموز است. این متن‌ها را **مستقیم به خودِ دانش‌آموز** می‌نویسی،
  پس لحن صمیمی، محترمانه و بدونِ تحقیر است:
    • ``misconception_root`` — «کجای ماجرا لغزیدی؟» چرا ذهنِ او به این پاسخِ
      اشتباه رفت. به فرایندِ فکرِ او اشاره کن، نه به خودش. (۲ تا ۳ جمله)
    • ``intuitive_explanation`` — «اصلِ داستان چیه؟» مفهوم را شهودی و
      گام‌به‌گام توضیح بده، بدونِ فرمولِ اضافه و بدونِ اصطلاحِ نامفهوم. (۳ تا ۵ جمله)
    • ``golden_tip`` — «نکتهٔ طلاییِ ساعت‌ساز»: یک تمثیلِ روزمره یا کلیدواژهٔ
      کوتاه که در حافظه بماند. (۱ تا ۲ جمله)
  برای سؤالِ correct هم این سه فیلد را پر کن، ولی با لحنِ تأییدی و تعمیقِ
  فهم. برای سؤالِ بی‌پاسخ، آموزشی از صفر باشد.

هم‌چنین برای هر سؤال این دو فیلد کوتاه را پر کن:
  - ``student_answer_summary``: پاسخِ دانش‌آموز در یک خط.
  - ``diagnostic_insight``: تشخیصِ تو در یک خط (چه اتفاقی در ذهنش افتاد).

برای **مرحله‌های ۱، ۳ و ۴** علاوه بر status، این دو فیلد اجباری است:
  - "evidence_quote": یک بریدهٔ کوتاه و **عیناً از متنِ خودِ دانش‌آموز**
    (نه بازنویسیِ تو). اگر پاسخ خالی است، null.
  - "wrong_claim": ادعای غلطِ مشخصی که در پاسخ آمده (یک جمله). اگر ادعای
    غلطی نیست، null.

قواعدِ سخت‌گیرانه (تخلف از آن‌ها حکم را باطل می‌کند):
  ۱. جملهٔ «نتیجه درست است» به‌تنهایی correct نمی‌سازد. اگر دانش‌آموز
     استدلالِ غلطی آورده که به نتیجهٔ درست رسیده، partial است.
  ۲. اگر در پاسخِ مرحله ۴ ادعایی مثل «مقاومت تغییر می‌کند تا جریان ثابت
     بماند» یا «مقاومت با ولتاژ زیاد می‌شود» باشد، حداکثر partial — حتی اگر
     جملهٔ «امیر اشتباه می‌کند» را نوشته باشد.
  ۳. MASTERED فقط وقتی مجاز است که مرحله ۳ و مرحله ۴ **هر دو** correct
     باشند. در هر حالتِ دیگر MASTERED ممنوع است.
  ۴. طولِ پاسخ هیچ نقشی ندارد. پاسخِ کوتاه ولی درست، correct است؛ پاسخِ
     بلندِ ناقص، partial.
  برای هر مرحله فیلدِ expected_logic_missed را هم پر کن؛ این فیلد به
  دانش‌آموز نشان داده نمی‌شود و مبنایِ جمع‌بندیِ کد است.

نکته: فیلدهای dimension_findings و root_cause_hypotheses و
improvement_suggestions را هم پر کن تا گزارش‌های قدیمی و PDF نشکنند.
improvement_suggestions باید آرایه‌ای از **رشته‌های فارسیِ ساده** باشد
(نه آبجکت/دیکشنری) — هر آیتم یک قدمِ عملیِ روشن.

<<<CONCEPT>>>{concept_name}<<<END>>>
<<<EXPECTED_LOGIC>>>{expected_json}<<<END>>>
<<<FORBIDDEN>>>{forbidden_json}<<<END>>>
<<<ANSWERS>>>
{answers_block}
<<<END>>>
"""

_NAMES = {
    1: "فلسفه و تصویر کلان",
    2: "تستِ لایهٔ نقاب",
    3: "دستکاریِ سیستم",
    4: "عیب‌یابیِ ساعتِ خراب",
    5: "چالشِ فاینمن",
}


# ---------------------------------------------------------------------------
# کمکی‌های متنی
# ---------------------------------------------------------------------------
_CHAR_MAP = str.maketrans({"ي": "ی", "ك": "ک", "أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ؤ": "و"})


def _normalize(text: str) -> str:
    s = (text or "").translate(_CHAR_MAP)
    s = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)
    s = s.replace("\u200c", " ")
    return re.sub(r"\s+", " ", s).strip()


def _word_present(word: str, text: str) -> bool:
    w = _normalize(word)
    if not w:
        return False
    pattern = r"(?<![\wآ-ی])" + re.escape(w) + r"(?![\wآ-ی])"
    return re.search(pattern, _normalize(text)) is not None


def find_forbidden_hits(answer: str, forbidden: list[str]) -> list[str]:
    """کلماتِ ممنوعه‌ای که دانش‌آموز به کار برده — بررسیِ قطعیِ سمتِ سرور."""
    return [w for w in (forbidden or []) if _word_present(w, answer)]


def _word_count(text: str) -> int:
    return len(_normalize(text).split()) if text else 0


def _chosen_option(
    answer: str, options: list[str], selected_index: Optional[int] = None
) -> Optional[int]:
    """اندیسِ گزینهٔ انتخاب‌شده — **منبعِ اول و اصلی: ``selected_index``**.

    چرا این تغییر لازم شد: نسخهٔ قبلی هر عددی را در متنِ پاسخ «گزینه» تفسیر
    می‌کرد. دانش‌آموزی که گزینهٔ «۳ آمپر» را می‌زد و در توضیحِ اختیاری
    می‌نوشت «۱۲ تقسیم بر ۴»، انتخابش به گزینهٔ چهارم می‌رفت. حالا انتخاب از
    یک منبعِ صریح و صفرمبنا می‌آید و توضیحِ آزاد هرگز در آن دخالت نمی‌کند.

    متنِ گزینه به‌عنوانِ مسیرِ دوم فقط وقتی پذیرفته می‌شود که **دقیقاً** با
    یکی از گزینه‌ها یکی باشد (نه هر عددی داخلِ جمله).
    """
    if selected_index is not None:
        try:
            index = int(selected_index)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < max(1, len(options)):
            return index
        return None
    if not answer or not options:
        return None
    text = _normalize(answer)
    for index, option in enumerate(options):
        if _normalize(option) == text:
            return index
    return None


# ---------------------------------------------------------------------------
# سیگنال‌های قطعی — به مدل داده می‌شوند و در لاگ می‌مانند
# ---------------------------------------------------------------------------
_SUGGESTION_KEYS = ("suggestion", "text", "description", "title", "action", "advice")

#: پیشنهادهایی که «قدمِ عملی» نیستند: توصیهٔ احساسی/انگیزشی یا جملهٔ کلی.
#: این‌ها در کارنامهٔ شناختی بی‌معنا هستند و در اجرای زنده هم دیده شدند.
_NON_ACTIONABLE_PATTERNS = (
    "نفس عمیق",
    "آرام باش",
    "استرس",
    "نگران نباش",
    "اعتماد به نفس",
    "خودت را باور",
    "بیشتر تلاش کن",
    "بیشتر تمرین کن",
    "تلاش بیشتری کن",
)


def _is_actionable(text: str) -> bool:
    compact = str(text or "").replace("\u200c", "")
    # حدِ طول فقط برای دورریختنِ آشغال (مثلِ «-» یا «ok») است، نه برای سنجشِ
    # کیفیت؛ پیشنهادِ کوتاه ولی عملی هم معتبر است.
    if len(compact.strip()) < 4:
        return False
    return not any(p.replace("\u200c", "") in compact for p in _NON_ACTIONABLE_PATTERNS)


def normalize_suggestions(raw: Any) -> list[str]:
    """پیشنهادها را به فهرستِ تمیزِ رشته تبدیل می‌کند.

    مدل‌ها گاهی به‌جای رشته، آبجکت می‌فرستند (``{"title": ..., "suggestion":
    ...}``). تبدیلِ سادهٔ ``str(dict)`` در فرانت به ``[object Object]`` و در
    PDF به دیکشنریِ خام می‌رسید. این‌جا هر شکلِ معقولی به یک جملهٔ فارسی
    تبدیل می‌شود و آیتم‌های بی‌محتوا (None، دیکشنریِ خالی، «نامشخص») حذف.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    out: list[str] = []
    for item in raw:
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            for key in _SUGGESTION_KEYS:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    text = value
                    break
            if not text:
                # هیچ کلیدِ شناخته‌شده‌ای نبود: اولین رشتهٔ غیرخالی
                for value in item.values():
                    if isinstance(value, str) and value.strip():
                        text = value
                        break
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            text = str(item)
        elif isinstance(item, list):
            text = " ".join(str(v).strip() for v in item if str(v or "").strip())

        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        # باقی‌ماندهٔ JSON/دیکشنری یا متنِ خالی، پیشنهاد نیست
        if not cleaned or cleaned.lower() in {"none", "null", "nan", "undefined"}:
            continue
        if cleaned.startswith(("{", "[")) and cleaned.endswith(("}", "]")):
            continue
        if not _is_actionable(cleaned):
            continue
        if cleaned not in out:
            out.append(cleaned)
    return out


def collect_signals(
    question_rows: list[dict[str, Any]],
    answers: dict[int, str],
    concept_name: str = "",
    selected_indices: dict[int, int] | None = None,
) -> dict[str, Any]:
    """سیگنال‌های ساختاری که بدونِ مدل هم قابلِ محاسبه‌اند — نسخهٔ ۱۰ سؤالی."""
    by_order = {int(q.get("order") or 0): q for q in question_rows}
    chosen_map = selected_indices or {}

    # ── مرحلهٔ ۲ (سؤال‌های تستی): هر کدام جداگانه و سپس تجمیع ──
    mcq_orders = sorted(o for o, r in by_order.items() if (r.get("options") or []))
    mcq_results: dict[int, Optional[bool]] = {}
    for order in mcq_orders:
        row = by_order[order]
        options = row.get("options") or []
        picked = _chosen_option(answers.get(order, ""), options, chosen_map.get(order))
        correct = row.get("correct_option_index")
        mcq_results[order] = (
            None if (picked is None or correct is None)
            else int(picked) == int(correct)
        )
    mcq_answered = {o: v for o, v in mcq_results.items() if v is not None}
    # «mcq_correct» = هر دو تست درست (شرطِ لازمِ قانونِ توهمِ دانایی)
    mcq_correct = bool(mcq_answered) and all(mcq_answered.values())
    mcq_any_correct = any(v for v in mcq_answered.values())

    first_mcq = mcq_orders[0] if mcq_orders else 0
    q2_row = by_order.get(first_mcq) or {}
    chosen = _chosen_option(
        answers.get(first_mcq, ""), q2_row.get("options") or [], chosen_map.get(first_mcq)
    )

    # ── کلماتِ ممنوعه: فقط در پاسخِ **همان سؤالی** که آن کلمه را ممنوع کرده ──
    # قاعدهٔ قبلی همهٔ واژه‌ها را در همهٔ پاسخ‌ها می‌گشت؛ با ۱۰ سؤال این یعنی
    # کلمه‌هایی که در سؤالِ ۲ آمده و ممنوع نیست، در پاسخِ سؤالِ ۹ «تخلف»
    # شمرده می‌شد. حالا هر فهرست به سؤالِ خودش گره خورده است.
    forbidden: list[str] = []
    hits: list[str] = []
    for order, row in sorted(by_order.items()):
        words = [w for w in (row.get("forbidden_words") or []) if w]
        if not words:
            continue
        for word in words:
            if word not in forbidden:
                forbidden.append(word)
        for hit in find_forbidden_hits(answers.get(order, "") or "", words):
            if hit not in hits:
                hits.append(hit)

    # ── سیگنالِ «بی‌ربط»: پاسخِ مفصل که هیچ واژهٔ کلیدیِ مفهوم را ندارد ──
    key_terms: list[str] = []
    key_terms.extend(t for t in _normalize(concept_name).split() if len(t) > 3)
    for row in question_rows:
        for proposition in row.get("mapped_propositions") or []:
            key_terms.extend(t for t in _normalize(str(proposition)).split() if len(t) > 4)
        expected = _normalize(str(row.get("expected_logic") or ""))
        key_terms.extend(t for t in expected.split() if len(t) > 4)
    unique_terms = list(dict.fromkeys(key_terms))[:60]

    discursive = sorted(o for o in by_order if not (by_order[o].get("options") or []))
    off_topic_orders: list[int] = []
    for order in discursive:
        text = _normalize(answers.get(order, ""))
        if _word_count(text) < 12:
            continue
        if unique_terms and not any(term in text for term in unique_terms):
            off_topic_orders.append(order)
    detailed = [o for o in discursive if _word_count(answers.get(o, "")) >= 12]
    mostly_off_topic = bool(detailed) and len(off_topic_orders) >= max(
        1, (len(detailed) * 2 + 2) // 3
    )

    answered_orders = {o for o in answers if _normalize(answers.get(o, ""))} | set(mcq_answered)

    return {
        "chosen_option": chosen,
        "correct_option": q2_row.get("correct_option_index"),
        "mcq_correct": mcq_correct,
        "mcq_any_correct": mcq_any_correct,
        "mcq_results": {str(k): v for k, v in sorted(mcq_results.items())},
        "forbidden_words": forbidden,
        "forbidden_hits": hits,
        "jargon_violated": bool(hits),
        "relevant_semantic_answers": bool(discursive) and len(off_topic_orders) < len(discursive),
        "off_topic_orders": off_topic_orders,
        "mostly_off_topic": mostly_off_topic,
        "answered_orders": sorted(answered_orders),
        "total_questions": len(by_order),
    }


# ---------------------------------------------------------------------------
# حکمِ ساختاریافتهٔ هر مرحله — جمع‌بندی با کد، نه با شمارشِ کلمه
# ---------------------------------------------------------------------------
#: وضعیت‌های مجازِ هر مرحله. «evidence_type» جدا از وضعیت است: یک پاسخِ
#: نادرست می‌تواند شاهدِ قوی داشته باشد.
STAGE_STATUS_CORRECT = "CORRECT"
STAGE_STATUS_HALF = "HALF_CORRECT"
STAGE_STATUS_WRONG = "WRONG"
STAGE_STATUS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

_VALID_STAGE_STATUS = {
    STAGE_STATUS_CORRECT,
    STAGE_STATUS_HALF,
    STAGE_STATUS_WRONG,
    STAGE_STATUS_INSUFFICIENT,
    # سازگاری با برچسب‌های قدیمیِ شواهد
    "CONFIRMED",
    "LIKELY_UNDERSTOOD",
    "UNCLEAR",
    "NEEDS_REVIEW",
}

#: نگاشتِ برچسب‌های قدیمی/مدل به وضعیتِ سه‌گانه. مدل‌ها گاهی CONFIRMED
#: می‌دهند و گاهی CORRECT؛ هر دو باید یک مسیر را بروند.
_STATUS_ALIASES = {
    "CORRECT": STAGE_STATUS_CORRECT,
    "IN_TRUE": STAGE_STATUS_CORRECT,
    "CONFIRMED": STAGE_STATUS_CORRECT,
    "LIKELY_UNDERSTOOD": STAGE_STATUS_CORRECT,
    "PARTIALLY_CORRECT": STAGE_STATUS_HALF,
    # فرمِ چهارگانه‌ای که پرامپت می‌خواهد (حروفِ کوچک هم پذیرفته می‌شود)
    "PARTIAL": STAGE_STATUS_HALF,
    "INCORRECT": STAGE_STATUS_WRONG,
    "INSUFFICIENT": STAGE_STATUS_INSUFFICIENT,
    "PARTIAL": STAGE_STATUS_HALF,
    "HALF_CORRECT": STAGE_STATUS_HALF,
    "MIXED": STAGE_STATUS_HALF,
    "WRONG": STAGE_STATUS_WRONG,
    "INCORRECT": STAGE_STATUS_WRONG,
    "MISCONCEPTION": STAGE_STATUS_WRONG,
    "UNCLEAR": STAGE_STATUS_INSUFFICIENT,
    "NEEDS_REVIEW": STAGE_STATUS_INSUFFICIENT,
    "INSUFFICIENT_EVIDENCE": STAGE_STATUS_INSUFFICIENT,
    "NO_ANSWER": STAGE_STATUS_INSUFFICIENT,
    "EMPTY": STAGE_STATUS_INSUFFICIENT,
}

#: ترتیبِ شدت — برای پیدا کردنِ «ضعیف‌ترین» حلقهٔ زنجیره.
_SEVERITY = {
    STAGE_STATUS_CORRECT: 0,
    STAGE_STATUS_HALF: 1,
    STAGE_STATUS_WRONG: 2,
    STAGE_STATUS_INSUFFICIENT: 3,
}


def canonical_stage_status(raw: Any) -> str:
    """هر برچسبی را به یکی از چهار وضعیتِ استاندارد می‌برد."""
    token = str(raw or "").strip().upper()
    return _STATUS_ALIASES.get(token, STAGE_STATUS_INSUFFICIENT)


#: نشانه‌های ادعای مفهومیِ غلط در پاسخِ مرحله ۴. اگر مدل Q4 را «درست»
#: بزند ولی متنِ دانش‌آموز یکی از این ادعاها را داشته باشد، برچسب به
#: HALF_CORRECT تنزل می‌کند: نتیجهٔ درست با استدلالِ غلط، «درست» نیست.
#: این گارد سمتِ کد است تا به حسنِ نیتِ مدل وابسته نباشد.
_WRONG_Q4_CLAIMS: tuple[tuple[re.Pattern[str], str], ...] = (
    # «مقاومت (خودش را) تغییر می‌دهد تا جریان ثابت بماند» — بدفهمیِ اصلی
    (
        re.compile(
            r"(?:مقاومت|R)[^.؟!]{0,45}"
            r"(?:تغییر میکند|تغییر می‌کند|عوض میشود|عوض می‌شود|زیاد میشود|"
            r"زیاد می‌شود|کم میشود|کم می‌شود|بیشتر میشود|بیشتر می‌شود)"
            r"[^.؟!]{0,45}"
            r"(?:جریان|I)[^.؟!]{0,30}(?:ثابت|همان مقدار|یکسان|تغییر نکند)"
        ),
        "ادعای «مقاومت تغییر می‌کند تا جریان ثابت بماند» — همان بدفهمیِ اصلی",
    ),
    # «مقاومت با بالا رفتنِ ولتاژ بیشتر می‌شود»
    (
        re.compile(
            r"(?:ولتاژ|V)[^.؟!]{0,30}(?:زیاد|بیشتر|بالا)[^.؟!]{0,30}"
            r"(?:مقاومت|R)[^.؟!]{0,25}(?:زیاد میشود|زیاد می‌شود|بیشتر میشود|"
            r"بیشتر می‌شود|بالا میرود|بالا می‌رود)"
        ),
        "ادعای «مقاومت با افزایش ولتاژ زیاد می‌شود»",
    ),
    # «جریان تغییر می‌کند تا مقاومت ثابت بماند» (ترتیبِ معکوسِ همین بدفهمی)
    (
        re.compile(
            r"(?:جریان|I)[^.؟!]{0,35}"
            r"(?:تغییر میکند|تغییر می‌کند|کم میشود|کم می‌شود|زیاد میشود|"
            r"زیاد می‌شود|عوض میشود|عوض می‌شود)"
            r"[^.؟!]{0,35}"
            r"(?:مقاومت|R)[^.؟!]{0,30}(?:ثابت بماند|ثابت میماند|ثابت می‌ماند|"
            r"یکسان بماند|تغییر نکند)"
        ),
        "ادعای «جریان تغییر می‌کند تا مقاومت ثابت بماند» — وارونه‌گوییِ رابطه",
    ),
    # «جریان ثابت می‌ماند»
    (
        re.compile(r"(?:جریان|I)[^.؟!]{0,30}(?:ثابت میماند|ثابت می‌ماند|تغییر نمیکند|تغییر نمی‌کند)"),
        "ادعای «جریان ثابت می‌ماند»",
    ),
    # «مدار/رسانا خودش را تنظیم می‌کند»
    (
        re.compile(
            r"(?:مدار|سیستم|رسانا)[^.؟!]{0,30}(?:خودش|خود به خود|خودکار)"
            r"[^.؟!]{0,25}(?:تنظیم میکند|تنظیم می‌کند|جبران میکند|جبران می‌کند|متعادل)"
        ),
        "ادعای «سیستم خودش را تنظیم می‌کند»",
    ),
)


def wrong_q4_claim(text: str) -> Optional[str]:
    """اگر پاسخِ مرحله ۴ ادعای مفهومیِ غلطی داشته باشد، توضیحش را برمی‌گرداند."""
    body = re.sub(r"\$[^$]*\$", " ", str(text or "")).replace("\u200c", "")
    # الگوها با آگاهی از ZWNJ نوشته شده‌اند؛ پس هر دو شکل را می‌آزماییم.
    for pattern, reason in _WRONG_Q4_CLAIMS:
        if pattern.search(body) or pattern.search(str(text or "")):
            return reason
    return None


def apply_q4_claim_guard(
    per_question: list[dict[str, Any]], answers: dict[int, str]
) -> bool:
    """Q4 را با ادعای مفهومیِ غلط، حداکثر ``HALF_CORRECT`` می‌کند.

    برمی‌گرداند True اگر تنزیل انجام شده باشد (برای ثبتِ یافته).
    """
    record = next((r for r in per_question if int(r.get("order") or 0) == 4), None)
    if record is None:
        return False
    if canonical_stage_status(record.get("status")) != STAGE_STATUS_CORRECT:
        return False
    reason = wrong_q4_claim(answers.get(4, ""))
    if not reason:
        return False
    record["status"] = STAGE_STATUS_HALF
    record["evidence_type"] = "contradicting"
    record["expected_logic_missed"] = reason
    if not record.get("missing_gear"):
        record["missing_gear"] = reason
    print(f"[CrossCheck] Q4 was marked correct but contains a wrong claim: {reason}")
    return True


def compute_debugging_strength(
    per_question: list[dict[str, Any]], signals: dict[str, Any]
) -> bool:
    """«قوی» یعنی: مرحله ۳ درست **و** مرحله ۴ حداقل نیمه‌درست — معنایی.

    هیچ‌جای این تابع به طولِ پاسخ یا تعدادِ کلمه نگاه نمی‌شود. پاسخِ بلند و
    بی‌ربط، یا پاسخی که فقط دلالتِ حاصل‌ضرب را تکرار می‌کند و «چرا» را
    توضیح نمی‌دهد، از این دروازه رد نمی‌شود.
    """
    stages = (
        collapse_to_stages(per_question)
        if len(per_question or []) > 5
        else list(per_question or [])
    )
    by_order = {int(r.get("order") or 0): r for r in stages}
    q3 = canonical_stage_status(by_order.get(3, {}).get("status"))
    q4 = canonical_stage_status(by_order.get(4, {}).get("status"))
    # مرحلهٔ ۴ باید «درست» باشد، نه فقط نیمه‌درست: نیمه‌درست یعنی دقیقاً
    # هستهٔ نقد را نگفته است — و همان هسته، دلیلِ وجودِ مرحله ۴ است.
    sem_ok = q3 == STAGE_STATUS_CORRECT and q4 == STAGE_STATUS_CORRECT
    return bool(sem_ok and signals.get("relevant_semantic_answers", True))


def aggregate_stage_status(statuses: list[str]) -> str:
    """برچسبِ یک **مرحله** از دو سؤالِ آن.

    قاعده: بدترین حالت حاکم است، با یک استثنا — اگر یکی از دو سؤال بی‌پاسخ
    باشد و دیگری درست، مرحله «نیمه‌درست» است نه «بی‌پاسخ»؛ نصفِ شاهد داشتن
    یعنی «نیمه‌راه»، نه «هیچ شاهد». و اگر یک سؤال درست و یکی غلط باشد، مرحله
    قابلِ‌اعتماد نیست و «نیمه‌درست» می‌شود.
    """
    clean = [canonical_stage_status(x) for x in statuses if x]
    if not clean:
        return STAGE_STATUS_INSUFFICIENT
    if len(set(clean)) == 1:
        return clean[0]
    present = set(clean)
    if STAGE_STATUS_CORRECT in present:
        # هر ترکیبی با یک سؤالِ درست: حداکثر نیمه‌درست
        return STAGE_STATUS_HALF
    if STAGE_STATUS_WRONG in present:
        # غلط + بی‌پاسخ ⇒ نیمه‌درست؛ غلط + نیمه‌درست ⇒ غلط
        return (
            STAGE_STATUS_HALF
            if STAGE_STATUS_INSUFFICIENT in present
            else STAGE_STATUS_WRONG
        )
    if STAGE_STATUS_HALF in present:
        return STAGE_STATUS_HALF
    return STAGE_STATUS_INSUFFICIENT


def collapse_to_stages(
    per_question: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """ده رکوردِ سؤال را به پنج رکوردِ **مرحله** جمع می‌کند.

    منطقِ حکم همیشه مرحله‌محور بوده؛ این تابع همان ورودی را از ساختارِ
    ده‌سؤالی می‌سازد. هر رکوردِ مرحله بهترین شاهد و بدترین ادعای سؤال‌های
    خودش را نگه می‌دارد و ``order`` آن شمارهٔ مرحله است (۱..۵).
    """
    by_stage: dict[int, list[dict[str, Any]]] = {}
    for record in per_question or []:
        order = int(record.get("order") or 0)
        stage = int(record.get("stage") or stage_of_order(order))
        if stage <= 0:
            continue
        by_stage.setdefault(stage, []).append(record)

    collapsed: list[dict[str, Any]] = []
    for stage in sorted(by_stage):
        records = sorted(by_stage[stage], key=lambda r: int(r.get("order") or 0))
        status = aggregate_stage_status([str(r.get("status") or "") for r in records])
        verdicts = [
            str(r.get("cognitive_verdict")).strip()
            for r in records
            if str(r.get("cognitive_verdict") or "").strip()
        ]
        collapsed.append(
            {
                "order": stage,
                "stage": stage,
                "orders": [int(r.get("order") or 0) for r in records],
                "stage_title": STAGE_TITLES_FA.get(stage)
                or (records[0].get("stage_title") or ""),
                "status": status,
                "evidence_quote": next(
                    (str(r.get("evidence_quote")).strip()
                     for r in records if r.get("evidence_quote")), None
                ),
                "wrong_claim": next(
                    (str(r.get("wrong_claim")).strip()
                     for r in records if r.get("wrong_claim")), None
                ),
                "expected_logic_missed": next(
                    (str(r.get("expected_logic_missed")).strip()
                     for r in records if r.get("expected_logic_missed")), None
                ),
                "cognitive_verdict": " / ".join(verdicts),
                "qualitative_feedback": " / ".join(verdicts),
                "missing_gear": next(
                    (r.get("missing_gear") for r in records if r.get("missing_gear")), None
                ),
                "question_count": len(records),
            }
        )
    return collapsed


def derive_status(
    model_status: str, per_question: list[dict[str, Any]], signals: dict[str, Any]
) -> tuple[str, Optional[str]]:
    """حکمِ نهایی را از شواهدِ مرحله‌ای مشتق می‌کند — نه از حرفِ مدل.

    این تابع «منبعِ واحدِ حقیقت» است: نشان، عنوان و خلاصه همه از خروجیِ همین
    تابع ساخته می‌شوند، پس ترکیبِ «زنجیره کامل و درست است» با نشانِ «نامشخص»
    یا «مسلط» با «استدلالِ ناقص» ممکن نیست.

    برمی‌گرداند ``(status, note)``؛ ``note`` فقط وقتی پر می‌شود که حکمِ مدل
    با شواهد نخوانده باشد.
    """
    # ورودی ممکن است ۱۰ رکوردِ سؤال باشد (فاز ۱۱) یا ۵ رکوردِ مرحله
    # (آزمون‌های قدیمی). در حالتِ اول، دو سؤالِ هر مرحله تجمیع می‌شوند.
    stages = collapse_to_stages(per_question) if len(per_question or []) > 5 else list(per_question or [])
    by_order = {int(r.get("order") or 0): r for r in stages}
    q1 = canonical_stage_status(by_order.get(1, {}).get("status"))
    q2 = canonical_stage_status(by_order.get(2, {}).get("status"))
    q3 = canonical_stage_status(by_order.get(3, {}).get("status"))
    q4 = canonical_stage_status(by_order.get(4, {}).get("status"))
    q5 = canonical_stage_status(by_order.get(5, {}).get("status"))

    jargon = bool(signals.get("jargon_violated"))
    off_topic = bool(signals.get("mostly_off_topic"))

    # ۱) بی‌ربطی و نقضِ کلماتِ ممنوعه، سقفِ سخت دارند.
    if off_topic:
        return "UNSTRUCTURED", (
            "پاسخ‌هایت مفصل بود، اما به موضوعِ همین آزمون نمی‌پرداخت. "
            "اول باید مکانیزم را دقیقاً برای همین مفهوم بگویی."
        )
    if jargon:
        return "JARGON_DEPENDENT", (
            "استدلالت ممکن است درست باشد، اما برای توضیحِ ساده ناچار شدی به "
            "همان اصطلاحاتِ ممنوعه تکیه کنی. فهم، وقتی آزاد است که بدونِ آن "
            "واژه‌ها هم بتوانی بگویی."
        )

    # کالیبراسیونِ فاز ۱۱: «مسلط / فهمِ عمیق» = مرحلهٔ ۳ (زنجیرهٔ علّی) و
    # مرحلهٔ ۴ (عیب‌یابی) و مرحلهٔ ۵ (توضیحِ ساده) هر سه درست باشند.
    core_ok = (
        q3 == STAGE_STATUS_CORRECT
        and q4 == STAGE_STATUS_CORRECT
        and q5 == STAGE_STATUS_CORRECT
    )

    # ۲) هستهٔ زنجیره درست است ⇒ مسلط. ضعفِ Q1/Q2 مانع نمی‌شود (مرحلهٔ ۲
    #    تست است و خطای محاسباتی، فهمِ عمیق را باطل نمی‌کند).
    if core_ok:
        return "MASTERED", None

    # ۳) «توهمِ دانایی» یعنی: تست را **درست** زده، اما در مرحلهٔ شهودی/تحلیلی
    #    (۳ یا ۴ یا ۵) لغزیده. اگر خودِ تست غلط باشد، مهارتِ فرمولی هم نیست؛
    #    آن‌جا حکمِ PARTIAL_FRAGMENTED صادق‌تر است.
    # «فرمول‌محور ولی فهمیده»: اگر فقط مرحلهٔ ۵ (بیان) لنگ زده و مرحلهٔ ۳
    # درست است، این توهمِ دانایی نیست — PARTIAL_FRAGMENTED با لحنِ محترمانه.
    if (
        q3 == STAGE_STATUS_CORRECT
        and q4 in (STAGE_STATUS_CORRECT, STAGE_STATUS_HALF)
        and q5 in (STAGE_STATUS_HALF, STAGE_STATUS_WRONG)
    ):
        return "PARTIAL_FRAGMENTED", (
            "مفهوم را می‌دانی و زنجیرهٔ علّی را درست چیدی؛ چیزی که کم است، "
            "بیرون آمدن از پشتِ فرمول و توضیحِ ساده با زبانِ خودت است."
        )

    # «توهمِ دانایی» سخت‌گیرانه: تست‌ها را درست زده، اما در مرحلهٔ ۳ یا ۴
    # استدلالِ غلط/ضدعلمی داده. ضعفِ صرفِ بیان (مرحلهٔ ۵) کافی نیست.
    if (
        signals.get("mcq_correct")
        and q3 in (STAGE_STATUS_HALF, STAGE_STATUS_WRONG)
        and q4 in (STAGE_STATUS_HALF, STAGE_STATUS_WRONG)
    ):
        if q4 in (STAGE_STATUS_HALF, STAGE_STATUS_WRONG):
            note = (
                "رابطه را در تست درست به کار بردی، اما در نقدِ استدلال به همان "
                "بدفهمی برگشتی."
            )
        else:
            note = (
                "تستِ فرمولی را درست زدی، اما در یکی از مرحله‌های شهودی یا تحلیلی "
                "همان دقت را نداشتی."
            )
        return "ILLUSION_OF_COMPETENCE", note

    # ۴) پاسخ‌ها هیچ ادعای قابلِ‌سنجشی ندارند (نمونه: «نمی‌دانم»).
    measurable = [
        canonical_stage_status(by_order.get(o, {}).get("status"))
        for o in (1, 3, 4, 5)
        if o in by_order
    ]
    if measurable and all(st == STAGE_STATUS_INSUFFICIENT for st in measurable):
        return "UNSTRUCTURED", (
            "پاسخ‌ها آن‌قدر کوتاه یا خالی بودند که نشود دربارهٔ فهمت حکم داد."
        )

    note = None
    if q4 != STAGE_STATUS_CORRECT:
        note = (
            "ضعیف‌ترین حلقهٔ زنجیره، مرحلهٔ عیب‌یابی بود: هستهٔ استدلالِ غلط "
            "به‌طور کامل رد نشد."
        )
    elif q3 != STAGE_STATUS_CORRECT:
        note = "زنجیرهٔ علّیِ مرحلهٔ دستکاری به‌طور کامل درست نبود."
    elif q1 == STAGE_STATUS_INSUFFICIENT:
        note = "تصویرِ کلانِ مفهوم هنوز جای خالی دارد."
    return "PARTIAL_FRAGMENTED", note


_STAGE_FA = {
    1: "فلسفه و تصویر کلان",
    2: "تستِ لایهٔ نقاب",
    3: "دستکاریِ سیستم",
    4: "عیب‌یابیِ ساعتِ خراب",
    5: "چالشِ فاینمن",
}
_STATUS_WORD_FA = {
    STAGE_STATUS_CORRECT: "درست",
    STAGE_STATUS_HALF: "نیمه‌درست",
    STAGE_STATUS_WRONG: "نادرست",
    STAGE_STATUS_INSUFFICIENT: "بدون پاسخ",
}


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa_num(value: Any) -> str:
    """رقمِ فارسی — متنِ فارسیِ کارنامه نباید رقمِ لاتین داشته باشد."""
    return str(value).translate(_FA_DIGITS)


def _summary_from_stages(
    per_question: list[dict[str, Any]],
    status: str,
    culprit: Optional[dict[str, Any]] = None,
    note: Optional[str] = None,
) -> str:
    """خلاصهٔ مدیریتی را از وضعیتِ تجمیعیِ Q1 تا Q5 می‌سازد.

    قاعدهٔ سخت: عبارتِ «بقیهٔ مرحله‌ها خوب پیش رفتند» فقط وقتی مجاز است که
    واقعاً بقیه درست باشند. اگر دو یا چند مرحله نیمه‌درست/نادرست‌اند، خلاصه
    همان چند مرحله را نام می‌برد. نسخهٔ قبلی این جمله را بی‌قید می‌نوشت و
    کارنامه‌ای می‌ساخت که با کارت‌هایش نمی‌خواند.
    """
    # ورودی می‌تواند ۱۰ رکوردِ سؤال باشد؛ برای خلاصه فقط پنج مرحله لازم است.
    stages = (
        collapse_to_stages(per_question)
        if len(per_question or []) > 5
        else list(per_question or [])
    )
    by_order = {int(r.get("order") or 0): r for r in stages}
    states = {
        order: canonical_stage_status(by_order.get(order, {}).get("status"))
        for order in range(1, 6)
    }
    correct_orders = [o for o, st in states.items() if st == STAGE_STATUS_CORRECT]
    problem_orders = [
        o for o, st in states.items()
        if st in (STAGE_STATUS_HALF, STAGE_STATUS_WRONG)
    ]
    unanswered = [
        o for o, st in states.items() if st == STAGE_STATUS_INSUFFICIENT
    ]

    def _name(order: int) -> str:
        title = str(by_order.get(order, {}).get("stage_title") or "").strip()
        # عنوانِ مرحله ممکن است خودش رقمِ لاتین داشته باشد («مرحله 1: …»)
        return _fa_num(title) if title else (
            f"مرحلهٔ {_fa_num(order)}: {_STAGE_FA.get(order, 'زنجیره')}"
        )

    def _flaw(order: int) -> str:
        return str(by_order.get(order, {}).get("expected_logic_missed") or "").strip()

    # ── هیچ مرحلهٔ ناکامی نیست: زنجیره بسته است ──
    if not problem_orders and not unanswered:
        return (
            "هر پنج مرحله با استدلالِ درست بسته شد؛ زنجیرهٔ فهم در این مفهوم "
            "کامل است."
        )

    parts: list[str] = []
    if problem_orders:
        if len(problem_orders) == 1:
            o = problem_orders[0]
            word = _STATUS_WORD_FA[states[o]]
            seg = f"«{_name(o)}» {word} بود"
            flaw = _flaw(o)
            if flaw:
                seg += f" — {flaw}"
            parts.append(seg + ".")
        else:
            detail = "، ".join(
                f"«{_name(o)}» {_STATUS_WORD_FA[states[o]]}" for o in problem_orders
            )
            parts.append(f"در {_fa_num(len(problem_orders))} مرحله لغزیدی: {detail}.")
    if unanswered:
        detail = "، ".join(f"«{_name(o)}»" for o in unanswered)
        parts.append(f"و {detail} بدون پاسخ ماند.")

    # «بقیه خوب بودند» فقط با شمارشِ واقعی — نه به‌عنوانِ جملهٔ تشریفاتی.
    rest = [o for o in correct_orders if o not in problem_orders]
    if rest:
        if len(rest) == 1:
            parts.append(f"فقط «{_name(rest[0])}» درست بود.")
        else:
            parts.append(
                f"{_fa_num(len(rest))} مرحله از پنج مرحله "
                f"({('، '.join(f'مرحلهٔ {_fa_num(o)}' for o in rest))}) درست بود."
            )
    if note and status != "MASTERED":
        parts.append(str(note).strip())
    if status != "MASTERED":
        parts.append(
            "تسلط وقتی معنا دارد که همهٔ حلقه‌های زنجیره، نه فقط یکی، بسته شوند."
        )
    return " ".join(p for p in parts if p)


def _verdict_culprit(per_question: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """حلقه‌ای که حکم را از «مسلط» برگرداند — به ترتیبِ اهمیت.

    Q4 (عیب‌یابی) مهم‌ترین است، بعد Q3 (زنجیرهٔ علّی)، بعد Q1. اگر هیچ‌کدام
    مشکل نداشتند، رفتارِ قبلی (ضعیف‌ترین مرحله) حفظ می‌شود.
    """
    stages = (
        collapse_to_stages(per_question)
        if len(per_question or []) > 5
        else list(per_question or [])
    )
    by_order = {int(r.get("order") or 0): r for r in stages}
    for order in (4, 3, 5, 1):
        record = by_order.get(order)
        if not record:
            continue
        if canonical_stage_status(record.get("status")) != STAGE_STATUS_CORRECT:
            return record
    return _weakest_link(stages)


def _weakest_link(per_question: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """ضعیف‌ترین مرحلهٔ زنجیره — برای توضیحِ «کجا شکست»."""
    worst: Optional[dict[str, Any]] = None
    worst_rank = -1
    for record in per_question:
        rank = _SEVERITY.get(canonical_stage_status(record.get("status")), 3)
        if rank > worst_rank:
            worst_rank = rank
            worst = record
    return worst


def _verdict_conflict(status: str, per_question: list[dict[str, Any]]) -> Optional[str]:
    """آیا حکمِ کلی با شواهدِ مرحله‌ای می‌خواند؟

    قاعدهٔ صریح: MASTERED فقط وقتی مجاز است که مرحله ۳ درست و مرحله ۴ درست
    باشد. اگر مدل کلی «مسلط» بدهد ولی Q4 نیمه‌درست یا نادرست باشد، این تابع
    تناقض را برمی‌گرداند و لایهٔ سازگارسازی حکم را اصلاح می‌کند.
    """
    if status != "MASTERED":
        return None
    by_order = {int(r.get("order") or 0): r for r in per_question}
    q3 = canonical_stage_status(by_order.get(3, {}).get("status"))
    q4 = canonical_stage_status(by_order.get(4, {}).get("status"))
    if q3 == STAGE_STATUS_CORRECT and q4 == STAGE_STATUS_CORRECT:
        return None
    if q4 != STAGE_STATUS_CORRECT and q4 != STAGE_STATUS_INSUFFICIENT:
        return (
            "حکمِ «مسلط» با نقدِ مرحله ۴ نمی‌خواند: هستهٔ استدلالِ غلط کامل "
            "رد نشده بود."
        )
    if q3 != STAGE_STATUS_CORRECT:
        return (
            "حکمِ «مسلط» با مرحله ۳ نمی‌خواند: زنجیرهٔ علّیِ دستکاریِ سیستم "
            "به‌طور کامل درست نبود."
        )
    return None


# ---------------------------------------------------------------------------
# اعمالِ قواعدِ قطعی روی حکمِ مدل
# ---------------------------------------------------------------------------
_VALID_STATUS = {
    "MASTERED",
    "ILLUSION_OF_COMPETENCE",
    "JARGON_DEPENDENT",
    "PARTIAL_FRAGMENTED",
    "UNSTRUCTURED",
}
_VALID_FINDING_TYPES = {
    "CONTRADICTION",
    "SYNERGY",
    "JARGON_VIOLATION",
    "BLUFF_DETECTED",
    "SLIP_RESOLVED",
}


def _clean_findings(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type") or "SYNERGY").upper().strip()
        if ftype not in _VALID_FINDING_TYPES:
            ftype = "SYNERGY"
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {
                "title": title,
                "type": ftype,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return out


def _dedupe(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for finding in findings:
        key = (finding["type"], finding["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _ensure_jargon_finding(findings: list[dict[str, str]], hits: list[str]) -> list[dict[str, str]]:
    """قانون ۲: اگر کلمهٔ ممنوعه استفاده شده، یافته‌اش حتماً باید در گزارش باشد."""
    if not hits:
        return findings
    if any(f["type"] == "JARGON_VIOLATION" for f in findings):
        return findings
    return [
        {
            "title": "شکستنِ قانونِ کلماتِ ممنوعه",
            "type": "JARGON_VIOLATION",
            "description": (
                f"در توضیحِ ساده از «{'، '.join(hits)}» استفاده کردی — همان کلماتی که "
                "قرار بود کنار بگذاری. یعنی توضیحت به ادبیاتِ کتاب تکیه داشت، نه به "
                "شهودِ خودت. (این مورد را سیستم مستقیم از متنِ پاسخِ تو استخراج کرد.)"
            ),
        }
    ] + findings


_STATUS_PERSONA = {
    "MASTERED": "مهندسی که ساعت را بست",
    # عنوانِ «تلهٔ فرمول و شهود» فقط وقتی مجاز است که تناقضی واقعاً ثبت شده
    # باشد. اگر باکسِ «شکارِ تناقض» بگوید «تناقضی یافت نشد»، این عنوان
    # دروغ است و کارنامه با خودش نمی‌خواند (بندِ ۳).
    "ILLUSION_OF_COMPETENCE": "پاسخ‌های متناقض — جای بازبینی",
    "JARGON_DEPENDENT": "فهمیده، ولی زندانیِ اصطلاحات",
    "PARTIAL_FRAGMENTED": "تفکرِ جزیره‌ای",
    "UNSTRUCTURED": "بی‌ساختار — پاسخ‌ها بیرون از موضوع",
}

#: عنوانِ جایگزین برای وقتی شواهدِ واقعی تناقض را نشان می‌دهند.
_ILLUSION_TITLE_WITH_CONTRADICTION = "شکارشده در تلهٔ فرمول و شهود"


def _apply_supremacy(status: str, findings: list[dict[str, str]], strong: bool) -> tuple[str, list[dict[str, str]], Optional[str]]:
    """قانون ۴: اگر عیب‌یابی قوی بود، حکمِ «نفهمیده» ارتقا می‌یابد.

    **اما** شاهدِ سختِ نقضِ کلماتِ ممنوعه پاک نمی‌شود: نمی‌توان هم‌زمان گفت
    «مفهوم را عمیقاً می‌داند» و «بدونِ اصطلاح نمی‌تواند حرف بزند». در آن حالت
    حکمِ JARGON_DEPENDENT می‌ماند و فقط یک یافتهٔ SYNERGY برای عیب‌یابی اضافه
    می‌شود.
    """
    if not strong:
        return status, findings, None
    if status == "JARGON_DEPENDENT":
        if not any("عیب‌یابی" in f["title"] for f in findings):
            findings = [
                {
                    "title": "عیب‌یابیِ منسجم، بیانِ زندانی",
                    "type": "SYNERGY",
                    "description": (
                        "استدلالِ تو در مرحله‌های دستکاری و عیب‌یابی درست بود — ساعتِ "
                        "مفهوم را بسته‌ای. مشکل در فهم نیست، در زندانِ اصطلاحات است."
                    ),
                }
            ] + findings
        return status, findings, (
            "استدلالِ تو در دستکاری و عیب‌یابی درست بود؛ سختیِ کار فقط در بیرون "
            "آمدن از زبانِ کتاب است."
        )
    if status in ("UNSTRUCTURED", "PARTIAL_FRAGMENTED"):
        note = (
            "استدلالِ تو در مرحله‌های دستکاری و عیب‌یابی درست و منسجم بود — "
            "«ساعت» را در ذهنت بسته‌ای. اگر در انتقالِ ساده کمی کوتاه آمدی یا "
            "به اصطلاح تکیه کردی، نشانهٔ نفهمیدن نیست."
        )
        if not any("عیب‌یابی" in f["title"] for f in findings):
            findings = [
                {
                    "title": "پیروزیِ عیب‌یابی بر بیانِ ضعیف",
                    "type": "SYNERGY",
                    "description": note,
                }
            ] + findings
        return "MASTERED", findings, note
    return status, findings, None


# ---------------------------------------------------------------------------
# تحلیل
# ---------------------------------------------------------------------------
def _answers_block(
    question_rows: list[dict[str, Any]],
    answers: dict[int, str],
    selected_indices: dict[int, int] | None = None,
) -> str:
    """بلوکِ پاسخ‌های ده‌گانه برای مدل.

    قاعدهٔ سخت (فاز ۱۰، حفظ‌شده در فاز ۱۱): پاسخِ تستی هرگز «بدون پاسخ»
    نمی‌رود. انتخابِ چهارگزینه‌ای در ``response_text`` نیست — در
    ``selected_option_index`` است.
    """
    chosen_map = selected_indices or {}
    chunks: list[str] = []
    seen_stages: set[int] = set()
    for row in sorted(question_rows, key=lambda r: int(r.get("order") or 0)):
        order = int(row.get("order") or 0)
        stage = int(row.get("stage") or stage_of_order(order))
        stage_slot = row.get("stage_slot") or ((order - 1) % QUESTIONS_PER_STAGE + 1)
        text_answer = (answers.get(order, "") or "").strip()
        options = row.get("options") or []
        chosen = _chosen_option(text_answer, options, chosen_map.get(order))
        correct = row.get("correct_option_index")

        lines: list[str] = [
            f"<<<STAGE {order}>>>  سؤال {order} "
            f"(مرحله {stage}، سؤال {stage_slot})  |  exam_type={row.get('exam_type')}"
        ]
        if stage not in seen_stages:
            seen_stages.add(stage)
            lines.append(f"— مرحلهٔ {stage}: {STAGE_TITLES_FA.get(stage, '')} —")
        lines.append(f"سؤال: {row.get('text') or ''}")

        if options:
            lines.append("گزینه‌ها: " + " | ".join(f"{i + 1}) {o}" for i, o in enumerate(options)))
            if correct is not None and 0 <= int(correct) < len(options):
                lines.append(f"گزینهٔ درست (محرمانه): {int(correct) + 1}) {options[int(correct)]}")
        forbidden = row.get("forbidden_words")
        if forbidden:
            lines.append("کلماتِ ممنوعه: " + "، ".join(forbidden))
        expected = row.get("expected_logic")
        if expected:
            lines.append(f"منطقِ موردانتظار: {expected}")

        if options:
            if chosen is None:
                lines.append(f"پاسخِ دانش‌آموز: {text_answer or '(بدون پاسخ)'}")
            else:
                matched = correct is not None and int(correct) == chosen
                label = (
                    f"مرحله ۲ (تست): دانش‌آموز گزینه [{chosen + 1}] با متن "
                    f"[{options[chosen]}] را انتخاب کرد."
                )
                if correct is not None and 0 <= int(correct) < len(options):
                    label += f" گزینه صحیح [{int(correct) + 1}] بود."
                    label += f" ⇒ انتخابِ او {'درست' if matched else 'نادرست'} است."
                lines.append(label)
                if text_answer:
                    lines.append(f"توضیحِ اختیاریِ دانش‌آموز (بر انتخاب اثر ندارد): {text_answer}")
        else:
            lines.append(f"پاسخِ دانش‌آموز: {text_answer or '(بدون پاسخ)'}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def _fallback_record(order: int, reason: str) -> dict[str, Any]:
    stage = stage_of_order(order)
    return {
        "question_id": None,
        "order": order,
        "stage": stage,
        "stage_slot": (order - 1) % QUESTIONS_PER_STAGE + 1,
        "stage_title": STAGE_TITLES_FA.get(stage, ""),
        "cognitive_verdict": reason,
        "missing_gear": None,
        "status": "INSUFFICIENT_EVIDENCE",
        "error_type": "none",
        "evidence_type": "weak_confirming",
        "reasoning": reason,
        "confidence": 0.0,
        "needs_teacher_review": True,
        "qualitative_feedback": reason,
    }


_TUTOR_FIELDS = ("misconception_root", "intuitive_explanation", "golden_tip")


def _coerce_tutor(raw: Any, record: dict[str, Any]) -> dict[str, str]:
    """آبجکتِ ``tutor_teaching`` را سالم می‌کند.

    مدل گاهی این آبجکت را نمی‌دهد (خروجیِ قدیمی، یا سؤالِ correct که از
    نظرش «نیازی نیست»). در آن حالت محتوای آموزشی از شواهدِ خودِ رکورد ساخته
    می‌شود تا دکمهٔ معلم هرگز به پنجرهٔ خالی نرسد — ولی **هیچ ادعای ساختگی
    دربارهٔ دانش‌آموز** اضافه نمی‌شود.
    """
    out: dict[str, str] = {}
    src = raw if isinstance(raw, dict) else {}
    for field in _TUTOR_FIELDS:
        value = str(src.get(field) or "").strip()
        out[field] = value

    status = canonical_stage_status(record.get("status"))
    verdict = str(record.get("cognitive_verdict") or "").strip()
    missed = str(record.get("expected_logic_missed") or "").strip()
    wrong = str(record.get("wrong_claim") or "").strip()

    if not out["misconception_root"]:
        if status == STAGE_STATUS_CORRECT:
            out["misconception_root"] = (
                "لغزشی نداشتی؛ پاسخت همان هستهٔ درست را داشت."
            )
        elif status == STAGE_STATUS_INSUFFICIENT:
            out["misconception_root"] = (
                "اینجا پاسخی نرسید، پس نتوانستیم ببینیم ذهنت کجا ایستاده است."
            )
        elif wrong:
            out["misconception_root"] = (
                f"ذهن اینجا روی این فرض ایستاد: «{wrong}» — و همین فرض، بقیهٔ "
                "استدلال را با خودش برد."
            )
        else:
            out["misconception_root"] = (
                verdict or "استدلال در میانهٔ راه ناقص ماند."
            )

    if not out["intuitive_explanation"]:
        if status == STAGE_STATUS_CORRECT:
            out["intuitive_explanation"] = (
                "همان مسیری را که رفتی، یک بار دیگر و کمی عمیق‌تر مرور کن: "
                "چرا این نتیجه ناگزیر از همان رابطه می‌آید؟"
            )
        else:
            core = missed or "هستهٔ منطقِ این سؤال"
            out["intuitive_explanation"] = (
                f"قدم‌به‌قدم پیش برو: اول ببین صورتِ سؤال چه می‌خواهد، بعد "
                f"همان رابطه را روی داده‌های مربوط به کار ببر — {core}."
            )

    if not out["golden_tip"]:
        out["golden_tip"] = (
            "قبل از هر محاسبه، یک بار با خودت بگو: «کدام کمیت واقعاً این‌جا "
            "نقش دارد و کدام یکی فقط تماشاچی است؟»"
        )
    return out


def _normalize_per_question(
    data: dict[str, Any],
    question_rows: list[dict[str, Any]],
    answers: dict[int, str] | None = None,
    selected_indices: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """رکوردهای per_question را کامل و مرتب می‌کند — هر **ده سؤال** رکورد می‌گیرد."""
    by_order = {int(q.get("order") or 0): q for q in question_rows}
    answered_orders = {
        int(o) for o, value in (answers or {}).items() if str(value or "").strip()
    }
    chosen_map = selected_indices or {}
    # انتخابِ گزینه هم «پاسخ» است؛ حتی اگر متنِ توضیح خالی باشد.
    for order, index in chosen_map.items():
        options = (by_order.get(int(order)) or {}).get("options") or []
        if index is not None and 0 <= int(index) < max(1, len(options)):
            answered_orders.add(int(order))

    records: dict[int, dict[str, Any]] = {}

    for item in data.get("per_question") or []:
        if not isinstance(item, dict):
            continue
        raw_order = item.get("order")
        raw_qid = item.get("question_id")
        order: Optional[int] = None
        try:
            if raw_order is not None:
                order = int(raw_order)
        except (TypeError, ValueError):
            order = None
        if order is None and raw_qid is not None:
            for candidate_order, row in by_order.items():
                if str(row.get("question_id")) == str(raw_qid):
                    order = candidate_order
                    break
        if order is None or order not in by_order:
            continue

        row = by_order.get(order) or {}
        stage = int(row.get("stage") or stage_of_order(order))
        missing = item.get("missing_gear")
        records[order] = {
            "question_id": row.get("question_id"),
            "order": order,
            "stage": stage,
            "stage_slot": row.get("stage_slot") or ((order - 1) % QUESTIONS_PER_STAGE + 1),
            "stage_title": row.get("stage_title") or STAGE_TITLES_FA.get(stage, ""),
            "evidence_quote": (str(item.get("evidence_quote")).strip() or None)
            if item.get("evidence_quote")
            else None,
            "wrong_claim": (str(item.get("wrong_claim")).strip() or None)
            if item.get("wrong_claim")
            else None,
            "expected_logic_missed": (str(item.get("expected_logic_missed")).strip() or None)
            if item.get("expected_logic_missed")
            else None,
            "student_answer_summary": str(item.get("student_answer_summary") or "").strip(),
            "diagnostic_insight": str(item.get("diagnostic_insight") or "").strip(),
            "cognitive_verdict": str(item.get("cognitive_verdict") or "").strip()
            or "تحلیل‌گر برای این سؤال توضیحی نداد.",
            "tutor_teaching_raw": item.get("tutor_teaching"),
            "missing_gear": (str(missing).strip() or None) if missing else None,
            "status": canonical_stage_status(item.get("status")),
            "error_type": str(item.get("error_type") or "none").strip(),
            "evidence_type": str(item.get("evidence_type") or "weak_confirming").strip(),
            "reasoning": str(item.get("reasoning") or item.get("cognitive_verdict") or "").strip(),
            "confidence": item.get("confidence", 0.5),
            "needs_teacher_review": bool(item.get("needs_teacher_review", False)),
            "qualitative_feedback": str(
                item.get("qualitative_feedback") or item.get("cognitive_verdict") or ""
            ).strip(),
        }

    # هر سؤالی که مدل تحلیلش نکرد، رکوردِ خالی می‌گیرد (نه سؤالِ گم‌شده).
    for order in sorted(by_order):
        if order not in records:
            records[order] = _fallback_record(
                order, "این سؤال تحلیل نشد یا پاسخی برایش ثبت نشده بود."
            )
            records[order]["stage"] = int(by_order[order].get("stage") or stage_of_order(order))
            records[order]["stage_slot"] = by_order[order].get("stage_slot") or (
                (order - 1) % QUESTIONS_PER_STAGE + 1
            )
            records[order]["stage_title"] = by_order[order].get("stage_title") or ""

    # ── سؤال‌های تستی: وضعیت فقط از تطابقِ اندیس با کلید ──
    # انتخابِ صریح فقط دو حالت دارد: درست یا نادرست — هرگز «بی‌پاسخ».
    for order, row in by_order.items():
        options = row.get("options") or []
        if not options:
            continue
        index = chosen_map.get(order)
        correct = row.get("correct_option_index")
        if index is None or correct is None:
            continue
        if not (0 <= int(index) < max(1, len(options))):
            continue
        record = records[order]
        matched = int(index) == int(correct)
        record["status"] = STAGE_STATUS_CORRECT if matched else STAGE_STATUS_WRONG
        record["evidence_type"] = "direct" if matched else "contradicting"
        record["confidence"] = 1.0
        chosen_text = options[int(index)]
        correct_text = (
            options[int(correct)] if 0 <= int(correct) < len(options) else ""
        )
        record["evidence_quote"] = (
            f"انتخابِ گزینهٔ {_fa_num(int(index) + 1)}: {chosen_text}"
        )
        if matched:
            record["cognitive_verdict"] = (
                f"رابطه را درست به کار برد و گزینهٔ {_fa_num(int(index) + 1)} "
                f"(«{chosen_text}») را انتخاب کرد."
            )
            record["qualitative_feedback"] = record["cognitive_verdict"]
            record["wrong_claim"] = None
        else:
            record["wrong_claim"] = (
                f"گزینهٔ {_fa_num(int(index) + 1)} («{chosen_text}») را انتخاب کرد، "
                f"در حالی که پاسخِ درست گزینهٔ {_fa_num(int(correct) + 1)} "
                f"(«{correct_text}») بود."
            )
            record["cognitive_verdict"] = (
                f"محاسبه را اشتباه انجام داد: {chosen_text} را انتخاب کرد، "
                f"اما رابطه به {correct_text} می‌رسد."
            )
            record["qualitative_feedback"] = record["cognitive_verdict"]

    # پاسخی که دانش‌آموز نداده (نه متن و نه گزینه) هرگز «درست» نیست.
    for order, record in records.items():
        if order not in answered_orders:
            record["status"] = STAGE_STATUS_INSUFFICIENT
            record["evidence_type"] = "none"
            record["confidence"] = 0.0

    # ── معلمِ هوشمند: بعد از نهایی‌شدنِ وضعیت، محتوای آموزشی سالم می‌شود ──
    # ترتیب مهم است: ``_coerce_tutor`` به ``status`` تکیه دارد، پس باید بعد از
    # همهٔ گاردها اجرا شود، نه داخلِ حلقهٔ ساخت.
    for order, record in records.items():
        record["tutor_teaching"] = _coerce_tutor(
            record.pop("tutor_teaching_raw", None), record
        )
    return [records[order] for order in sorted(records)]


def _filter_false_synergy(
    findings: list[dict[str, str]], per_question: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """SYNERGY فقط وقتی می‌ماند که دو مرحله واقعاً همسو و هر دو درست باشند.

    پرامپت از مدل می‌خواهد میانگینِ عددی و زنجیرهٔ علّی را «هم‌افزا» بنامد، ولی
    در اجرای زنده دیدیم که همین، حکمِ متناقض می‌سازد: کارتِ مرحلهٔ ۴ «نادرست»
    است و کنارش نوشته «هم‌افزاییِ کامل». یافته‌ای که با شواهدِ خودش نمی‌خواند
    حذف می‌شود.
    """
    if not findings:
        return findings
    statuses = {
        int(r.get("order") or 0): canonical_stage_status(r.get("status"))
        for r in per_question
    }
    # هم‌افزایی فقط دربارهٔ زوجِ «دستکاری + عیب‌یابی» معنا دارد؛ همان دو
    # مرحله‌ای که یافته به آن‌ها اشاره می‌کند. وضعیتِ بقیهٔ مرحله‌ها این‌جا
    # دخالت نمی‌کند (اگر لازم بود، حکمِ کلی جداگانه اصلاح می‌شود).
    if statuses.get(3) == STAGE_STATUS_CORRECT and statuses.get(4) == STAGE_STATUS_CORRECT:
        return findings
    return [f for f in findings if str(f.get("type", "")).upper() != "SYNERGY"]


def _usage_snapshot() -> dict[str, Any]:
    """جمعِ هزینه/توکنِ فراخوانی‌های همین آزمون — برای متادیتای گزارش."""
    try:
        from ai.model_abstraction import usage_summary

        return usage_summary()
    except Exception:  # noqa: BLE001
        return {}


def _hard_fallback(
    question_rows: list[dict[str, Any]], signals: dict[str, Any], reason: str
) -> dict[str, Any]:
    """اگر مدل هیچ خروجیِ قابل‌اتکایی نداد، قواعدِ قطعی تنها مرجع می‌شوند.

    نکتهٔ مهم: در این مسیر هیچ برچسبِ مرحله‌ای در دست نیست، پس **هیچ‌وقت**
    حکمِ MASTERED صادر نمی‌شود. «مسلط» ادعایی است که فقط با شاهدِ معناییِ
    مرحلهٔ ۳ و ۴ پشتیبانی می‌شود؛ نبودِ تحلیل یعنی نبودِ شاهد، نه تسلط.
    """
    findings: list[dict[str, str]] = []
    if signals["jargon_violated"]:
        findings.append(
            {
                "title": "شکستنِ قانونِ کلماتِ ممنوعه",
                "type": "JARGON_VIOLATION",
                "description": f"در توضیحِ ساده از «{'، '.join(signals['forbidden_hits'])}» استفاده کردی.",
            }
        )
    if signals["mostly_off_topic"]:
        findings.append(
            {
                "title": "پاسخ‌های خارج از موضوع",
                "type": "BLUFF_DETECTED",
                "description": (
                    "پاسخ‌هایت مفصل بود، اما به موضوعِ همین آزمون نمی‌پرداخت. "
                    "طولانی بودن، جای درست بودن را نمی‌گیرد."
                ),
            }
        )
    if signals["jargon_violated"]:
        status = "JARGON_DEPENDENT"
        persona = "معتاد به ادبیاتِ کتاب"
    elif signals["mostly_off_topic"]:
        status = "UNSTRUCTURED"
        persona = "پاسخ‌های طولانی، بیرون از موضوع"
    elif signals["mcq_correct"]:
        status = "ILLUSION_OF_COMPETENCE"
        persona = "گرفتارِ تضادِ فرمول و شهود"
    else:
        status = "PARTIAL_FRAGMENTED"
        persona = "تفکرِ جزیره‌ای"

    status, findings, note = _apply_supremacy(status, findings, False)

    return {
        "needs_interrogation": False,
        "interrogation": None,
        "needs_clarification": False,
        "clarification_data": None,
        "mastery_status": status,
        "persona_title": _STATUS_PERSONA.get(status) or persona,
        "mastery_note": note,
        "executive_summary": (
            "تحلیل‌گرِ هوش مصنوعی این بار خروجیِ قابل‌اتکایی نداد، اما پاسخ‌های تو "
            "با قواعدِ قطعیِ سیستم سنجیده شد. برای تحلیلِ عمیق‌تر، این آزمون را با "
            "معلم مرور کن."
        ),
        "cross_check_findings": _dedupe(findings),
        "per_question": [_fallback_record(o, reason) for o in range(1, TOTAL_QUESTIONS + 1)],
        "dimension_findings": [
            {"dimension": "تحلیلِ مقایسه‌ای", "status": "UNCLEAR", "finding": reason}
        ],
        "root_cause_hypotheses": [],
        "improvement_suggestions": [
            "این آزمون را با معلم مرور کن؛ تحلیلِ خودکار این بار کامل نبود."
        ],
        "signals": signals,
        "analyzer": "deterministic-fallback",
    }


async def analyze_stage_chain(
    concept_name: str,
    question_rows: list[dict[str, Any]],
    answers: dict[int, str],
    selected_indices: Optional[dict[int, int]] = None,
) -> dict[str, Any]:
    """زنجیرهٔ ۵ مرحله‌ای را به‌صورتِ کل‌نگر و مقایسه‌ای تحلیل می‌کند.

    ``question_rows``: [{"order", "exam_type", "stage_title", "text",
                          "options", "correct_option_index",
                          "forbidden_words", "expected_logic", "question_id"}]
    ``answers``: {order: response_text}

    هرگز استثنا پرتاب نمی‌کند — در شکستِ کاملِ مدل، قواعدِ قطعی حکم می‌دهند.
    """
    rows = [r for r in (question_rows or []) if isinstance(r, dict)]
    answers = {int(k): str(v or "") for k, v in (answers or {}).items()}
    signals = collect_signals(rows, answers, concept_name, selected_indices)

    expected = {
        int(r.get("order") or 0): r.get("expected_logic") or "" for r in rows
    }
    forbidden = {
        int(r.get("order") or 0): r.get("forbidden_words") or [] for r in rows
    }

    prompt = fill(
        _EXAM_PROMPT,
        concept_name=concept_name,
        expected_json=json.dumps(expected, ensure_ascii=False),
        forbidden_json=json.dumps(forbidden, ensure_ascii=False),
        answers_block=_answers_block(rows, answers, selected_indices),
    )

    data: Optional[dict[str, Any]] = None
    try:
        router = get_router()
        resp = await router.generate(prompt, "analyze_exam", temperature=0.3)
        data = extract_json_object(resp.text)
    except Exception as exc:  # noqa: BLE001
        print(f"[CrossCheck] model call failed: {exc}")

    if not isinstance(data, dict):
        return _hard_fallback(
            rows, signals, "خروجیِ مدل قابلِ ساختاردهی نبود؛ از قواعدِ قطعی استفاده شد."
        )

    status = str(data.get("mastery_status") or "").upper().strip()
    if status not in _VALID_STATUS:
        status = "PARTIAL_FRAGMENTED"

    # شواهدِ ساختاریافتهٔ هر مرحله *پیش از* حکمِ نهایی جمع می‌شود؛ حکمِ کلی
    # تابعِ همین شواهد است، نه مستقل از آن.
    per_question = _normalize_per_question(data, rows, answers, selected_indices)
    # گاردِ متن: اگر مدل Q4 را «درست» زد ولی خودِ پاسخ ادعای مفهومیِ غلطی دارد،
    # برچسب به HALF_CORRECT تنزل می‌کند. نتیجهٔ درست با استدلالِ غلط، درست نیست.
    q4_downgraded = apply_q4_claim_guard(per_question, answers)
    # قوتِ عیب‌یابی فقط از برچسبِ معناییِ Q3 و Q4 می‌آید. این متغیر محلی است،
    # نه سیگنالِ عمومی — تا هیچ مصرف‌کننده‌ای دوباره به شمارشِ کلمه برنگردد.
    debugging_strong = compute_debugging_strength(per_question, signals)

    # ── منبعِ واحدِ حقیقت برای حکم ──
    # حکمِ نهایی دیگر «حرفِ مدل + وصله‌پینه» نیست: از شواهدِ مرحله‌ای مشتق
    # می‌شود. هر بار که مدل چیزی جز این بگوید، در لاگ می‌بینیم.
    model_status = status
    status, verdict_note = derive_status(model_status, per_question, signals)
    if verdict_note or status != model_status:
        print(
            f"[CrossCheck] verdict derived from evidence: model={model_status} "
            f"-> final={status}"
        )

    findings = _clean_findings(data.get("cross_check_findings"))
    findings = _ensure_jargon_finding(findings, signals["forbidden_hits"])
    if q4_downgraded:
        findings.insert(0, {
            "title": "نتیجهٔ درست، استدلالِ غلط",
            "type": "BLUFF_DETECTED",
            "description": (
                "در مرحلهٔ عیب‌یابی نتیجهٔ درستی گفتی، اما دلیلی که آوردی خودش "
                "همان بدفهمی است: فرض کردی مقاومت با ولتاژ یا جریان عوض می‌شود. "
                "این مرحله حداکثر نیمه‌درست حساب می‌شود."
            ),
        })
    if signals["mostly_off_topic"] and not any(
        f["type"] == "BLUFF_DETECTED" for f in findings
    ):
        findings.insert(0, {
            "title": "پاسخ‌های خارج از موضوع",
            "type": "BLUFF_DETECTED",
            "description": (
                "بیشترِ پاسخ‌های تو مفصل بود، اما به موضوعِ همین آزمون نمی‌پرداخت. "
                "طولانی بودن، جای درست بودن را نمی‌گیرد."
            ),
        })
    # شاهدِ سخت: اگر در توضیحِ ساده کلمهٔ ممنوعه به کار رفته، سقفِ حکم
    # JARGON_DEPENDENT است — حتی اگر مدل از روی استدلالِ خوب «مسلط» گفته باشد.
    if signals["jargon_violated"] and status in ("MASTERED", "PARTIAL_FRAGMENTED", "UNSTRUCTURED"):
        status = "JARGON_DEPENDENT"
    status, findings, supremacy_note = _apply_supremacy(
        status, findings, debugging_strong
    )
    # پاسخِ بی‌ربطِ مفصل، استدلالِ خوب نیست. این گارد باید **بعد** از حاکمیتِ
    # عیب‌یابی بیاید تا مدل نتواند با SYNERGY خودش را به «مسلط» برساند.
    if signals["mostly_off_topic"]:
        status = "UNSTRUCTURED"
        supremacy_note = (
            "پاسخ‌هایت مفصل بود، اما به موضوعِ همین آزمون نمی‌پرداخت. "
            "اول باید مکانیزم را دقیقاً برای همین مفهوم بگویی."
        )
    findings = _dedupe(findings)
    findings = _filter_false_synergy(findings, per_question)

    # ── هماهنگیِ تیتر با باکسِ «شکارِ تناقض» (بندِ ۳) ──
    # اگر هیچ یافتهٔ CONTRADICTION ثبت نشده، تیتر نباید ادعای تله/تناقض کند.
    has_contradiction = any(f.get("type") == "CONTRADICTION" for f in findings)
    contradiction_noted = any(
        "تناقض" in str(f.get("title") or "") or "تله" in str(f.get("title") or "")
        for f in findings
    )

    raw_persona = str(data.get("persona_title") or "").strip()
    # عنوان، خلاصه، یافته‌ها و نشان باید یک داستان بگویند. هر بار که کد حکم را
    # بازنویسی کرده باشد (سازگارسازی، حاکمیت، بی‌ربطی)، عنوانِ خودِ مدل کنار
    # می‌رود — وگرنه کارتی می‌بینیم که نشانش «مسلط» است و خلاصه‌اش «ناقص».
    verdict_rewritten = bool(supremacy_note or verdict_note or signals["mostly_off_topic"])
    persona_title = (
        raw_persona
        if raw_persona and not verdict_rewritten
        else (_STATUS_PERSONA.get(status) or raw_persona or "نقشهٔ ذهنیِ نامنظم")
    )
    if signals["mostly_off_topic"]:
        persona_title = _STATUS_PERSONA["UNSTRUCTURED"]

    # اگر عنوان ادعای «تله/تناقض» دارد ولی هیچ تناقضی در شواهد نیست، دروغ است.
    if (has_contradiction or contradiction_noted) and status == "ILLUSION_OF_COMPETENCE":
        persona_title = _ILLUSION_TITLE_WITH_CONTRADICTION
    elif status == "ILLUSION_OF_COMPETENCE" and not (has_contradiction or contradiction_noted):
        persona_title = _STATUS_PERSONA["ILLUSION_OF_COMPETENCE"]

    # خلاصهٔ مدل ممکن است با حکمِ اصلاح‌شده در تضاد باشد («مسلط» + «اما در
    # نقد استدلال لنگ زدی»). در آن حالت خلاصهٔ سازگار با شواهد نوشته می‌شود.
    executive_summary = str(data.get("executive_summary") or "").strip()
    if verdict_rewritten:
        # «ضعیف‌ترین حلقه» یعنی حلقه‌ای که واقعاً حکم را برگرداند — نه هر
        # مرحله‌ای که خالی مانده. اگر Q4 نیمه‌درست است، همان دلیلِ اصلی است.
        culprit = _verdict_culprit(per_question)
        stage_name = (
            culprit.get("stage_title") or _NAMES.get(int(culprit.get("order") or 0), "")
            if culprit
            else ""
        )
        executive_summary = _summary_from_stages(
            per_question, status, culprit, verdict_note or supremacy_note
        )
    if signals["mostly_off_topic"]:
        persona_title = _STATUS_PERSONA["UNSTRUCTURED"]

    # ── فاز ۱۱: «بازپرس / رفعِ ابهام» (سؤالِ اختیاریِ ۱۱ام) ──
    # کلیدهای تازه (needs_interrogation / interrogation) پذیرفته می‌شوند و
    # کلیدهای قدیمی (needs_clarification / clarification_data) هم برایِ
    # سازگاری خوانده می‌شوند. خروجی هر دو نام را دارد.
    needs = bool(data.get("needs_interrogation") or data.get("needs_clarification"))
    raw_interro = data.get("interrogation") or data.get("clarification_data") or {}
    interrogation: Optional[dict[str, Any]] = None
    if isinstance(raw_interro, dict):
        mirror = str(raw_interro.get("mirror_prompt") or "").strip()
        question = str(raw_interro.get("question") or "").strip()
        contradicting = []
        for value in raw_interro.get("contradicting_questions") or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            # شمارهٔ سؤال (۱..۱۰) یا شمارهٔ مرحله (۱..۵) — هر دو پذیرفته‌اند.
            if 1 <= number <= TOTAL_QUESTIONS:
                contradicting.append(number)
        if mirror or question:
            interrogation = {
                "contradicting_questions": contradicting[:4],
                "mirror_prompt": mirror or question,
                "question": question or "کدام یکی را واقعاً باور داری؟",
            }
    # بازپرسی بدونِ متنِ آینه‌ای، دانش‌آموز را در بن‌بست می‌گذارد.
    if needs and interrogation is None:
        needs = False
    # یافتهٔ CONTRADICTION یا به بازپرسی می‌رسد یا وجود ندارد. تناقضی که از
    # دانش‌آموز پرسیده نشود، در کارنامه حکمِ صادرشده می‌ماند و بی‌انصافی است.
    if not needs:
        findings = [f for f in findings if f["type"] != "CONTRADICTION"]
    # حکمِ «تسلط» همراهِ بازپرسیِ باز، متناقض است.
    if needs and status == "MASTERED":
        status = "PARTIAL_FRAGMENTED"

    suggestions = normalize_suggestions(data.get("improvement_suggestions"))[:6]
    if not suggestions:
        suggestions = [
            "همان پدیده را برای یک بچهٔ ۱۰ ساله، بدونِ هیچ اصطلاحِ تخصصی، بازگو کن."
        ]

    return {
        "needs_interrogation": needs,
        "interrogation": interrogation,
        # سازگاریِ عقب‌رو با مصرف‌کننده‌های قدیمی
        "needs_clarification": needs,
        "clarification_data": interrogation,
        "mastery_status": status,
        "persona_title": persona_title,
        "executive_summary": executive_summary,
        "cross_check_findings": findings,
        "per_question": per_question,
        "dimension_findings": data.get("dimension_findings") or [],
        "root_cause_hypotheses": data.get("root_cause_hypotheses") or [],
        "improvement_suggestions": suggestions,
        "mastery_note": supremacy_note,
        "signals": signals,
        "analyzer": "cross-check",
        # مصرفِ مدل برای همین آزمون (مدل، توکنِ ورودی/خروجی، هزینهٔ گزارش‌شده)
        "ai_usage": _usage_snapshot(),
    }
