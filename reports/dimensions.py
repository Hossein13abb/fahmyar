"""ابعادِ فهم — اسکیمای *قطعی* و مشترکِ بک‌اند و فرانت‌اند (فاز ۱۰).

چرا این ماژول ساخته شد
----------------------
نسخهٔ قبلی «ابعاد فهم — تحلیل کلی» را از ``dimension_findings`` می‌ساخت که
مدل با کلیدهای آزاد و نام‌های دلخواه برمی‌گرداند. فرانت‌اند پنج کلیدِ ثابت
انتظار داشت، بک‌اند چیزی جز «تحلیل ابعادی انجام نشد»/``UNCLEAR`` نمی‌داد، و
نتیجه این بود که هر پنج بعد «نامشخص» و بی‌محتوا نمایش داده می‌شدند.

حالا پنج بعد **از شواهدِ واقعیِ پنج مرحله** ساخته می‌شوند: هر بعد دقیقاً یک
مرحله را می‌سنجد، وضعیتش از برچسبِ همان مرحله می‌آید، و کلیدها ثابت‌اند:

    conceptual_knowledge    ← مرحلهٔ ۱ (فلسفه و تصویر کلان)
    distractor_resistance   ← مرحلهٔ ۲ (تستِ لایهٔ نقاب)
    causal_reasoning        ← مرحلهٔ ۳ (دستکاریِ سیستم)
    critical_debugging      ← مرحلهٔ ۴ (عیب‌یابی)
    simple_communication    ← مرحلهٔ ۵ (چالشِ فاینمن)

«نامشخص» فقط وقتی در کار می‌آید که دانش‌آموز واقعاً آن مرحله را خالی رها
کرده باشد؛ و آن حالت هم با وضعیتِ صریحِ ``not_assessed`` («بدون پاسخ») بیان
می‌شود، نه با برچسبِ مبهمِ «نامشخص».
"""
from __future__ import annotations

from typing import Any, Optional

#: وضعیت‌های مجازِ هر بعد — اسکیمای مشترک با فرانت‌اند (ReportView.jsx).
DIMENSION_STATUSES: tuple[str, ...] = ("mastered", "developing", "needs_work", "not_assessed")

DIMENSION_STATUS_FA: dict[str, str] = {
    "mastered": "تسلط",
    "developing": "در حال رشد",
    "needs_work": "نیازمند کار",
    "not_assessed": "بدون پاسخ",
}

#: هر بُعد + عنوانِ دانش‌آموزپسند + زیرعنوان (مهارتِ شناختیِ سنجیده‌شده).
#:
#: نام‌های تازه (فاز ۳۰) از زبانِ درونیِ سنجش بیرون آمده‌اند: «دانش مفهومی»
#: برای یک دانش‌آموزِ دبیرستانی چیزی نمی‌گوید، ولی «شهود و درک تصویر کلان»
#: دقیقاً می‌گوید چه مهارتی سنجیده شده و چرا مهم است.
STAGE_DIMENSIONS: tuple[tuple[int, str, str, str], ...] = (
    (1, "conceptual_knowledge", "شهود و درک تصویر کلان",
     "درکِ چرایی و فلسفهٔ مفهوم"),
    (2, "distractor_resistance", "تشخیص متغیرِ اصلی از دادهٔ فریبنده",
     "تواناییِ تفکیکِ اطلاعاتِ مهم از مزاحم"),
    (3, "causal_reasoning", "پیش‌بینیِ علت‌ومعلولیِ رفتارِ پدیده",
     "تحلیلِ تغییراتِ سیستم بدونِ عدد و فرمول"),
    (4, "critical_debugging", "شناساییِ خطا در استدلال‌های علمی",
     "پیدا کردنِ باگِ مفهومی در راه‌حل‌های به‌ظاهر درست"),
    (5, "simple_communication", "ساده‌سازی و انتقال به زبانِ خودمانی",
     "تواناییِ بیانِ مفهوم به ساده‌ترین شکلِ ممکن"),
)

