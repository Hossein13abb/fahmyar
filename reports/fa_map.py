"""نگاشت دفاعی عناوین انگلیسی/نیمه‌فارسی به فارسی اصیل — برای گزارش آزمون جامع.

اگر مدل (یا دادهٔ قدیمی) عناوین انگلیسی بدهد، اینجا به معادل فارسی تبدیل می‌شوند؛
هیچ عنوان انگلیسی‌ای نباید در UI یا بخش‌های متنی گزارش بماند.
فرمول‌ها و نمادهای علمی کوتاه (I = V/R) انگلیسیِ ممنوعه نیستند.
"""
from __future__ import annotations

import re
from typing import Any

TARGET_DIMENSIONS = [
    "درک مفهومی و علّی",
    "کاربرد در دنیای واقعی",
    "مهارت‌های کمی و محاسباتی",
    "بازنمایی نموداری و تصویری",
    "مواجهه با تله‌ها و بدفهمی‌ها",
    "شفافیت بیان و خودپایشی",
]

DIMENSION_ALIASES: list[tuple[str, str]] = [
    # ۱) درک مفهومی و علّی
    ("Conceptual/Causal Understanding", TARGET_DIMENSIONS[0]),
    ("Conceptual-Causal Understanding", TARGET_DIMENSIONS[0]),
    ("Conceptual Causal Understanding", TARGET_DIMENSIONS[0]),
    ("Conceptual Understanding", TARGET_DIMENSIONS[0]),
    ("Causal Understanding", TARGET_DIMENSIONS[0]),
    ("Conceptual Causality", TARGET_DIMENSIONS[0]),
    ("فهم مفهومی/علّی", TARGET_DIMENSIONS[0]),
    ("فهم مفهومی و علّی", TARGET_DIMENSIONS[0]),
    ("درک مفهومی/علّی", TARGET_DIMENSIONS[0]),
    ("درک علت و معلول", TARGET_DIMENSIONS[0]),
    ("تعریف و مرزبندی مفهوم", TARGET_DIMENSIONS[5]),
    # ۲) کاربرد در دنیای واقعی
    ("Real-World Application", TARGET_DIMENSIONS[1]),
    ("Real World Application", TARGET_DIMENSIONS[1]),
    ("Real-world application", TARGET_DIMENSIONS[1]),
    ("Application in the Real World", TARGET_DIMENSIONS[1]),
    ("Practical Application", TARGET_DIMENSIONS[1]),
    ("Everyday Application", TARGET_DIMENSIONS[1]),
    ("کاربرد واقعی", TARGET_DIMENSIONS[1]),
    ("کاربرد در زندگی واقعی", TARGET_DIMENSIONS[1]),
    ("کاربرد در دنیای واقعی", TARGET_DIMENSIONS[1]),
    ("کاربرد عملی", TARGET_DIMENSIONS[1]),
    # ۳) مهارت‌های کمی و محاسباتی
    ("Quantitative and Computational Skills", TARGET_DIMENSIONS[2]),
    ("Quantitative/Computational Skills", TARGET_DIMENSIONS[2]),
    ("Quantitative Skills", TARGET_DIMENSIONS[2]),
    ("Computational Skills", TARGET_DIMENSIONS[2]),
    ("Procedural Skill", TARGET_DIMENSIONS[2]),
    ("Computational Procedure", TARGET_DIMENSIONS[2]),
    ("Numerical Computation", TARGET_DIMENSIONS[2]),
    ("رویهٔ حل‌سازی", TARGET_DIMENSIONS[2]),
    ("مهارت محاسباتی", TARGET_DIMENSIONS[2]),
    ("مهارت‌های کمی", TARGET_DIMENSIONS[2]),
    # ۴) بازنمایی نموداری و تصویری
    ("Diagram/Visual Representation", TARGET_DIMENSIONS[3]),
    ("Visual Representation", TARGET_DIMENSIONS[3]),
    ("Diagrammatic Representation", TARGET_DIMENSIONS[3]),
    ("Graph Reading", TARGET_DIMENSIONS[3]),
    ("Chart Reading", TARGET_DIMENSIONS[3]),
    ("Diagram Interpretation", TARGET_DIMENSIONS[3]),
    ("Reading Graphs and Data", TARGET_DIMENSIONS[3]),
    ("خواندن نمودار و داده", TARGET_DIMENSIONS[3]),
    ("بازنمایی نموداری", TARGET_DIMENSIONS[3]),
    ("نموداری", TARGET_DIMENSIONS[3]),
    # ۵) مواجهه با تله‌ها و بدفهمی‌ها
    ("Misconception Trap", TARGET_DIMENSIONS[4]),
    ("Misconception Traps", TARGET_DIMENSIONS[4]),
    ("Common Misconceptions", TARGET_DIMENSIONS[4]),
    ("Misconceptions", TARGET_DIMENSIONS[4]),
    ("Identifying Misconceptions", TARGET_DIMENSIONS[4]),
    ("ردیابی بدفهمی شایع", TARGET_DIMENSIONS[4]),
    ("ردیابی بدفهمی‌های رایج", TARGET_DIMENSIONS[4]),
    ("تلهٔ بدفهمی", TARGET_DIMENSIONS[4]),
    ("تله‌های بدفهمی", TARGET_DIMENSIONS[4]),
    ("بدفهمی‌های شایع", TARGET_DIMENSIONS[4]),
    # ۶) شفافیت بیان و خودپایشی
    ("Clarity of Explanation", TARGET_DIMENSIONS[5]),
    ("Clarity and Self-monitoring", TARGET_DIMENSIONS[5]),
    ("Clarity and Self-Monitoring", TARGET_DIMENSIONS[5]),
    ("Self-monitoring", TARGET_DIMENSIONS[5]),
    ("Self Monitoring", TARGET_DIMENSIONS[5]),
    ("Metacognitive Clarity", TARGET_DIMENSIONS[5]),
    ("Expression Clarity", TARGET_DIMENSIONS[5]),
    ("Transparency of Expression", TARGET_DIMENSIONS[5]),
    ("شفافیت بیان", TARGET_DIMENSIONS[5]),
    ("خودپایشی", TARGET_DIMENSIONS[5]),
    ("شفافیت پاسخ", TARGET_DIMENSIONS[5]),
]

