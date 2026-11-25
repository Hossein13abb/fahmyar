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
from ai.prompt_safe import fill

# ---------------------------------------------------------------------------
# قالبِ پرامپت — بدونِ .format()
# ---------------------------------------------------------------------------
_EXAM_PROMPT = r"""شما «کارآگاهِ علوم شناختیِ فهم‌یار» هستید.
وظیفهٔ شما تصحیحِ تک‌به‌تکِ سؤالات مثل یک معلمِ سنتی نیست.
وظیفهٔ شما **مقایسهٔ پاسخ‌های دانش‌آموز با یکدیگر (Cross-Checking)** و کشفِ تناقض‌های پنهان در ذهنِ اوست.

این آزمون یک «زنجیرهٔ ۵ مرحله‌ای» است، نه پنج سؤالِ مستقل:
  مرحله ۱ (philosophy):       فلسفه و مکانیزمِ ریشه‌ای، بدونِ فرمول
  مرحله ۲ (mask_mcq):         تستِ استاندارد — «لایهٔ نقاب»
  مرحله ۳ (perturbation):     دستکاریِ سیستم، بدونِ عدد
  مرحله ۴ (debugging):        نقدِ یک استدلالِ غلطِ ظاهراً علمی — شاه‌کلید
  مرحله ۵ (feynman_synthesis): توضیح برای بچهٔ ۱۰ ساله، با کلماتِ ممنوعه

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
     "status": "CORRECT | HALF_CORRECT | WRONG | INSUFFICIENT_EVIDENCE",
     "cognitive_verdict": "یک جمله: چه چیزی را فهمیده و چه چیزی را نه",
     "expected_logic_missed": "کدام بخشِ منطقِ موردانتظار غایب است (اگر کامل است، null)",
     "evidence_type": "strong_confirming | weak_confirming | contradicting | none",
     "missing_gear": "چرخ‌دندهٔ غایب در ذهن (یا null)",
     "confidence": 0.0}
  ],
  "dimension_findings": [],
  "root_cause_hypotheses": [],
  "improvement_suggestions": []
}

قواعدِ status (اجباری، برای همان پنج مرحله):
  - CORRECT: پاسخ همان هستهٔ منطقیِ expected_logic را دارد.
  - HALF_CORRECT: بخشی از استدلال درست است ولی هستهٔ منطقِ موردانتظار غایب
    یا ناقص است. **پاسخِ درست در نتیجه ولی بدونِ توضیحِ چرایی = HALF_CORRECT.**
  - WRONG: پاسخ به نتیجهٔ نادرست می‌رسد یا بدفهمی را تأیید می‌کند.
  - INSUFFICIENT_EVIDENCE: پاسخی نیست، یا پاسخ هیچ ادعای قابلِ‌سنجش ندارد.
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


def _chosen_option(answer: str, options: list[str]) -> Optional[int]:
    """اندیسِ گزینهٔ انتخاب‌شده — متنِ گزینه اولویت دارد، عدد یک‌پایه است."""
    if not answer or not options:
        return None
    text = _normalize(answer)
    for index, option in enumerate(options):
        if _normalize(option) == text:
            return index
    stripped = str(answer).strip()
    if stripped.isdigit():
        value = int(stripped)
        if 1 <= value <= len(options):
            return value - 1
    # «گزینهٔ ۲» یا «2) ...»
    match = re.search(r"(?:گزینه\s*)?([۱-۹\d])", stripped)
    if match:
        digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
        value = int(match.group(1).translate(digits))
        if 1 <= value <= len(options):
            return value - 1
    return None


# ---------------------------------------------------------------------------
# سیگنال‌های قطعی — به مدل داده می‌شوند و در لاگ می‌مانند
# ---------------------------------------------------------------------------
_SUGGESTION_KEYS = ("suggestion", "text", "description", "title", "action", "advice")


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
        if cleaned not in out:
            out.append(cleaned)
    return out


def collect_signals(
    question_rows: list[dict[str, Any]],
    answers: dict[int, str],
    concept_name: str = "",
) -> dict[str, Any]:
    """سیگنال‌های ساختاری که بدونِ مدل هم قابلِ محاسبه‌اند."""
    by_order = {int(q.get("order") or 0): q for q in question_rows}
    q2 = by_order.get(2) or {}
    options = q2.get("options") or []
    chosen = _chosen_option(answers.get(2, ""), options)
    correct = q2.get("correct_option_index")
    mcq_correct = (
        chosen is not None and correct is not None and int(chosen) == int(correct)
    )

    q5 = by_order.get(5) or {}
    forbidden = list(q5.get("forbidden_words") or [])
    hits = find_forbidden_hits(answers.get(5, ""), forbidden)

    substantive = {
        order: _word_count(answers.get(order, "")) >= 15 for order in (1, 3, 4)
    }

    # توجه: «طولِ پاسخ» هیچ‌جا شاهدِ درستی نیست. پیش‌تر `debugging_strong`
    # از شمارشِ کلمات ساخته می‌شد و همین باعثِ حکمِ کاذبِ «مسلط» بود: پاسخِ
    # بلندِ نیمه‌درست یا حتی بی‌ربط، «قوی» شمرده می‌شد. اکنون قوتِ عیب‌یابی
    # فقط از حکمِ معناییِ مرحله‌های ۳ و ۴ می‌آید (compute_debugging_strength).

    # سیگنالِ «بی‌ربط»: پاسخِ مفصل که هیچ واژهٔ کلیدیِ مفهوم را در خود ندارد.
    # مدل‌ها در پاسخِ off-topic استدلالِ قویِ بی‌ربط می‌بینند و «SYNERGY» می‌دهند؛
    # این سیگنال جلوی حکمِ «مسلط» را می‌گیرد.
    key_terms: list[str] = []
    concept_tokens = [
        t for t in _normalize(concept_name).split() if len(t) > 3
    ]
    key_terms.extend(concept_tokens)
    for row in question_rows:
        for proposition in row.get("mapped_propositions") or []:
            key_terms.extend(t for t in _normalize(str(proposition)).split() if len(t) > 4)
        expected = _normalize(str(row.get("expected_logic") or ""))
        key_terms.extend(t for t in expected.split() if len(t) > 4)
    unique_terms = list(dict.fromkeys(key_terms))[:40]

    off_topic_orders: list[int] = []
    for order in (1, 3, 4, 5):
        text = _normalize(answers.get(order, ""))
        if _word_count(text) < 15:
            continue
        if unique_terms and not any(term in text for term in unique_terms):
            off_topic_orders.append(order)
    detailed = [o for o in (1, 3, 4, 5) if _word_count(answers.get(o, "")) >= 15]
    mostly_off_topic = bool(detailed) and len(off_topic_orders) >= max(1, len(detailed) - 1)

    return {
        "chosen_option": chosen,
        "correct_option": correct,
        "mcq_correct": mcq_correct,
        "forbidden_words": forbidden,
        "forbidden_hits": hits,
        "jargon_violated": bool(hits),
        "substantive": substantive,
        "any_substantive": any(substantive.values()),
        # پاسخِ مرتبط و غیرِبی‌ربط برای مرحله‌های ۳ و ۴ — لازم ولی ناکافی.
        # این فقط «شرطِ لازم» است؛ درستیِ محتوایی جداگانه سنجیده می‌شود.
        "relevant_semantic_answers": (
            3 not in off_topic_orders and 4 not in off_topic_orders
        ),
        # در `_hard_fallback` جایگزین می‌شود؛ این‌جا عمداً False است تا هیچ‌کس
        # از شمارشِ کلمه به «تسلط» نرسد.
        "debugging_strong": False,
        "off_topic_orders": off_topic_orders,
        "mostly_off_topic": mostly_off_topic,
        "answered_orders": sorted(o for o in answers if _normalize(answers.get(o, ""))),
        "word_counts": {o: _word_count(answers.get(o, "")) for o in (1, 2, 3, 4, 5)},
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


def compute_debugging_strength(
    per_question: list[dict[str, Any]], signals: dict[str, Any]
) -> bool:
    """«قوی» یعنی: مرحله ۳ درست **و** مرحله ۴ حداقل نیمه‌درست — معنایی.

    هیچ‌جای این تابع به طولِ پاسخ یا تعدادِ کلمه نگاه نمی‌شود. پاسخِ بلند و
    بی‌ربط، یا پاسخی که فقط دلالتِ حاصل‌ضرب را تکرار می‌کند و «چرا» را
    توضیح نمی‌دهد، از این دروازه رد نمی‌شود.
    """
    by_order = {int(r.get("order") or 0): r for r in per_question}
    q3 = canonical_stage_status(by_order.get(3, {}).get("status"))
    q4 = canonical_stage_status(by_order.get(4, {}).get("status"))
    # مرحلهٔ ۴ باید «درست» باشد، نه فقط نیمه‌درست: نیمه‌درست یعنی دقیقاً
    # هستهٔ نقد را نگفته است — و همان هسته، دلیلِ وجودِ مرحله ۴ است.
    sem_ok = q3 == STAGE_STATUS_CORRECT and q4 == STAGE_STATUS_CORRECT
    return bool(sem_ok and signals.get("relevant_semantic_answers", True))


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
    "ILLUSION_OF_COMPETENCE": "شکارشده در تلهٔ فرمول و شهود",
    "JARGON_DEPENDENT": "زندانیِ اصطلاحاتِ کتاب",
    "PARTIAL_FRAGMENTED": "تفکرِ جزیره‌ای",
    "UNSTRUCTURED": "بی‌ساختار — پاسخ‌ها بیرون از موضوع",
}


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
def _answers_block(question_rows: list[dict[str, Any]], answers: dict[int, str]) -> str:
    chunks: list[str] = []
    for row in sorted(question_rows, key=lambda r: int(r.get("order") or 0)):
        order = int(row.get("order") or 0)
        answer = answers.get(order, "") or "(بدون پاسخ)"
        stage = row.get("stage_title") or _NAMES.get(order, f"مرحله {order}")
        lines = [
            f"<<<STAGE {order}>>>  {stage}  |  exam_type={row.get('exam_type')}",
            f"سؤال: {row.get('text') or ''}",
        ]
        options = row.get("options")
        if options:
            lines.append("گزینه‌ها: " + " | ".join(f"{i + 1}) {o}" for i, o in enumerate(options)))
            correct = row.get("correct_option_index")
            if correct is not None:
                lines.append(f"گزینهٔ درست (محرمانه): {int(correct) + 1}) {options[int(correct)]}")
        forbidden = row.get("forbidden_words")
        if forbidden:
            lines.append("کلماتِ ممنوعه: " + "، ".join(forbidden))
        expected = row.get("expected_logic")
        if expected:
            lines.append(f"منطقِ موردانتظار: {expected}")
        lines.append(f"پاسخِ دانش‌آموز: {answer}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def _fallback_record(order: int, reason: str) -> dict[str, Any]:
    return {
        "question_id": None,
        "order": order,
        "stage_title": _NAMES.get(order, f"مرحله {order}"),
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


def _normalize_per_question(
    data: dict[str, Any],
    question_rows: list[dict[str, Any]],
    answers: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """رکوردهای per_question را کامل و مرتب می‌کند — هر پنج مرحله باید رکورد داشته باشند."""
    by_order = {int(q.get("order") or 0): q for q in question_rows}
    answered_orders = {
        int(o) for o, value in (answers or {}).items() if str(value or "").strip()
    }
    records: dict[int, dict[str, Any]] = {}

    for item in data.get("per_question") or []:
        if not isinstance(item, dict):
            continue
        raw_order = item.get("order")
        raw_qid = item.get("question_id")
        # ترتیب اولویت: order صریح، بعد نگاشتِ question_id به order
        order = None
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
        if order is None or order not in range(1, 6):
            continue

        row = by_order.get(order) or {}
        missing = item.get("missing_gear")
        record = {
            "question_id": row.get("question_id"),
            "order": order,
            "stage_title": row.get("stage_title") or _NAMES.get(order, f"مرحله {order}"),
            "cognitive_verdict": str(item.get("cognitive_verdict") or "").strip()
            or "تحلیل‌گری برای این مرحله توضیحی نداد.",
            "missing_gear": (str(missing).strip() or None) if missing else None,
            # وضعیت به چهار حالتِ استاندارد نگاشت می‌شود تا جمع‌بندیِ کد
            # به برچسبِ دلخواهِ مدل وابسته نباشد.
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
        records[order] = record

    for order in range(1, 6):
        if order not in records:
            records[order] = _fallback_record(
                order, "این مرحله تحلیل نشد یا پاسخی برایش ثبت نشده بود."
            )
    # پاسخی که دانش‌آموز نداده (یا خالی فرستاده) هرگز «درست» نیست.
    for order, record in records.items():
        if order not in answered_orders:
            record["status"] = STAGE_STATUS_INSUFFICIENT
            record["evidence_type"] = "none"
            record["confidence"] = 0.0
    return [records[order] for order in sorted(records)]

    return [records[order] for order in sorted(records)]


def _hard_fallback(
    question_rows: list[dict[str, Any]], signals: dict[str, Any], reason: str
) -> dict[str, Any]:
    """اگر مدل هیچ خروجیِ قابل‌اتکایی نداد، قواعدِ قطعی تنها مرجع می‌شوند."""
    findings: list[dict[str, str]] = []
    if signals["jargon_violated"]:
        findings.append(
            {
                "title": "شکستنِ قانونِ کلماتِ ممنوعه",
                "type": "JARGON_VIOLATION",
                "description": f"در توضیحِ ساده از «{'، '.join(signals['forbidden_hits'])}» استفاده کردی.",
            }
        )
    if signals["debugging_strong"]:
        findings.append(
            {
                "title": "عیب‌یابیِ منسجم",
                "type": "SYNERGY",
                "description": "استدلالِ تو در مرحله‌های دستکاری و عیب‌یابی مفصل و منسجم بود.",
            }
        )
    if signals["jargon_violated"]:
        status = "JARGON_DEPENDENT"
        persona = "معتاد به ادبیاتِ کتاب"
    elif signals["mostly_off_topic"]:
        status = "UNSTRUCTURED"
        persona = "پاسخ‌های طولانی، بیرون از موضوع"
    elif signals["debugging_strong"]:
        status = "MASTERED"
        persona = "معماری که ساعت را بست"
    elif signals["mcq_correct"]:
        status = "ILLUSION_OF_COMPETENCE"
        persona = "گرفتارِ تضادِ فرمول و شهود"
    else:
        status = "PARTIAL_FRAGMENTED"
        persona = "تفکرِ جزیره‌ای"

    status, findings, note = _apply_supremacy(status, findings, signals["debugging_strong"])

    return {
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
        "per_question": [_fallback_record(o, reason) for o in range(1, 6)],
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
    signals = collect_signals(rows, answers, concept_name)

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
        answers_block=_answers_block(rows, answers),
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
    per_question = _normalize_per_question(data, rows, answers)
    signals["debugging_strong"] = compute_debugging_strength(per_question, signals)

    # گاردِ سازگاری: مدل می‌تواند کلی «مسلط» بدهد درحالی‌که خودش مرحلهٔ ۴ را
    # نیمه‌درست علامت زده. حکم باید یکی باشد؛ شواهدِ مرحله‌ای مقدم است.
    conflict = _verdict_conflict(status, per_question)
    verdict_note: Optional[str] = None
    if conflict:
        status = (
            "ILLUSION_OF_COMPETENCE"
            if signals.get("mcq_correct") and not signals.get("jargon_violated")
            else "PARTIAL_FRAGMENTED"
        )
        verdict_note = conflict
        print(f"[CrossCheck] verdict reconciled with per-stage evidence: {conflict}")

    findings = _clean_findings(data.get("cross_check_findings"))
    findings = _ensure_jargon_finding(findings, signals["forbidden_hits"])
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
        status, findings, signals["debugging_strong"]
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

    # خلاصهٔ مدل ممکن است با حکمِ اصلاح‌شده در تضاد باشد («مسلط» + «اما در
    # نقد استدلال لنگ زدی»). در آن حالت خلاصهٔ سازگار با شواهد نوشته می‌شود.
    executive_summary = str(data.get("executive_summary") or "").strip()
    if verdict_rewritten:
        weakest = _weakest_link(per_question)
        stage_name = (
            weakest.get("stage_title") or _NAMES.get(int(weakest.get("order") or 0), "")
            if weakest
            else ""
        )
        if stage_name:
            executive_summary = (
                f"ضعیف‌ترین حلقهٔ زنجیرهٔ تو «{stage_name}» بود. "
                "بقیهٔ مرحله‌ها خوب پیش رفتند، اما تسلطِ کامل وقتی ساخته "
                "می‌شود که همین حلقه هم بسته شود."
            )
        else:
            executive_summary = verdict_note or supremacy_note or executive_summary
    if signals["mostly_off_topic"]:
        persona_title = _STATUS_PERSONA["UNSTRUCTURED"]

    needs = bool(data.get("needs_clarification"))
    clar_raw = data.get("clarification_data") or {}
    clarification: Optional[dict[str, Any]] = None
    if isinstance(clar_raw, dict):
        mirror = str(clar_raw.get("mirror_prompt") or "").strip()
        contradicting = []
        for value in clar_raw.get("contradicting_questions") or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= 5:
                contradicting.append(number)
        if mirror:
            clarification = {
                "contradicting_questions": contradicting[:3],
                "mirror_prompt": mirror,
            }
    # بازپرسی بدونِ متنِ آینه‌ای، دانش‌آموز را در بن‌بست می‌گذارد.
    if needs and clarification is None:
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
        "needs_clarification": needs,
        "clarification_data": clarification,
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
    }
