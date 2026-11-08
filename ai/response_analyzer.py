"""تحلیل پاسخِ آزادِ دانش‌آموز (به فارسی) → استخراج شواهد کیفی.

اصل بنیادین: ساختار استدلال سنجیده می‌شود (ادعا + دلیل + ارتباط)،
نه حضور واژه‌ها. واژهٔ درست بدون دلیل ≠ شواهدِ فهمیدن.

خروجی ساخت‌یافته: فهرست EvidenceRecord با status یکی از ۵ وضعیتِ کیفی.
اگر اطمینان تحلیل‌گر < CONFIDENCE_THRESHOLD باشد → UNCLEAR + نیازمند بررسی معلم.
همیشه در شکستِ تحلیل، جلسه متوقف نمی‌شود؛ شواهد «نامشخص» ثبت می‌شود.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from config import settings
from models.question import EvidenceStatus
from ai.model_abstraction import get_router

_VALID_STATUS = {s.value for s in EvidenceStatus}
_VALID_EVIDENCE_TYPES = {
    "strong_confirming",
    "weak_confirming",
    "computational_success",   # موفقیت صرفاً محاسباتی — هرگز جایگزین فهم گزارهٔ اصلی نیست
    "weak_contradicting",
    "strong_contradicting",
}
_VALID_ERROR_TYPES = {"conceptual", "computational", "misreading", "none"}


@dataclass
class EvidenceRecord:
    proposition_id: str
    status: str  # EvidenceStatus value
    evidence_type: str  # یکی از _VALID_EVIDENCE_TYPES
    reasoning: str
    confidence: float
    error_type: str = "none"
    needs_teacher_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROMPT = """شما تحلیل‌گر ارزیابی آموزشی «فهم‌یار» هستید. پاسخ فارسیِ دانش‌آموز را تحلیل کنید.

اصل قطعی: ساختار استدلال را بسنجید (ادعا + دلیل + ارتباطِ دلیل با ادعا)، نه حضور واژه‌های کلیدی را.

قواعد تحلیل:
1. پاسخِ صحیح بدون هیچ استدلالی → فقط شواهدِ ضعیف است (evidence_type=weak_confirming، confidence پایین).
2. واژهٔ کلیدیِ درست بدون دلیل → شواهدِ فهمیدن محسوب نمی‌شود.
3. اگر پاسخ شامل «چون/زیرا/به این دلیل…» و یک دلیلِ مرتبط باشد → شواهد قوی است.
4. غلط‌های محاسباتی یا بی‌دقتی را از خطای مفهومی جدا کنید (error_type).
   اگر پاسخ صرفاً یک محاسبهٔ مکانیکیِ درستِ بدون هیچ استدلال مفهومی است، evidence_type را computational_success بگذارید (نه strong_confirming).
5. پاسخ‌های محاوره‌ای، دارای غلط املایی یا اصطلاحات انگلیسی–فارسی مخلوط را بپذیرید؛ معنی را بسنجید نه شکل را.
6. اگر دانش‌آموز چیزی را که بلد نیست، حدس زده یا کپی کرده — آن را NEEDS_REVIEW/UNCLEAR علامت بزنید.
7. اگر از تحلیل خود مطمئن نیستید → confidence را پایین بگذارید و needs_teacher_review=true بزنید (status=UNCLEAR).

وضعیت‌های مجاز status: CONFIRMED | LIKELY_UNDERSTOOD | UNCLEAR | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE
نوع‌های مجاز evidence_type: strong_confirming | weak_confirming | computational_success | weak_contradicting | strong_contradicting
نوع‌های مجاز error_type: conceptual | computational | misreading | none

خروجی فقط JSON معتبر با این ساختار (بدون هیچ متن اضافه):
{{
  "evidence": [
    {{
      "proposition_id": "دقیقاً همان متن گزاره از فهرست ورودی",
      "status": "...",
      "evidence_type": "...",
      "reasoning": "دلیل ارزیابی شما (به فارسی)",
      "confidence": 0.0,
      "error_type": "none",
      "needs_teacher_review": false
    }}
  ],
  "overall_reasoning": "جمع‌بندی کوتاه"
}}

