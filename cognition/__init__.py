"""موتور فهم‌سنجی شناختی (Cognitive Assessment Engine).

این بسته جایگزینِ کاملِ موتور قدیمیِ ارزیابی است. تفاوت بنیادین:

* موتور قدیمی هر سؤال را **جدا** تصحیح می‌کرد و پاسخ‌ها را جمع می‌زد.
* این موتور سؤال‌ها را **با هم مقایسه** می‌کند و تناقض‌های ذهنِ دانش‌آموز را
  شکار می‌کند — چون فهمیدن یعنی *انسجامِ درونی*، نه تعدادِ جوابِ درست.

پنج سؤال آزمون، پنج لایهٔ متفاوتِ یک مفهوم را می‌سنجند:

    ۱. philosophy          — چرا این مفهوم اختراع شد؟ (ضدِ بلوف)
    ۲. mask_mcq            — لایهٔ نقاب: تستِ استاندارد با اطلاعاتِ انحرافی
    ۳. perturbation        — دستکاریِ سیستم: پیش‌بینیِ زنجیرهٔ علّی، بدون عدد
    ۴. debugging           — عیب‌یابیِ استدلالِ غلطِ ظاهراً علمی (شاه‌کلید)
    ۵. feynman_synthesis   — توضیح برای بچهٔ ۱۰ ساله، با کلماتِ ممنوعه

و ارزیابی بر پایهٔ چهار قانونِ شناختی انجام می‌شود:

    قانون ۱ — تضادِ نقاب و شهود      (Q2  در برابر  Q5)
    قانون ۲ — حاکمیتِ عیب‌یابی        (Q3 و Q4)
    قانون ۳ — اعتیاد به ادبیاتِ کتاب  (نقضِ forbidden_words)
    قانون ۴ — بی‌دقتی در برابر کج‌فهمی (نیازمندِ بازپرسی)
"""
from __future__ import annotations

from .personas import (
    PERSONAS,
    MASTERY_STATUSES,
    STATUS_LABELS,
    persona_for_status,
    status_description,
    status_label,
)
from .contract import (
    QUESTION_TYPES,
    QUESTION_TITLES,
    STAGES,
    Blueprint,
    ClarificationData,
    CrossCheckFinding,
    EvaluationReport,
    GeneratedAssessment,
    QuestionInsight,
    assess_payload_from_generation,
    normalize_evaluation,
    normalize_generation,
    validate_generation,
)
from .rules import (
    RULE_LABELS,
    apply_supremacy_override,
    detect_jargon_violation,
    find_forbidden_words,
    rule_summary,
)

__all__ = [
    "PERSONAS",
    "MASTERY_STATUSES",
    "STATUS_LABELS",
    "persona_for_status",
    "status_description",
    "status_label",
    "QUESTION_TYPES",
    "QUESTION_TITLES",
    "STAGES",
    "Blueprint",
    "ClarificationData",
    "CrossCheckFinding",
    "EvaluationReport",
    "GeneratedAssessment",
    "QuestionInsight",
    "assess_payload_from_generation",
    "normalize_evaluation",
    "normalize_generation",
    "validate_generation",
    "RULE_LABELS",
    "apply_supremacy_override",
    "detect_jargon_violation",
    "find_forbidden_words",
    "rule_summary",
]