#: شناسهٔ کوتاهِ هر بُعد — همان چیزی که کامپوننتِ کارت انتظار دارد.
DIMENSION_SHORT_IDS: dict[str, str] = {
    "conceptual_knowledge": "intuition",
    "distractor_resistance": "noise_filter",
    "causal_reasoning": "causal",
    "critical_debugging": "critical",
    "simple_communication": "teaching",
}

#: وضعیتِ سه‌سطحی که کارتِ کارنامه نشان می‌دهد (برچسبِ عمومی، بدونِ درصدِ نمره).
MASTERY_LEVELS: tuple[str, ...] = ("mastered", "shaky", "needs_work")

_MASTERY_FROM_STATUS: dict[str, str] = {
    "mastered": "mastered",
    "developing": "shaky",
    "needs_work": "needs_work",
}

#: امتیازِ شاهد‌محور برای نوارِ پیشرفت — فقط از روی پاسخ‌های واقعیِ همان بُعد.
#: هیچ عددِ ساختگی‌ای در کار نیست: اگر دانش‌آموز به بُعدی پاسخ نداده باشد،
#: نتیجه ``None`` است و کارت اصلاً رندر نمی‌شود.
_STATUS_SCORE: dict[str, int] = {
    "CORRECT": 100,
    "HALF_CORRECT": 50,
    "WRONG": 0,
}

#: نگاشتِ برچسبِ مرحله → وضعیتِ بعد. «نامشخص» در این جدول وجود ندارد.
_STATUS_MAP: dict[str, str] = {
    "CORRECT": "mastered",
    "HALF_CORRECT": "developing",
    "WRONG": "needs_work",
    "INSUFFICIENT_EVIDENCE": "not_assessed",
}

