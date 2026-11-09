"""تحلیل پاسخِ آزادِ دانش‌آموز (به فارسی) → استخراج شواهد کیفی.

اصل بنیادین: ساختار استدلال سنجیده می‌شود (ادعا + دلیل + ارتباط)،
نه حضور واژه‌ها. واژهٔ درست بدون دلیل ≠ شواهدِ فهمیدن.

خروجی ساخت‌یافته: فهرست EvidenceRecord با status یکی از ۵ وضعیتِ کیفی.
تحلیل‌گر «سخت‌گیر و قطعی» است: غلطِ علمیِ روشن = بدفهمیِ تأییدشده (NEEDS_REVIEW)، نه «نامشخص».
UNCLEAR فقط و فقط برای پاسخ‌های بی‌ربط/نامفهوم یا اطمینانِ زیر آستانه است.
اگر اطمینان تحلیل‌گر < CONFIDENCE_THRESHOLD باشد → UNCLEAR + نیازمند بررسی معلم.
qualitative_feedback (دلیلِ دقیقِ رد/تأیید) در evidence هر رکورد ذخیره و در گزارش به معلم نمایش داده می‌شود.
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
from ai.json_sanitize import extract_json_object

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
    qualitative_feedback: str = ""  # دلیلِ دقیقِ رد/تأیید — همان متنی که معلم می‌خواند

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROMPT = """شما «متخصص تشخیص آموزشیِ سخت‌گیرِ فهم‌یار» هستید. وظیفهٔ شما تشخیصِ قاطعانهٔ وضعیتِ علمیِ پاسخِ دانش‌آموز است — نه دلجویی، نه حدس‌زدن، نه قضاوتِ محتاطانه.

اصل قطعی: ساختار استدلال را بسنجید (ادعا + دلیل + ارتباطِ دلیل با ادعا) در برابر مبانیِ علمیِ شناخته‌شدهٔ آن مفهوم. حضور واژه‌های کلیدی هیچ ارزشی ندارد.

تعریف دقیق وضعیت‌ها (تخطی از آن‌ها ممنوع است):
- CONFIRMED: فقط وقتی استدلالِ علمی کاملاً درست و عمیق است (ادعا + دلیلِ مرتبط و استدلالِ علّی).
- LIKELY_UNDERSTOOD: هستهٔ مرکزی فهم درست است؛ بیان دانش‌آموز کمی ناقص است ولی جهت آن اشتباه نیست.
- NEEDS_REVIEW (معادل «بدفهمیِ تأییدشده»): پاسخِ علمی غلط است یا استدلال با مبانی علمی تضاد دارد → با قاطعیت بدفهمی را تأیید کنید؛ دقیقاً بنویسید «دانش‌آموز به اشتباه تصور می‌کند که…» و دلیلِ علمیِ نادرستیِ آن چیست. برای این حالت: error_type=conceptual و evidence_type=strong_contradicting.
- UNCLEAR: فقط و فقط برای پاسخ‌های بی‌ربط یا نامفهوم (مثل «نمی‌دانم»، «سلام»، حروفِ بی‌معنی، پاسخ کاملاً نامرتبط) یا وقتی واقعاً هیچ داوری ممکن نیست.
- INSUFFICIENT_EVIDENCE: پاسخی ثبت نشده یا به هیچ‌یک از گزاره‌های فهرست ورودی اشاره نشده.