<<<QUESTION>>>{question_text}<<<END>>>
<<<PROPOSITIONS>>>{propositions_json}<<<END>>>
<<<RUBRIC>>>{rubric_json}<<<END>>>
<<<RESPONSE>>>{student_response}<<<END>>>"""


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _normalize_record(item: dict[str, Any], fallback_prop: str) -> EvidenceRecord:
    prop = str(item.get("proposition_id") or fallback_prop).strip() or fallback_prop
    status = str(item.get("status") or "UNCLEAR").upper().strip()
    if status not in _VALID_STATUS:
        status = "UNCLEAR"
    etype = str(item.get("evidence_type") or "weak_confirming").lower().strip()
    if etype not in _VALID_EVIDENCE_TYPES:
        etype = "weak_confirming"
    error_type = str(item.get("error_type") or "none").lower().strip()
    if error_type not in _VALID_ERROR_TYPES:
        error_type = "none"
    try:
        confidence = float(item.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    needs_review = bool(item.get("needs_teacher_review", False))
    reasoning = str(item.get("reasoning") or "").strip() or "بدون توضیح تحلیل‌گر"

    # الزام: اطمینان پایین → نامشخص + بررسی معلم
    if confidence < settings.CONFIDENCE_THRESHOLD:
        status = EvidenceStatus.UNCLEAR.value
        needs_review = True

    return EvidenceRecord(
        proposition_id=prop,
        status=status,
        evidence_type=etype,
        reasoning=reasoning,
        confidence=confidence,
        error_type=error_type,
        needs_teacher_review=needs_review,
    )


def _fallback_records(propositions: list[str], reason: str) -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            proposition_id=prop,
            status=EvidenceStatus.UNCLEAR.value,
            evidence_type="weak_confirming",
            reasoning=reason,
            confidence=0.0,
            error_type="none",
            needs_teacher_review=True,
        )
        for prop in propositions
    ]


async def analyze_response(
    question,
    student_response: str,
    rubric: dict | None = None,
) -> list[EvidenceRecord]:
    """پاسخ دانش‌آموز را تحلیل و فهرست EvidenceRecord برمی‌گرداند.

    question: شیء Question (یا هر شیئی با attributeهای text / mapped_propositions / rubric)
    """
    rubric = rubric if rubric is not None else (getattr(question, "rubric", None) or {})
    propositions = list(getattr(question, "mapped_propositions", None) or [])
    if not propositions:
        # اگر سؤالی گزاره‌ای منسوب نکرده، از rubric یا عنوان عمومی استفاده کن
        propositions = [f"مفهومِ سؤال #{getattr(question, 'id', '?')}"]

    response_text = (student_response or "").strip()
    if not response_text:
        return _fallback_records(propositions, "پاسخی ثبت نشده است.")

    prompt = _PROMPT.format(
        question_text=getattr(question, "text", ""),
        propositions_json=json.dumps(propositions, ensure_ascii=False),
        rubric_json=json.dumps(rubric, ensure_ascii=False)[:4000],
        student_response=response_text,
    )

    try:
        router = get_router()
        resp = await router.generate(prompt, "analyze_response", temperature=0.2)
        data = _extract_json(resp.text)
        if not data or not isinstance(data.get("evidence"), list) or not data["evidence"]:
            return _fallback_records(propositions, "تحلیل‌گر خروجی قابل‌استفاده نداد — نیازمند بررسی معلم است.")
        records = [_normalize_record(item, propositions[0]) for item in data["evidence"] if isinstance(item, dict)]
        if not records:
            return _fallback_records(propositions, "ساختار شواهد نامعتبر بود — نیازمند بررسی معلم است.")
        return records
    except Exception as exc:
        # هیچ‌وقت جلسه را به‌خاطر خطای تحلیل متوقف نکن
        return _fallback_records(propositions, f"تحلیل خودکار ناموفق بود ({exc}) — نیازمند بررسی معلم است.")