#: جملهٔ تحلیلی به تفکیک (کلیدِ بُعد، وضعیت) — دوم‌شخص، بدونِ شمارهٔ مرحله.
#:
#: فاز ۳۰: نسخهٔ قبلی می‌نوشت «به این مرحله پاسخی نداده است» و دانش‌آموز
#: مجبور بود حدس بزند «این مرحله» کدام است. حالا هر جمله خودکفاست: می‌گوید
#: در این مهارت چه دیدیم و چرا.
_FINDINGS: dict[tuple[str, str], str] = {
    # ── ۱) شهود و درکِ تصویرِ کلان ──
    ("conceptual_knowledge", "mastered"):
        "تصویرِ کلیِ مفهوم را در ذهن داری و می‌دانی چرا این مفهوم اصلاً به وجود آمده — نه فقط اسم و تعریفش.",
    ("conceptual_knowledge", "developing"):
        "جهتِ کلیِ مفهوم را می‌شناسی، اما وقتی می‌پرسیم چرا این مفهوم لازم شد، جوابت نیمه‌کاره می‌ماند.",
    ("conceptual_knowledge", "needs_work"):
        "مفهوم را مجموعه‌ای از تعریف‌های جدا از هم می‌بینی، پس جایی برای وصل کردنِ «چرا» پیدا نمی‌کنی.",
    ("conceptual_knowledge", "not_assessed"):
        "به سؤالِ شهودی پاسخی ندادی، پس تصویرِ کلیِ ذهنت در این مفهوم سنجیده نشد.",
    # ── ۲) تشخیصِ متغیرِ اصلی از دادهٔ فریبنده ──
    ("distractor_resistance", "mastered"):
        "دادهٔ مزاحم را شناختی و کنار گذاشتی و رابطه را فقط روی اطلاعاتِ واقعاً مرتبط سنجیدی.",
    ("distractor_resistance", "developing"):
        "مسیرِ درست را می‌دانستی، اما دادهٔ اضافی حواست را پرت کرد و محاسبه را از جوابِ درست دور کرد.",
    ("distractor_resistance", "needs_work"):
        "اطلاعاتِ نامرتبط را با دادهٔ اصلی اشتباه گرفتی؛ همین باعث شد رابطهٔ درست هم به جوابِ غلط برسد.",
    ("distractor_resistance", "not_assessed"):
        "گزینه‌ای انتخاب نکردی، پس توانایی‌ات در جدا کردنِ دادهٔ مهم از مزاحم سنجیده نشد.",
    # ── ۳) پیش‌بینیِ علت‌ومعلولی ──
    ("causal_reasoning", "mastered"):
        "زنجیره را حلقه‌به‌حلقه چیدی: چه چیزی تغییر کرد، چه چیزی از آن تغییر کرد، و چرا نتیجه عوض شد.",
    ("causal_reasoning", "developing"):
        "نتیجهٔ نهایی را درست گفتی، اما حلقه‌های میانی را جا انداختی؛ یعنی به جواب رسیدی بدونِ اینکه مسیرش را توضیح بدهی.",
    ("causal_reasoning", "needs_work"):
        "جهتِ رابطه را برعکس یا ناقص بیان کردی؛ از تغییرِ ورودی به نتیجهٔ درست نرسیدی.",
    ("causal_reasoning", "not_assessed"):
        "به سؤالِ پیش‌بینیِ رفتار پاسخ ندادی، پس توانایی‌ات در دیدنِ رابطهٔ علت و معلول سنجیده نشد.",
    # ── ۴) شناساییِ خطا در استدلال ──
    ("critical_debugging", "mastered"):
        "هستهٔ استدلالِ غلط را پیدا کردی و دقیقاً گفتی کدام فرض اشتباه است.",
    ("critical_debugging", "developing"):
        "فهمیدی چیزی می‌لنگد، ولی نتوانستی بگویی چه چیزی؛ نقدت در سطحِ «اشتباه است» ماند.",
    ("critical_debugging", "needs_work"):
        "استدلالِ غلط را نپذیرفتی یا خودت هم در همان دام افتادی؛ ریشهٔ خطا دست‌نخورده ماند.",
    ("critical_debugging", "not_assessed"):
        "به سؤالِ بررسیِ استدلال پاسخ ندادی، پس توانایی‌ات در پیدا کردنِ خطا سنجیده نشد.",
    # ── ۵) ساده‌سازی و انتقال ──
    ("simple_communication", "mastered"):
        "مفهوم را بدونِ اصطلاحِ تخصصی و با مثالی که درست به مفهوم وصل می‌شود توضیح دادی.",
    ("simple_communication", "developing"):
        "مثال آوردی، اما بخشی از آن با مفهوم جور در نمی‌آید؛ یا برای ساده گفتن باز هم به اصطلاحِ تخصصی تکیه کردی.",
    ("simple_communication", "needs_work"):
        "برای ساده گفتن نتوانستی از اصطلاحِ تخصصی فاصله بگیری، یا مثالت خودش بدفهمی ساخت.",
    ("simple_communication", "not_assessed"):
        "به سؤالِ توضیحِ ساده پاسخ ندادی، پس توانایی‌ات در انتقالِ مفهوم سنجیده نشد.",
}


def _score_pct(records: list[dict[str, Any]]) -> Optional[int]:
    """امتیازِ ۰ تا ۱۰۰ هم‌راستا با وضعیتِ تجمیعیِ همان بُعد.

    ⚠️ باگِ نسخهٔ اول (فاز ۳۰): بی‌پاسخ را در میانگین نمی‌آورد و از دو سؤال
    (یکی ``CORRECT`` و یکی ``INSUFFICIENT_EVIDENCE``) امتیازِ ۱۰۰ می‌ساخت —
    در حالی که وضعیتِ تجمیعی ``HALF_CORRECT`` بود. نتیجه: کارتی با نوارِ
    ۱۰۰٪ و برچسبِ «نیازمند تثبیت»؛ دقیقاً همان ناسازگاریِ داده که نباید
    اتفاق بیفتد.

    قاعدهٔ درست: **همان ورودی‌ای که وضعیتِ نهایی را می‌سازد، امتیاز را هم
    بسازد.** بی‌پاسخ مثلِ نیمه‌درست شمرده می‌شود، چون نبودِ شاهد به معنای
    تأییدِ آن مهارت نیست.
    """
    values: list[int] = []
    for record in records or []:
        status = str(record.get("status") or "").upper().strip()
        if status in _STATUS_SCORE:
            values.append(_STATUS_SCORE[status])
        elif status:
            # شاهدِ ناکافی — نه صفرِ کامل، نه صدِ کامل.
            values.append(50)
    if not values:
        return None
    return round(sum(values) / len(values))