قواعد رفتاری:
1. ممنوع‌شدنِ کلمات تردید: هرگز از «به نظر می‌رسد»، «شاید»، «ممکن است»، «به‌نوعی»، «تا حدی» استفاده نکنید. تحلیل باید مستقیم باشد: «دانش‌آموز به اشتباه تصور می‌کند که …» / «این پاسخ نشان‌دهندهٔ فهمِ درستِ مفهومِ X است.»
2. غلطِ محاسباتی یا بی‌دقتی را از خطای مفهومی جدا کنید (error_type). محاسبهٔ مکانیکیِ درست بدون هیچ استدلال مفهومی → evidence_type=computational_success (هرگز CONFIRMED نکنید).
3. غلطِ علمیِ روشن را NEEDS_REVIEW ثبت کنید — نه UNCLEAR و نه «نیازمند بررسی» به‌معنای «نمی‌دانم»؛ و needs_teacher_review را false بگذارید (این تشخیصِ قطعی شماست).
4. needs_teacher_review=true فقط وقتی: پاسخ بی‌ربط/نامفهوم است یا confidence شما پایین‌تر از آستانه است.
5. پاسخ‌های محاوره‌ای، غلط املایی، یا فارسی–انگلیسیِ مخلوط را بپذیرید؛ معنی را بسنجید نه صورت را.
6. در reasoning و qualitative_feedback: ابتدا حکمِ قطعی، سپس دلیل. اگر پاسخ غلط است: دقیقاً چه چیزی غلط است و چرا.

وضعیت‌های مجاز status: CONFIRMED | LIKELY_UNDERSTOOD | UNCLEAR | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE
نوع‌های مجاز evidence_type: strong_confirming | weak_confirming | computational_success | weak_contradicting | strong_contradicting
نوع‌های مجاز error_type: conceptual | computational | misreading | none

