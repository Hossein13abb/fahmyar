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

#: هر بعد به کدام مرحله گره خورده است.
STAGE_DIMENSIONS: tuple[tuple[int, str, str], ...] = (
    (1, "conceptual_knowledge", "دانش مفهومی"),
    (2, "distractor_resistance", "مقاومت در برابر دادهٔ انحرافی"),
    (3, "causal_reasoning", "استدلال علّی"),
    (4, "critical_debugging", "نقد استدلال"),
    (5, "simple_communication", "انتقال ساده"),
)

#: نگاشتِ برچسبِ مرحله → وضعیتِ بعد. «نامشخص» در این جدول وجود ندارد.
_STATUS_MAP: dict[str, str] = {
    "CORRECT": "mastered",
    "HALF_CORRECT": "developing",
    "WRONG": "needs_work",
    "INSUFFICIENT_EVIDENCE": "not_assessed",
}

#: جملهٔ تحلیلی به تفکیک (کلیدِ بعد، وضعیت) — هر جمله به همان مرحله اشاره دارد.
_FINDINGS: dict[tuple[str, str], str] = {
    # ── ۱) دانش مفهومی ──
    ("conceptual_knowledge", "mastered"):
        "تصویرِ کلانِ مفهوم را دارد و می‌داند چرا این مفهوم به وجود آمده، نه فقط اسمش را.",
    ("conceptual_knowledge", "developing"):
        "جهتِ کلیِ مفهوم را می‌شناسد، اما دلیلِ وجودی و مرزهای آن را کامل بیان نکرد.",
    ("conceptual_knowledge", "needs_work"):
        "تصویرِ کلانِ مفهوم را ندارد؛ آن را مجموعه‌ای از تعریف‌های پراکنده می‌بیند.",
    ("conceptual_knowledge", "not_assessed"):
        "به این مرحله پاسخی نداده است؛ دربارهٔ تصویرِ کلانِ او داوری ممکن نیست.",
    # ── ۲) مقاومت در برابر دادهٔ انحرافی ──
    ("distractor_resistance", "mastered"):
        "دادهٔ مزاحم را شناخت و کنار گذاشت؛ رابطه را روی داده‌های مرتبط به کار برد.",
    ("distractor_resistance", "developing"):
        "پاسخِ درستی به دست نیاورد، هرچند مسیرِ محاسبه را تا حدی می‌شناخت.",
    ("distractor_resistance", "needs_work"):
        "در انتخابِ گزینه، دادهٔ نامرتبط یا محاسبهٔ نادرست او را از پاسخِ درست دور کرد.",
    ("distractor_resistance", "not_assessed"):
        "گزینه‌ای انتخاب نکرد؛ دربارهٔ مقاومتِ او در برابر دادهٔ انحرافی داوری ممکن نیست.",
    # ── ۳) استدلال علّی ──
    ("causal_reasoning", "mastered"):
        "زنجیرهٔ علّی را حلقه‌به‌حلقه چید: تغییرِ ورودی ← تغییرِ میانی ← تغییرِ نتیجه.",
    ("causal_reasoning", "developing"):
        "نتیجهٔ نهایی را درست گفت، اما حلقه‌های میانیِ زنجیرهٔ علّی را کامل توضیح نداد.",
    ("causal_reasoning", "needs_work"):
        "رابطهٔ علّی را برعکس یا ناقص بیان کرد؛ از تغییرِ ورودی به نتیجهٔ درست نرسید.",
    ("causal_reasoning", "not_assessed"):
        "به این مرحله پاسخی نداده است؛ استدلالِ علّیِ او سنجیده نشد.",
    # ── ۴) نقد استدلال ──
    ("critical_debugging", "mastered"):
        "هستهٔ استدلالِ غلط را پیدا کرد و دقیقاً گفت کدام فرض اشتباه است.",
    ("critical_debugging", "developing"):
        "اشتباه را تشخیص داد، اما توضیح نداد چرا اشتباه است؛ نقد در سطحِ «اشتباه می‌گوید» ماند.",
    ("critical_debugging", "needs_work"):
        "استدلالِ غلط را نپذیرفت یا خودش در همان بدفهمی افتاد؛ هستهٔ خطا دست‌نخورده ماند.",
    ("critical_debugging", "not_assessed"):
        "به این مرحله پاسخی نداده است؛ توانِ نقدِ استدلالِ او سنجیده نشد.",
    # ── ۵) انتقال ساده ──
    ("simple_communication", "mastered"):
        "مفهوم را بدونِ اصطلاحِ تخصصی و با تمثیلی که نگاشتش درست است منتقل کرد.",
    ("simple_communication", "developing"):
        "تمثیل را آورد، اما نگاشتِ آن با مفهوم کامل نمی‌خواند یا جایی لنگ می‌زند.",
    ("simple_communication", "needs_work"):
        "برای توضیحِ ساده نتوانست از اصطلاحاتِ تخصصی فاصله بگیرد یا تمثیلش نادرست بود.",
    ("simple_communication", "not_assessed"):
        "به این مرحله پاسخی نداده است؛ توانِ انتقالِ سادهٔ او سنجیده نشد.",
}


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


def build_stage_dimensions(per_question: list[dict[str, Any]]) -> list[dict[str, str]]:
    """پنج بُعدِ استاندارد را از شواهدِ پنج مرحله می‌سازد.

    با ساختارِ ده‌سؤالی (فاز ۱۱) دو سؤالِ هر مرحله **تجمیع** می‌شوند تا هر
    بُعد همچنان یک وضعیتِ واحد داشته باشد. خروجی همیشه دقیقاً پنج عضو دارد و
    کلیدهایش ثابت‌اند؛ فرانت‌اند با همین قرارداد رندر می‌کند و هیچ‌گاه به
    «نامشخص»ِ بی‌داده نمی‌رسد.
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

    out: list[dict[str, str]] = []
    for order, key, label in STAGE_DIMENSIONS:
        records = grouped.get(order) or []
        record = records[0] if records else {}
        if len(records) > 1:
            merged = _aggregate_statuses([str(r.get("status") or "") for r in records])
        else:
            merged = str(record.get("status") or "")
        status = dimension_status(merged)
        out.append(
            {
                "key": key,
                "label": label,
                "order": str(order),
                "stage_title": str(record.get("stage_title") or ""),
                "status": status,
                "status_fa": DIMENSION_STATUS_FA[status],
                "finding": _FINDINGS[(key, status)],
                "has_evidence": status != "not_assessed",
                "question_count": len(records),
            }
        )
    return out