def dimension_status(stage_status: Any) -> str:
    """برچسبِ مرحله → وضعیتِ بعد. هر مقدارِ ناشناخته «بدون پاسخ» می‌شود، نه «نامشخص»."""
    return _STATUS_MAP.get(str(stage_status or "").upper().strip(), "not_assessed")


def _aggregate_statuses(statuses: list[str]) -> str:
    """تجمیعِ وضعیتِ دو سؤالِ یک مرحله — بدترین حالتِ غیرِتهی.

    منطقِ کامل در ``ai.cross_check.aggregate_stage_status`` است؛ این نسخهٔ
    سبک برای گزارش است تا ماژولِ گزارش به موتورِ داوری وابسته نشود.
    """
    clean = [str(s or "").upper().strip() for s in statuses if s]
    if not clean:
        return "INSUFFICIENT_EVIDENCE"
    if len(set(clean)) == 1:
        return clean[0]
    present = set(clean)
    if "CORRECT" in present:
        return "HALF_CORRECT"
    if "WRONG" in present:
        return "HALF_CORRECT" if "INSUFFICIENT_EVIDENCE" in present else "WRONG"
    if "HALF_CORRECT" in present:
        return "HALF_CORRECT"
    return "INSUFFICIENT_EVIDENCE"


def build_stage_dimensions(per_question: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """پنج بُعدِ استاندارد را از شواهدِ پنج مرحله می‌سازد.

    با ساختارِ ده‌سؤالی (فاز ۱۱) دو سؤالِ هر مرحله **تجمیع** می‌شوند تا هر
    بُعد همچنان یک وضعیتِ واحد داشته باشد. خروجی همیشه دقیقاً پنج عضو دارد و
    کلیدهایش ثابت‌اند.

    فاز ۳۰: هر عضو علاوه بر فیلدهای قبلی (``key``/``status``/``finding``) سه
    فیلدِ نمایشیِ تازه دارد:

      * ``id``            — شناسهٔ کوتاه برای کارت (``intuition`` …)
      * ``title``/``subtitle`` — عنوانِ دانش‌آموزپسند و مهارتِ سنجیده‌شده
      * ``mastery_level``  — سه‌سطحی: ``mastered``/``shaky``/``needs_work``
      * ``score_pct``      — ۰..۱۰۰ از روی پاسخ‌های واقعی، یا ``None``

    ``score_pct`` عمداً ``None`` می‌ماند وقتی شاهدی نیست؛ عددِ ساختگی برای پر
    کردنِ نوارِ پیشرفت، همان «دادهٔ ساختگی» است که نباید نمایش داده شود.
    """
    # گروه‌بندی بر اساسِ شمارهٔ مرحله (نه ترتیبِ سؤال)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in per_question or []:
        order = int(record.get("order") or 0)
        stage = int(record.get("stage") or 0) or (
            (order - 1) // 2 + 1 if order >= 1 else 0
        )
        if stage <= 0:
            continue
        grouped.setdefault(stage, []).append(record)

    out: list[dict[str, Any]] = []
    for order, key, title, subtitle in STAGE_DIMENSIONS:
        records = grouped.get(order) or []
        record = records[0] if records else {}
        if len(records) > 1:
            merged = _aggregate_statuses([str(r.get("status") or "") for r in records])
        else:
            merged = str(record.get("status") or "")
        status = dimension_status(merged)
        score = _score_pct(records)
        out.append(
            {
                # ── کلیدهای اصلی (قراردادِ قبلی، دست‌نخورده) ──
                "key": key,
                "label": title,
                "order": str(order),
                "stage_title": str(record.get("stage_title") or ""),
                "status": status,
                "status_fa": DIMENSION_STATUS_FA[status],
                "finding": _FINDINGS[(key, status)],
                "has_evidence": status != "not_assessed",
                "question_count": len(records),
                # ── فیلدهای نمایشیِ فاز ۳۰ ──
                "id": DIMENSION_SHORT_IDS[key],
                "title": title,
                "subtitle": subtitle,
                "mastery_level": _MASTERY_FROM_STATUS.get(status, "needs_work"),
                "score_pct": score,
            }
        )
    return out
