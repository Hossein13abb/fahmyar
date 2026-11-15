"""پرسوناهای شناختی و نقشهٔ وضعیتِ تسلط.

هر پرسونا یک *الگوی* ذهنی است، نه یک نمره. دو دانش‌آموز می‌توانند هر دو
«ضعیف» باشند اما یکی گرفتارِ تضادِ نقاب و شهود باشد و دیگری معتاد به
ادبیاتِ کتاب — و درمانِ این دو کاملاً متفاوت است.
"""
from __future__ import annotations

from typing import Any

#: پنج وضعیتِ تسلط. کلیدها همان مقادیری هستند که مدل برمی‌گرداند.
MASTERY_STATUSES = (
    "MASTERED",
    "ILLUSION_OF_COMPETENCE",
    "JARGON_DEPENDENT",
    "PARTIAL_FRAGMENTED",
    "UNSTRUCTURED",
)

#: جزئیاتِ نمایشیِ هر پرسونا.
PERSONAS: dict[str, dict[str, Any]] = {
    "MASTERED": {
        "title": "معمارِ مفهوم",
        "subtitle": "ساعت را در ذهنت بستی",
        "emoji": "🛠️",
        "tone": "positive",
        "color": "emerald",
        "meaning": (
            "می‌توانی مفهوم را از چند زاویهٔ متفاوت توضیح بدهی و بین آن‌ها "
            "انسجام نگه داری. این همان چیزی است که «فهمیدن» نامیده می‌شود."
        ),
        "advice_focus": "عمق بیشتر: مفهوم را به مبحثِ بعدی وصل کن و مرزهای اعتبارش را پیدا کن.",
    },
    "ILLUSION_OF_COMPETENCE": {
        "title": "گرفتارِ تضادِ فرمول و شهود",
        "subtitle": "توهمِ یادگیری",
        "emoji": "🎭",
        "tone": "critical",
        "color": "rose",
        "meaning": (
            "فرمول را بلدی و تست را درست می‌زنی، اما وقتی کلماتِ تخصصی را از "
            "دستت گرفتیم، به همان شهودِ اولیه‌ات برگشتی. یعنی فرمول روی "
            "درکِ تو نشسته، نه درونِ آن."
        ),
        "advice_focus": "فرمول را کنار بگذار و همان پدیده را با یک مثالِ روزمره بازگو کن.",
    },
    "JARGON_DEPENDENT": {
        "title": "معتاد به ادبیاتِ کتاب",
        "subtitle": "فهمِ محبوس در کلمات",
        "emoji": "📚",
        "tone": "critical",
        "color": "amber",
        "meaning": (
            "برای توضیح، به کلماتِ تخصصیِ کتاب تکیه می‌کنی. این کلمات ابزارِ "
            "بیان‌اند، نه خودِ فهم. تا وقتی نتوانی بدونِ آن‌ها توضیح بدهی، "
            "نمی‌توانی مطمئن باشی که فهمیده‌ای."
        ),
        "advice_focus": "قانونِ فاینمن: همان مفهوم را برای یک بچهٔ ۱۰ ساله توضیح بده، بدونِ هیچ اصطلاح.",
    },
    "PARTIAL_FRAGMENTED": {
        "title": "تفکرِ جزیره‌ای",
        "subtitle": "چرخ‌دنده‌ها جدا از هم",
        "emoji": "🧩",
        "tone": "neutral",
        "color": "sky",
        "meaning": (
            "قطعه‌های مفهوم را داری، اما به هم وصل نشده‌اند. هر جزیره را "
            "جدا می‌شناسی؛ چیزی که کم است، زنجیرهٔ علّیِ بین آن‌هاست."
        ),
        "advice_focus": "یک زنجیرهٔ سه‌مرحله‌ای بساز: اگر این تغییر کند، بعدش چه می‌شود، و چرا؟",
    },
    "UNSTRUCTURED": {
        "title": "نقشهٔ ذهنیِ نامنظم",
        "subtitle": "پایه‌ها هنوز شکل نگرفته",
        "emoji": "🌫️",
        "tone": "neutral",
        "color": "slate",
        "meaning": (
            "پاسخ‌ها نشان می‌دهند که اجزای پایه هنوز در ذهن شکل نگرفته‌اند. "
            "این نه شکست است و نه کندی — نقطهٔ شروعِ درست همین‌جاست."
        ),
        "advice_focus": "از تصویرِ کلان شروع کن: این مفهوم برای حلِ چه مشکلی به وجود آمد؟",
    },
}


#: برچسبِ فارسیِ وضعیت‌ها — هرگز متنِ انگلیسی به کاربر نشان داده نمی‌شود.
STATUS_LABELS: dict[str, str] = {
    "MASTERED": "تسلطِ کامل",
    "ILLUSION_OF_COMPETENCE": "توهمِ یادگیری",
    "JARGON_DEPENDENT": "وابستگی به اصطلاحات",
    "PARTIAL_FRAGMENTED": "فهمِ ناقص",
    "UNSTRUCTURED": "نقشهٔ نامنظم",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get((status or "").strip().upper(), "نامشخص")


def persona_for_status(status: str) -> dict[str, Any]:
    """جزئیاتِ نمایشیِ پرسونا برای یک وضعیت؛ در صورتِ ناشناخته، پیش‌فرضِ محافظه‌کارانه."""
    return PERSONAS.get((status or "").strip().upper(), PERSONAS["UNSTRUCTURED"])


def status_description(status: str) -> str:
    return persona_for_status(status)["meaning"]