EXAM_TYPE_FA = {
    "conceptual": "مفهومی/استدلالی",
    "real_world": "کاربرد واقعی",
    "diagram": "نموداری/شکلی",
    "misconception_trap": "تلهٔ بدفهمی",
    "computational": "محاسباتی/رویه‌ای",
    "definitional": "حفظی/تعریفی",
    "novel_application": "کاربرد نو",
    "phenomenon_explain": "تبیین پدیده",
    "compare_explanations": "مقایسهٔ تبیین‌ها",
    "predict": "پیش‌بینی",
    "categorize": "دسته‌بندی",
    "error_identify": "شناسایی خطا",
}

_FA_DIRE = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_EN_WORD = re.compile(r"[A-Za-z]{4,}")


def _key(text: str) -> str:
    text = str(text or "").strip().lower()
    for ch in ("\u200c", " ", "-", "_", "/", "\\", "–", "—", "|", ":", "؛", "،", "٬"):
        text = text.replace(ch, "")
    return text


def latin_heavy(text: Any) -> bool:
    """ترو اگر متن عمدتاً انگلیسی باشد (فرمول‌های کوتاه انگلیسی به‌حساب نمی‌آیند)."""
    s = str(text or "")
    fa = len(_FA_DIRE.findall(s))
    en = sum(len(m.group(0)) for m in _EN_WORD.finditer(s))
    return en >= 8 and en > fa


def fa_text(text: Any, fallback_fa: str) -> str:
    s = str(text or "").strip()
    if not s:
        return fallback_fa
    return fallback_fa if latin_heavy(s) else s


def normalize_dimension(name: Any) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "درک مفهومی و علّی"
    key = _key(raw)
    for alias, target in sorted(DIMENSION_ALIASES, key=lambda kv: len(_key(kv[0])), reverse=True):
        a = _key(alias)
        if a == key:
            return target
    for alias, target in DIMENSION_ALIASES:
        a = _key(alias)
        if len(a) >= 6 and a in key:
            return target
    # هیچ نگاشتی نبود: اگر عنوانی انگلیسیِ غیرمنتظره باشد، عنوان فارسیِ خنثی برگردان
    if _EN_WORD.search(raw):
        return "بُعد فهم"
    return raw


def normalize_exam_type(exam_type: Any) -> str:
    raw = str(exam_type or "").strip()
    return EXAM_TYPE_FA.get(raw, raw if not _EN_WORD.search(raw) else "تحلیلی")


def dimension_fallback(status: str, kind: str = "finding") -> str:
    st = str(status or "").upper()
    if st == "NEEDS_REVIEW":
        return "در این بُعد نشانه‌های بدفهمی دیده شد؛ معلم باید با نمونه‌نقض، استدلال دانش‌آموز را بازسازی کند."
    if st == "CONFIRMED":
        return "این بُعد در پاسخ‌ها با استدلال روشن ثبت شده است."
    if st == "LIKELY_UNDERSTOOD":
        return "هستهٔ این بُعد به نظر می‌رسد درست باشد، اما بیان باید کامل‌تر شود."
    if st == "INSUFFICIENT_EVIDENCE":
        return "در این بُعد پاسخ کافی برای داوری ثبت نشده است."
    return "در این بُعد پاسخ روشن و قاطع نیست؛ معلم باید با پرسش راهنما ادامه را بررسی کند."


def feedback_fallback(status: str) -> str:
    st = str(status or "").upper()
    if st == "NEEDS_REVIEW":
        return "در این پاسخ تناقض علمی روشن دیده می‌شود؛ دانش‌آموز باید همان استدلال را با نمونه‌نقض بازسازی کند."
    if st == "CONFIRMED":
        return "این پاسخ با مبانی علمی سازگار است و استدلال علّی روشن دارد."
    if st == "LIKELY_UNDERSTOOD":
        return "هستهٔ پاسخ درست است، اما دلیل و مرزبندی آن باید کامل‌تر بیان شود."
    if st == "INSUFFICIENT_EVIDENCE":
        return "برای این پاسخ شواهد کافی ثبت نشده است."
    return "این پاسخ دلیل روشن و قابل اتکا ندارد؛ معلم باید با پرسش راهنما فهم دانش‌آموز را روشن کند."


def suggestion_fallback() -> str:
    return "پیش‌نیازها را مرور کنید و برای هر بدفهمیِ شناسایی‌شده یک مثال نقض ساده طراحی و بلند بلند توضیح دهید."