فقط و فقط یک JSON معتبر برگردان. هیچ متن توضیحی قبل یا بعد از JSON (نه حتی یک کلمه) ننویس. واژهٔ «json» را به عنوان برچسب فنس (```json) یا هر شکل دیگری ننویس. پاسخت باید دقیقاً با کاراکتر «{{» شروع شود و دقیقاً با «}}» پایان یابد؛ فقط همان شیء JSON.

خروجی فقط JSON معتبر با این ساختار:
{{
  "evidence": [
    {{
      "proposition_id": "دقیقاً همان متن گزاره از فهرست ورودی",
      "status": "...",
      "evidence_type": "...",
      "reasoning": "حکم قطعی + دلیل (به فارسی، بدون کلمات تردید)",
      "confidence": 0.0,
      "error_type": "none",
      "needs_teacher_review": false
    }}
  ],
  "qualitative_feedback": "دلیلِ دقیقِ رد یا تأیید پاسخ در ۱ تا ۳ جمله. اگر رد شد: دقیقاً بنویسید چه چیزی غلط است و چرا و کدام گزاره نقض شده — این همان متنی است که معلم می‌خواند.",
  "overall_reasoning": "جمع‌بندی یک‌جمله‌ای"
}}

یادآوری نهایی: پاسخ را فقط با {{ شروع و فقط با }} تمام کن — هیچ چیز دیگری ننویس.

<<<QUESTION>>>{question_text}<<<END>>>
<<<PROPOSITIONS>>>{propositions_json}<<<END>>>
<<<RUBRIC>>>{rubric_json}<<<END>>>
<<<RESPONSE>>>{student_response}<<<END>>>"""


# استخراج مقاوم JSON — پیاده‌سازی مشترک در ai/json_sanitize.py
_extract_json = extract_json_object


_NEGATION_SCRUB_RE = re.compile(r"(بدون|هیچ|نه|بی)\s*[‌\u200c]?\s*(اشتباه|غلط|تضاد|نادرست|برعکس|معکوس|دست‌رفته)", re.IGNORECASE)

_MISCONCEPTION_MARKERS = (
    "به اشتباه",
    "بدفهمی",
    "تضاد",
    "برعکس",
    "نادرست",
    "دست‌رفته",
    "معکوس",
    "NEEDS_REVIEW",
)


def _has_decisive_misconception_marker(text: str) -> bool:
    scrubbed = _NEGATION_SCRUB_RE.sub("", text or "")  # «هیچ تضادی/اشتباهی …» بدفهمی نیست
    low = scrubbed.lower()
    return any(marker.lower() in low for marker in _MISCONCEPTION_MARKERS)


_HEDGE_WORDS = ("به نظر می‌رسد", "شاید", "ممکن است", "به‌نوعی", "تا حدی")


def _strip_hedges(text: str) -> str:
    """کلمات تردید را از ابتدای تحلیل حذف می‌کند (قاطعیت اجباری)."""
    out = text.strip()
    for hedge in _HEDGE_WORDS:
        out = out.replace(hedge, "").strip()
    return out or text.strip()


def _normalize_record(item: dict[str, Any], fallback_prop: str, qualitative_feedback: str = "") -> EvidenceRecord:
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
    reasoning = _strip_hedges(str(item.get("reasoning") or "").strip()) or "بدون توضیح تحلیل‌گر"
    feedback = _strip_hedges(str(item.get("qualitative_feedback") or qualitative_feedback).strip())

    # نشانگرهای قطعیِ بدفهمی در خودِ متن تحلیل — بدون هیچ شرط دیگری، حکم قطعی است
    decisive_text = _has_decisive_misconception_marker(reasoning + " " + feedback)
    decisive_struct = error_type == "conceptual" and (
        etype in ("strong_contradicting", "weak_contradicting")
        or status == EvidenceStatus.NEEDS_REVIEW.value
    )
    if decisive_text:
        # قانون سخت‌گیرانهٔ جدید: نشانهٔ بدفهمی در متن → NEEDS_REVIEW قطعی با confidence=0.95
        status = EvidenceStatus.NEEDS_REVIEW.value
        needs_review = False
        confidence = 0.95
    elif decisive_struct:
        # بدفهمیِ مفهومیِ ساختاری (contradicting + conceptual) → قطعی
        status = EvidenceStatus.NEEDS_REVIEW.value
        needs_review = False
        confidence = max(confidence, 0.9)
    else:
        # تضعیف اطمینان دیگر داوری را زیر سؤال نمی‌برد؛ همان status مدل حفظ می‌شود
        needs_review = bool(item.get("needs_teacher_review", False))

    return EvidenceRecord(
        proposition_id=prop,
        status=status,
        evidence_type=etype,
        reasoning=reasoning,
        confidence=confidence,
        error_type=error_type,
        needs_teacher_review=needs_review,
        qualitative_feedback=feedback or reasoning,
    )


_MISCONCEPTION_RAW_MARKERS = ("اشتباه", "غلط", "نادرست", "تضاد", "برعکس", "معکوس", "NEEDS_REVIEW")
_FENCE_INNER_RE = re.compile(r"```(?:[a-zA-Z]*)\s*(.*?)```", re.DOTALL)


def _clean_raw_text(raw: str) -> str:
    """پاک‌سازی متن خام مدل: فنس‌ها و علامت‌های ```json/بک‌تیک‌ها از ابتدا/انتها حذف می‌شوند."""
    t = (raw or "").strip()
    t = _FENCE_INNER_RE.sub(r"\1", t)          # بلوک ```json … ``` → محتوای داخلی
    t = re.sub(r"^```(?:[a-zA-Z]*)\s*", "", t)  # فنس بازِ بدون‌بسته
    t = re.sub(r"\s*```\s*$", "", t)            # فنس بستهٔ اضافه
    t = re.sub(r"^[`\s]+|[`\s]+$", "", t)       # بک‌تیک/صحنِ ابتدا و انتها
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _records_from_raw_text(raw_text: str, propositions: list[str]) -> list[EvidenceRecord]:
    """وقتی JSON پارس نمی‌شود: خودِ متن خام AI نزد معلم محفوظ است — هرگز بنر خطای ثابت نشان داده نمی‌شود.

    اگر متن خام شامل نشانه‌های بدفهمی (اشتباه/غلط/نادرست/تضاد/برعکس/معکوس/NEEDS_REVIEW) بود،
    حکم را قطعی می‌کنیم: status=NEEDS_REVIEW و needs_teacher_review=False («⚠️ بدفهمی شناسایی‌شده»).
    """
    cleaned = _clean_raw_text(raw_text)
    scrubbed = _NEGATION_SCRUB_RE.sub("", cleaned)  # «هیچ اشتباهی نکرد» نباید بدفهمی شمرده شود
    low = scrubbed.lower()
    is_decisive = any(marker.lower() in low for marker in _MISCONCEPTION_RAW_MARKERS)
    body = cleaned or (raw_text or "").strip()
    if is_decisive:
        return [
            EvidenceRecord(
                proposition_id=prop,
                status=EvidenceStatus.NEEDS_REVIEW.value,
                evidence_type="strong_contradicting",
                reasoning=body,
                confidence=0.9,  # نشانه‌های صریح بدفهمی در متن مدل
                error_type="conceptual",
                needs_teacher_review=False,
                qualitative_feedback=body,
            )
            for prop in propositions
        ]
    return [
        EvidenceRecord(
            proposition_id=prop,
            status=EvidenceStatus.UNCLEAR.value,
            evidence_type="weak_confirming",
            reasoning=body[:600],
            confidence=0.0,
            error_type="none",
            needs_teacher_review=True,
            qualitative_feedback=body,
        )
        for prop in propositions
    ]


def _fallback_records(propositions: list[str], reason: str, raw_excerpt: str = "") -> list[EvidenceRecord]:
    cleaned = _clean_raw_text(raw_excerpt) if raw_excerpt else ""
    feedback = cleaned or reason                     # هرگز بنر خطای ثابت
    body = (cleaned or reason)[:600] if cleaned else reason

    return [
        EvidenceRecord(
            proposition_id=prop,
            status=EvidenceStatus.UNCLEAR.value,
            evidence_type="weak_confirming",
            reasoning=body,
            confidence=0.0,
            error_type="none",
            needs_teacher_review=True,
            qualitative_feedback=feedback,
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
            raw_output = (getattr(resp, "text", "") or "").strip()
            if raw_output:
                print("[Analyzer] JSON parse failed — using raw model output as evidence (decisive if misconception markers found).")
                return _records_from_raw_text(raw_output[:1200], propositions)
            print("[Analyzer] Model returned empty output.")
            return _fallback_records(propositions, "مدل هیچ خروجی‌ای برنگرداند.")
        qualitative_feedback = str(data.get("qualitative_feedback") or "").strip()
        records = [_normalize_record(item, propositions[0], qualitative_feedback) for item in data["evidence"] if isinstance(item, dict)]
        if not records:
            raw_output = (getattr(resp, "text", "") or "").strip()
            if raw_output:
                print("[Analyzer] Evidence structure invalid — using raw model output as evidence.")
                return _records_from_raw_text(raw_output[:1200], propositions)
            print("[Analyzer] Model returned empty evidence and empty text.")
            return _fallback_records(propositions, "خروجی مدل خالی بود.")
        return records
    except Exception as exc:
        # هیچ‌وقت جلسه را به‌خاطر خطای تحلیل متوقف نکن
        raw_output = (locals().get("resp") and getattr(locals()["resp"], "text", "") or "").strip()
        if raw_output:
            print(f"[Analyzer] Exception ({exc}) — using raw model output as evidence.")
            return _records_from_raw_text(raw_output[:1200], propositions)
        print(f"[Analyzer] analysis exception: {exc}")
        return _fallback_records(propositions, f"تحلیل خودکار ناموفق بود ({exc}) — نیازمند بررسی معلم است.")

_EXAM_PROMPT = """شما «متخصص ارشد تشخیص آموزشیِ سخت‌گیرِ فهم‌یار» هستید. کل دفترچهٔ آزمون ({q_count} سؤال) و همهٔ پاسخ‌های دانش‌آموز را یکپارچه تحلیل کنید — نه سؤال‌به‌سؤال جدا.

قواعد:
1. فقط JSON معتبر برگردانید. هیچ متن توضیحی قبل یا بعد از JSON (حتی یک کلمه) ننویسید. پاسخ دقیقاً با «{{» شروع و با «}}» پایان یابد.
2. الگوهای تکرارشونده بین پاسخ‌ها را بیابید: بدفهمیِ ثابت؟ خطای محاسباتیِ سیستماتیک؟ استدلال علّی ناقص؟ دانشِ حفظی بدون فهم؟
3. برای هر سؤال دقیقاً یک آیتم در "per_question" بدهید:
   - status: CONFIRMED | LIKELY_UNDERSTOOD | UNCLEAR | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE
     * فقط غلط علمی روشن (تضاد با مبانی) → NEEDS_REVIEW؛ دقیقاً بنویسید دانش‌آموز به اشتباه تصور می‌کند که …
     * UNCLEAR فقط برای بی‌ربط/نامفهوم.
   - error_type: conceptual | computational | misreading | none
   - qualitative_feedback: ۱ تا ۳ جملهٔ مستقیم؛ چه چیزی درست/غلط است و چرا (متنِ دقیق برای معلم و دانش‌آموز).
4. "dimension_findings": ۴ تا ۶ بُعد فهم (مثلاً «فهم مفهومی/علّی»، «کاربرد واقعی»، «خواندن نمودار و داده»، «ردیابی بدفهمی شایع»، «رویهٔ حل‌سازی»، «تعریف و مرزبندی مفهوم») با status و finding یک‌جمله‌ای.
5. "root_cause_hypotheses": ریشه‌های احتمالی در دروس پایه/ریاضی (مثلاً «ضعف در نسبت و تناسب (ریاضی پایهٔ ۷-۹)») یا بدفهمیِ بنیادینِ مفهومی؛ به‌ترتیب احتمال.
6. "improvement_suggestions": ۴ تا ۶ راهکار عملی و متن‌محور (بدون نمره/رتبه/درصد)؛ ابتدا مرور پیش‌نیازها، سپس تمرین هدفمند.
7. هیچ نمره، رتبه، درصد یا مقایسه‌ای ننویسید. تحلیل کیفیِ مستقیم و قاطع.

خروجی دقیقاً این ساختار:
{{
  "per_question": [
    {{
      "question_id": <شناسهٔ عددی سؤال ورودی>,
      "status": "...",
      "evidence_type": "strong_confirming | weak_confirming | computational_success | weak_contradicting | strong_contradicting",
      "error_type": "conceptual | computational | misreading | none",
      "reasoning": "حکم قطعی + دلیل (فارسی، بدون کلمات تردید)",
      "confidence": 0.0,
      "needs_teacher_review": false,
      "qualitative_feedback": "دلیل دقیق رد/تأیید پاسخ — متنِ نهایی برای گزارش"
    }}
  ],
  "dimension_findings": [
    {{"dimension": "فهم مفهومی/علّی", "status": "...", "finding": "یک جمله"}}
  ],
  "root_cause_hypotheses": [
    {{"area": "…", "reasoning": "چرا این ریشه محتمل است", "cross_subject": false}}
  ],
  "improvement_suggestions": ["راهکار ۱", "راهکار ۲"]
}}

<<<CONCEPT>>>{concept_name}<<<END>>>
<<<PROPOSITIONS>>>{propositions_json}<<<END>>>
<<<ANSWERS>>>
{answers_block}
<<<END>>>
"""


async def analyze_exam(concept_name: str, propositions: list[str], items: list[dict]) -> dict[str, Any]:
    """تحلیل یکپارچهٔ کل دفترچهٔ آزمون. هرگز استثنا پرتاب نمی‌کند؛ در شکست، شواهد خام حفظ می‌شوند.

    items: [{"question_id": int, "order": int, "exam_type": str, "text": str,
              "mapped_propositions": [str], "response_text": str}]
    """
    propositions = list(propositions or [])
    items = [i for i in (items or []) if isinstance(i, dict)]

    answers_block = "\n\n".join(
        f"<<<Q{idx}>>>question_id={i.get('question_id')} | type={i.get('exam_type')} | گزاره={json.dumps(i.get('mapped_propositions') or [], ensure_ascii=False)}\n"
        f"سؤال: {str(i.get('text') or '').strip()}\n"
        f"پاسخ دانش‌آموز: {str(i.get('response_text') or '').strip() or '(بدون پاسخ)'}"
        for idx, i in enumerate(items, start=1)
    )
    prompt = _EXAM_PROMPT.format(
        q_count=len(items),
        concept_name=concept_name,
        propositions_json=json.dumps(propositions, ensure_ascii=False),
        answers_block=answers_block,
    )

    data: Optional[dict[str, Any]] = None
    raw_text = ""
    try:
        router = get_router()
        resp = await router.generate(prompt, "analyze_exam", temperature=0.2)
        raw_text = (getattr(resp, "text", "") or "").strip()
        data = _extract_json(raw_text)
    except Exception as exc:
        print(f"[ExamAnalyzer] model call failed: {exc}")

    if not isinstance(data, dict):
        # بدنه‌اش خراب است — متن خام را عیناً در هر سؤالِ بی‌جواب می‌نشانیم
        body = _clean_raw_text(raw_text) if raw_text else "تحلیل‌گر خودکار خروجی نداد؛ جلسه برای معلم محفوظ است."
        per_question = [
            {
                **_decisive_or_clear_record(
                    {"question_id": i.get("question_id"), "reasoning": body, "confidence": 0.0,
                     "error_type": "none", "evidence_type": "weak_confirming",
                     "needs_teacher_review": True, "qualitative_feedback": body},
                    str((i.get("mapped_propositions") or [f"سؤال #{i.get('question_id')}"])[0]),
                ),
                "question_id": i.get("question_id"),
                "order": i.get("order"),
                "exam_type": i.get("exam_type"),
                "question_text": str(i.get("text") or "").strip(),
            }
            for i in items
        ]
        return {
            "per_question": per_question,
            "dimension_findings": [
                {"dimension": "تحلیل یکپارچهٔ آزمون", "status": "UNCLEAR",
                 "finding": "خروجی مدل قابل‌ساختاردهی نبود؛ متن خام مدل در تحلیل تک‌تک سؤالات پیوست است."},
            ],
            "root_cause_hypotheses": [],
            "improvement_suggestions": ["معلم باید شخصاً این آزمون را بررسی کند؛ تحلیل خودکار قابل‌اتکا نبود."],
        }

    # ── نرمال‌سازی per_question ──
    by_id = {int(i.get("question_id")): i for i in items if str(i.get("question_id", "")).isdigit()}
    per_question = []
    for q in (data.get("per_question") or []):
        if not isinstance(q, dict):
            continue
        try:
            qid = int(q.get("question_id"))
        except (TypeError, ValueError):
            continue
        if qid not in by_id:
            continue  # مدل شناسهٔ نامعتبر/خیالین برگردانده — رکورد را نمی‌پذیریم
        src = by_id.get(qid) or {}
        prop = str((src.get("mapped_propositions") or [f"سؤال #{qid}"])[0])
        record = _decisive_or_clear_record(q, prop)
        record["question_id"] = qid
        record["order"] = src.get("order")
        record["exam_type"] = src.get("exam_type")
        record["question_text"] = str(src.get("text") or "").strip()
        per_question.append(record)

    # هر سؤال بدون رکورد → رکورد حداقلی
    covered = {q["question_id"] for q in per_question}
    for i in items:
        qid = i.get("question_id")
        if qid not in covered:
            body = "پاسخی برای این سؤال ثبت نشد یا تحلیل‌گر آن را پوشش نداد."
            per_question.append({
                "proposition_id": str((i.get("mapped_propositions") or [f"سؤال #{qid}"])[0]),
                "status": EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
                "evidence_type": "weak_confirming",
                "reasoning": body,
                "confidence": 0.0,
                "error_type": "none",
                "needs_teacher_review": True,
                "qualitative_feedback": body,
                "question_id": qid,
                "order": i.get("order"),
                "exam_type": i.get("exam_type"),
                "question_text": str(i.get("text") or "").strip(),
            })
    per_question.sort(key=lambda q: (q.get("order") or 999))

    # ── نرمال‌سازی ابعاد و ریشه‌ها و پیشنهادها ──
    dimensions = []
    for d in (data.get("dimension_findings") or []):
        if not isinstance(d, dict):
            continue
        dim = str(d.get("dimension") or "").strip()
        finding = _strip_hedges(str(d.get("finding") or "").strip())
        if not dim or not finding:
            continue
        status = str(d.get("status") or "UNCLEAR").upper().strip()
        if _has_decisive_misconception_marker(finding + " " + dim):
            status = EvidenceStatus.NEEDS_REVIEW.value
        elif status not in _VALID_STATUS:
            status = EvidenceStatus.UNCLEAR.value
        dimensions.append({"dimension": dim, "status": status, "finding": finding})

    root_causes = []
    for h in (data.get("root_cause_hypotheses") or []):
        if not isinstance(h, dict):
            continue
        area = str(h.get("area") or "").strip()
        reasoning = _strip_hedges(str(h.get("reasoning") or "").strip())
        if not area:
            continue
        root_causes.append({"area": area, "reasoning": reasoning, "cross_subject": bool(h.get("cross_subject", False))})

    suggestions = [
        _strip_hedges(str(x).strip()) for x in (data.get("improvement_suggestions") or [])
        if str(x).strip()
    ][:6]
    if not suggestions:
        suggestions = ["معلم باید بر اساس این آزمون، مسیر مرور پیش‌نیازها را شخصاً تعیین کند."]

    return {
        "per_question": per_question,
        "dimension_findings": dimensions,
        "root_cause_hypotheses": root_causes,
        "improvement_suggestions": suggestions,
    }


def _decisive_or_clear_record(item: dict[str, Any], fallback_prop: str) -> dict[str, Any]:
    """همان قواعد نرمالایزر قاطع — خروجی دیکشنری (برای آزمون جامع)."""
    status = str(item.get("status") or "UNCLEAR").upper().strip()
    if status not in _VALID_STATUS:
        status = EvidenceStatus.UNCLEAR.value
    etype = str(item.get("evidence_type") or "weak_confirming").lower().strip()
    if etype not in _VALID_EVIDENCE_TYPES:
        etype = "weak_confirming"
    error_type = str(item.get("error_type") or "none").lower().strip()
    if error_type not in _VALID_ERROR_TYPES:
        error_type = "none"
    try:
        confidence = min(1.0, max(0.0, float(item.get("confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = _strip_hedges(str(item.get("reasoning") or "").strip()) or "بدون توضیح تحلیل‌گر"
    feedback = _strip_hedges(str(item.get("qualitative_feedback") or reasoning).strip())
    decisive_text = _has_decisive_misconception_marker(reasoning + " " + feedback)
    decisive_struct = error_type == "conceptual" and (
        etype in ("strong_contradicting", "weak_contradicting") or status == EvidenceStatus.NEEDS_REVIEW.value
    )
    if decisive_text:
        status, confidence, needs_review = EvidenceStatus.NEEDS_REVIEW.value, 0.95, False
    elif decisive_struct:
        status, confidence, needs_review = EvidenceStatus.NEEDS_REVIEW.value, max(confidence, 0.9), False
    else:
        needs_review = bool(item.get("needs_teacher_review", False))
    return {
        "proposition_id": str(item.get("proposition_id") or fallback_prop).strip() or fallback_prop,
        "status": status,
        "evidence_type": etype,
        "reasoning": reasoning,
        "confidence": confidence,
        "error_type": error_type,
        "needs_teacher_review": needs_review,
        "qualitative_feedback": feedback or reasoning,
    }
