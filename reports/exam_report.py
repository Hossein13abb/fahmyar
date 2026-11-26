"""گزارش تفصیلی آزمون جامع تشخیصی (Detailed Diagnostic Report) — کیفی، بدون نمره/رتبه/درصد.

ساختار ورودی (همان چیزی که submit-test ذخیره می‌کند):
  evidence_log: [{question_id, order?, exam_type?, question_text?, response, answered_at, evidence: [record]}]
  current_hypotheses:
      [{type: "exam_meta", dimensions: [{dimension, status, finding}], suggestions: [str]},
       {type: "root_cause", concept_name, status, reasoning, cross_subject}, ...]
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus, STATUS_FA
from ai.brand_terms import PUBLIC_STAGE_TITLES, scrub_deep
from ai.cross_check import normalize_suggestions
from reports.dimensions import build_stage_dimensions, DIMENSION_STATUS_FA
from reports.fa_map import (
    root_cause_text,
    normalize_dimension,
    normalize_exam_type,
    fa_text,
    dimension_fallback,
    feedback_fallback,
    suggestion_fallback,
)

def _model_name(meta: dict[str, Any], ai_usage: dict[str, Any]) -> str:
    """نامِ دقیقِ مدلی که این کارنامه را ارزیابی کرده است (بندِ ۳).

    ترتیبِ اولویت:
      ۱) مدلی که واقعاً فراخوانی شده (از usage واقعیِ OpenRouter) —
         صادقانه‌ترین منبع، چون همان مدل پول خورده است.
      ۲) مدلِ پین‌شدهٔ ارزیابی از تنظیمات.
    هرگز رشتهٔ ساختگی برنمی‌گرداند؛ اگر هیچ‌کدام نبود، «نامشخص» — نه نامِ مدلِ دیگر.
    """
    models = [str(m).strip() for m in (ai_usage.get("models") or []) if str(m).strip()]
    if models:
        # مدلِ غالب = پرارتباط‌ترین؛ اگر یکی بود همان.
        return models[0]
    pinned = str(meta.get("assessment_model") or "").strip()
    if pinned:
        return pinned
    try:
        from config import settings

        return str(settings.OPENROUTER_ASSESSMENT_MODEL or "").strip() or "نامشخص"
    except Exception:  # noqa: BLE001
        return "نامشخص"


def _strip_hedges_local(text: str) -> str:
    """تردیدهای لفظیِ رایج را از متنِ ریشه پاک می‌کند (بدون تغییر محتوای آموزشی)."""
    s = text
    for hedge in ("به نظر می‌رسد که ", "به نظر می‌رسد ", "احتمالاً ", "ممکن است "):
        s = s.replace(hedge, "")
    return s.strip()



# نشانگرهای خروجی خامِ مدل (دانش‌آموز فارسی‌زبان هرگز این‌ها را تایپ نمی‌کند)
_MODEL_MARKERS = (
    "<<<",
    '"per_question"', '"dimension_findings"', '"root_cause_hypotheses"', '"improvement_suggestions"',
)


def _looks_like_model_output(text: str) -> bool:
    """آیا این رشته شبیه خروجی خام/JSONِ مدل است؟ (برای اینکه آن را اشتباهی به‌عنوان پاسخ دانش‌آموز نشان ندهیم)"""
    t = (text or "").strip()
    if not t:
        return False
    if any(m in t for m in _MODEL_MARKERS):
        return True
    if t.startswith("{") and t.endswith("}"):
        try:
            obj = json.loads(t)
        except Exception:
            return False
        # کلیدهای اختصاصیِ تحلیل‌گر: اگر یکی از این‌ها در JSON بود، این رشته
        # خروجیِ مدل است، نه چیزی که دانش‌آموز تایپ کرده.
        return isinstance(obj, dict) and any(
            k in obj
            for k in (
                "per_question",
                "dimension_findings",
                "root_cause_hypotheses",
                "improvement_suggestions",
                "cognitive_verdict",
                "qualitative_feedback",
                "missing_gear",
                "mastery_status",
                "evidence_type",
                "expected_logic",
            )
        )
    return False


#: وضعیتِ پنج‌گانهٔ ابعاد → وضعیتِ شاهد (همان واژگانی که نرمال‌سازِ گزارش می‌فهمد)
_EVIDENCE_STATUS_FOR_DIM = {
    "mastered": EvidenceStatus.CONFIRMED.value,
    "developing": EvidenceStatus.LIKELY_UNDERSTOOD.value,
    "needs_work": EvidenceStatus.NEEDS_REVIEW.value,
    "not_assessed": EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
}


def _coerce_options_for_report(raw: Any) -> list[str]:
    """گزینه‌ها برای نمایش در کارنامه — بدونِ کلیدِ صحیح."""
    if not isinstance(raw, list):
        return []
    return [str(o) for o in raw if str(o or "").strip()]


def _coerce_selected(raw: Any) -> Optional[int]:
    """اندیسِ انتخاب‌شده را سالم می‌کند؛ فقط ۰..۳ معتبر است، بقیه None."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 3 else None


_TUTOR_KEYS = ("misconception_root", "intuitive_explanation", "golden_tip")


_RESOLUTION_KEYS = ("why_it_happened", "how_to_connect_bridge", "exam_shield_tip")


def _public_stage_title(order: Any) -> str:
    """«سؤال ۷ از ۱۰» → «بررسی استدلال علمی». هرگز نامِ متدولوژی.

    آزمونِ جامع ۱۰ سؤال دارد (۲ سؤال در هر مرحله)، پس تقسیم بر ۲ لازم است.
    ورودیِ نامعتبر به «سؤال تحلیلی» می‌افتد تا هیچ مصرف‌کننده‌ای ``None`` نگیرد.
    """
    try:
        n = int(order)
    except (TypeError, ValueError):
        return "سؤال تحلیلی"
    if n < 1:
        return "سؤال تحلیلی"
    stage = (n - 1) // 2 + 1
    return PUBLIC_STAGE_TITLES.get(stage, "سؤال تحلیلی")


def _contradiction_tutor_for_report(finding: dict[str, Any]) -> dict[str, Any]:
    """فیلدهای «معلمِ تناقض» را برای یک یافتهٔ کارنامه آماده می‌کند.

    فقط یافتهٔ ``CONTRADICTION`` دکمهٔ معلم می‌گیرد؛ برای بقیهٔ انواع،
    کلیدهای اضافه صادر نمی‌شوند تا فرانت مجبور نباشد حالتِ خالی را هم
    مدیریت کند. اگر مدل آموزش را نداد، متنی از توضیحِ خودِ یافته ساخته
    می‌شود — دکمه هرگز به پنجرهٔ خالی نمی‌رسد.
    """
    ftype = str(finding.get("type") or "").upper().strip()
    if ftype != "CONTRADICTION":
        return {}

    raw = finding.get("tutor_resolution")
    src = raw if isinstance(raw, dict) else {}
    resolution = {k: str(src.get(k) or "").strip() for k in _RESOLUTION_KEYS}
    for key, value in list(resolution.items()):
        if value and _looks_like_model_output(value):
            resolution[key] = ""

    title = str(finding.get("contradiction_title") or finding.get("title") or "").strip()
    description = str(finding.get("description") or "").strip()

    if not resolution["why_it_happened"]:
        resolution["why_it_happened"] = (
            f"بین دو جوابت فاصله افتاد: {description}"
            if description
            else "دو جوابت یک حرف را نمی‌زنند — و این یعنی یکی‌شان از حفظ "
            "آمده و آن یکی از شهودِ خودت."
        )
    if not resolution["how_to_connect_bridge"]:
        resolution["how_to_connect_bridge"] = (
            "هر دو پاسخ را کنارِ هم بگذار و ببین کدام‌شان با قانونِ اصلیِ "
            "مفهوم هم‌خوان است؛ همان یکی حرفِ آخر را می‌زند و آن یکی باید "
            "اصلاح شود."
        )
    if not resolution["exam_shield_tip"]:
        resolution["exam_shield_tip"] = (
            "قبل از زدنِ گزینه، یک بار با خودت بگو: «اگر همین را می‌خواستم "
            "تشریح کنم، همین جواب را می‌دادم؟» همان یک جمله، تناقض را لو می‌دهد."
        )

    return {
        "contradiction_title": title or "این دو حرفت با هم نمی‌خوانند",
        "tutor_resolution": resolution,
    }


def _coerce_tutor_for_report(record: dict[str, Any]) -> dict[str, str]:
    """``tutor_teaching`` را برای کارنامه آماده می‌کند.

    سه ضمانت:
      ۱. همیشه سه کلیدِ غیرخالی دارد (دکمهٔ معلم هرگز پنجرهٔ خالی باز نمی‌کند).
      ۲. متنِ خامِ مدل/JSONِ نشت‌کرده نمایش داده نمی‌شود.
      ۳. برای دادهٔ قدیمی (بدونِ فیلد) از متنِ تشخیصیِ موجود ساخته می‌شود.
    """
    raw = record.get("tutor_teaching")
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, str] = {}
    for key in _TUTOR_KEYS:
        value = str(src.get(key) or "").strip()
        if not value or _looks_like_model_output(value):
            value = ""
        out[key] = value

    verdict = str(record.get("cognitive_verdict") or "").strip()
    feedback = str(record.get("qualitative_feedback") or "").strip()
    missed = str(record.get("expected_logic_missed") or "").strip()
    wrong = str(record.get("wrong_claim") or "").strip()
    status = str(record.get("status") or "").upper()

    # همهٔ متن‌ها با لحنِ دومِ‌شخصِ معلم نوشته می‌شوند (قراردادِ فاز ۱۳).
    if not out["misconception_root"]:
        if status == EvidenceStatus.CONFIRMED.value or status == "CORRECT":
            out["misconception_root"] = (
                "این‌جا لغزشی نداشتی؛ استدلالت کامل بود. بیا یک قدم عمیق‌ترش کنیم."
            )
        elif wrong:
            out["misconception_root"] = (
                f"ببین دوست من! تو روی این فرض ایستادی: «{wrong}» — و همین "
                "فرض، بقیهٔ استدلالت را با خودش برد."
            )
        else:
            out["misconception_root"] = (
                verdict or "استدلالت در میانهٔ راه لنگ زد — بیا کاملش کنیم."
            )

    if not out["intuitive_explanation"]:
        out["intuitive_explanation"] = feedback or (
            f"بیا قدم‌به‌قدم برویم: {missed}"
            if missed
            else "بیا این مفهوم را از پایه با هم بسازیم — بی‌آنکه فرمولی حفظ "
            "کنی. یک مثالِ روزمره‌اش را برایم تصور کن و از همان‌جا شروع کنیم."
        )

    if not out["golden_tip"]:
        out["golden_tip"] = (
            "رمزِ طلایی: قبل از هر محاسبه از خودت بپرس «کدام کمیت واقعاً "
            "این‌جا نقش دارد و کدام یکی فقط تماشاچی است؟»"
        )
    return out


def _diagnostic_fallback(record: dict[str, Any]) -> str:
    """تشخیصِ یک‌خطی برای دادهٔ قدیمی که فیلدِ ``diagnostic_insight`` ندارد."""
    status = str(record.get("status") or "").upper()
    if status in ("CORRECT", EvidenceStatus.CONFIRMED.value):
        return "استدلالت در این بخش با منطقِ موردانتظار هم‌خوان بود."
    if status == "HALF_CORRECT":
        return "هستهٔ استدلالت درست بود، اما حلقهٔ تعیین‌کننده‌اش کامل گفته نشد."
    if status == "WRONG":
        return "استدلالت به نتیجه‌ای می‌رسد که با رفتارِ واقعیِ سیستم نمی‌خواند."
    return "برای این سؤال شاهدی ثبت نشد؛ داوری ممکن نبود."


def _selected_text_for_report(entry: dict[str, Any]) -> Optional[str]:
    """متنِ گزینهٔ انتخاب‌شده — ذخیره‌شده در evidence_log، با بازسازی از options.

    اگر متنِ ذخیره‌شده نبود (دادهٔ قدیمی)، از همان اندیس و لیستِ گزینه‌ها
    بازسازی می‌شود تا کارنامه هرگز «گزینهٔ ۲: » با متنِ خالی نشان ندهد.
    """
    stored = str(entry.get("selected_option_text") or "").strip()
    if stored:
        return stored
    index = _coerce_selected(entry.get("selected_option_index"))
    options = _coerce_options_for_report(entry.get("options"))
    if index is not None and 0 <= index < len(options):
        return options[index]
    return None


def _raw_student_answer(entry: dict[str, Any]) -> str:
    """فقط و فقط متنِ خامی که دانش‌آموز تایپ کرده برمی‌گرداند.

    - هیچ‌گاه خروجی JSONِ مدل، متون فال‌بکِ تحلیل‌گر یا reasoning/feedback را در فیلد response کپی نمی‌کند.
    - اگر به‌هر دلیلی (مثلاً دادهٔ قدیمی) رشته‌ای شبیهِ خروجی مدل در entry["response"] نشسته باشد،
      به‌جای نمایشِ آن، پاسخ خالی برمی‌گرداند تا UI «پاسخی ثبت نشده بود» نشان دهد.
    """
    resp = entry.get("response", "")
    if resp is None:
        return ""
    resp = str(resp).strip()
    if _looks_like_model_output(resp):
        return ""
    return resp


_TYPE_ORDER = {"conceptual": 1, "real_world": 2, "diagram": 3, "misconception_trap": 4, "computational": 5, "definitional": 6}


def build_exam_report(db: Session, session: AssessmentSession) -> dict[str, Any]:
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    concept_name = concept.name if concept else "نامشخص"

    per_question: list[dict[str, Any]] = []
    for entry in (session.evidence_log or []):
        record = (entry.get("evidence") or [{}])[0] if isinstance(entry.get("evidence"), list) else {}
        per_question.append({
            "question_id": entry.get("question_id"),
            "order": entry.get("order"),
            "exam_type": normalize_exam_type(entry.get("exam_type") or record.get("exam_type")),
            "exam_type_raw": entry.get("exam_type") or record.get("exam_type"),
            "question_text": entry.get("question_text") or record.get("question_text") or "",
            "status": record.get("status", EvidenceStatus.UNCLEAR.value),
            "evidence_type": record.get("evidence_type"),
            "error_type": record.get("error_type", "none"),
            # پاسخِ دانش‌آموز — فقط متنِ واقعیِ خودش (هرگز حکم/بازخوردِ مدل).
            "response": _raw_student_answer(entry),
            # انتخابِ گزینه در MCQ: صفرمبنا ذخیره، یک‌مبنا نمایش.
            "selected_option_index": _coerce_selected(entry.get("selected_option_index")),
            # متنِ گزینهٔ انتخاب‌شده، صریح و مستقل از گزینه‌ها (بندِ ۱-الف)
            "selected_option_text": _selected_text_for_report(entry),
            # متنِ گزینه‌ها لازم است تا کارنامه بتواند «گزینهٔ ۲: ۳ آمپر» را
            # نشان دهد. خودِ correct_option_index هرگز به فرانت نمی‌رود.
            "options": _coerce_options_for_report(entry.get("options")),
            "reasoning": fa_text(record.get("reasoning", ""), feedback_fallback(record.get("status", ""))),
            "qualitative_feedback": fa_text(
                record.get("qualitative_feedback") or record.get("reasoning") or "",
                feedback_fallback(record.get("status", "")),
            ),
            "confidence": record.get("confidence", 0.0),
            "needs_teacher_review": bool(record.get("needs_teacher_review", False)),
            # فاز ۷ — کارنامهٔ X-Ray
            # فاز ۱۷: عنوانِ مرحله همیشه برچسبِ عمومی است، از شمارهٔ ترتیب
            # ساخته می‌شود — نه از ``stage_title`` ذخیره‌شده که در آزمون‌های
            # قدیمی نامِ متدولوژیِ داخلی دارد. (رقمِ فارسی هم همین‌جا درست
            # می‌شود؛ «مرحله 1» با رقمِ لاتین در تصاویر دیده شده بود.)
            "stage_title": _public_stage_title(entry.get("order")),
            "cognitive_verdict": record.get("cognitive_verdict"),
            # فاز ۲۰: missing_gear حذف شد — کارنامه دیگر بجِ 「گره‌های کلیدی」
            # را رندر نمی‌کند و این فیلد مصرف‌کننده‌ای ندارد.
            # ── معلمِ هوشمند (فاز ۱۲) ──
            # این آبجکت در همان فراخوانیِ اولِ ارزیابی ساخته می‌شود؛ کارنامه
            # فقط آن را منتقل می‌کند و هیچ کالِ اضافه‌ای به مدل نمی‌زند.
            "student_answer_summary": record.get("student_answer_summary") or "",
            "diagnostic_insight": record.get("diagnostic_insight")
            or _diagnostic_fallback(record),
            "tutor_teaching": _coerce_tutor_for_report(record),
        })
    per_question.sort(key=lambda q: (q.get("order") or 999))

    # ── فاز ۱۰: پنج بُعدِ استاندارد، از شواهدِ واقعیِ پنج مرحله ──
    # دیگر از dimension_findings آزادِ مدل ساخته نمی‌شود؛ کلیدها ثابت‌اند
    # (conceptual_knowledge … simple_communication) و هیچ بعدی «نامشخص»
    # نمی‌ماند مگر آن مرحله واقعاً بی‌پاسخ باشد.
    stage_dimensions = build_stage_dimensions(per_question)

    hypotheses = list(session.current_hypotheses or [])
    meta = next((h for h in hypotheses if h.get("type") == "exam_meta"), {})
    dimensions = list(meta.get("dimensions") or [])
    suggestions = list(meta.get("suggestions") or [])
    cross_check_findings = [
        {
            "title": str(f.get("title") or "").strip(),
            "type": str(f.get("type") or "SYNERGY").upper().strip(),
            "description": str(f.get("description") or "").strip(),
            "resolution": f.get("resolution"),
            **_contradiction_tutor_for_report(f),
        }
        for f in (meta.get("cross_check_findings") or [])
        if isinstance(f, dict) and str(f.get("title") or "").strip()
    ]
    mastery_status = meta.get("mastery_status")
    persona_title = meta.get("persona_title")
    executive_summary = meta.get("executive_summary")
    needs_clarification = bool(meta.get("needs_clarification"))
    # مصرفِ مدل: مجموعِ هزینه/توکنِ همین آزمون (از usage واقعیِ OpenRouter)
    ai_usage = meta.get("ai_usage") if isinstance(meta.get("ai_usage"), dict) else {}
    clarification_data = meta.get("clarification_data") if needs_clarification else None

    if not dimensions:
        # گزارش بدون تحلیلِ آزادِ مدل: پنج بُعدِ استاندارد جای خالی را پر می‌کنند.
        # وضعیت‌ها با کلیدِ *انگلیسیِ* شناخته‌شده داده می‌شوند تا نرمال‌سازِ
        # پایین‌دست آن‌ها را به «نامشخص» برنگرداند (برچسبِ فارسی این‌جا
        # شناخته نمی‌شود و به UNCLEAR می‌افتاد — همان باگِ «همه نامشخص»).
        dimensions = [
            {
                "dimension": d["label"],
                "status": _EVIDENCE_STATUS_FOR_DIM[d["status"]],
                "finding": d["finding"],
            }
            for d in stage_dimensions
        ]
    if not suggestions:
        suggestions = ["معلم باید بر اساس پاسخ‌ها مسیر مرور را شخصاً تعیین کند."]

    norm_dimensions = []
    for d in dimensions:
        if not isinstance(d, dict):
            continue
        st = str(d.get("status") or EvidenceStatus.UNCLEAR.value).upper()
        norm_dimensions.append({
            "dimension": normalize_dimension(d.get("dimension")),
            "status": st if st in STATUS_FA else EvidenceStatus.UNCLEAR.value,
            "finding": fa_text(d.get("finding"), dimension_fallback(st)),
        })
    dimensions = norm_dimensions
    # فاز ۲۰: root_causes حذف شد. گرافِ وابستگی از کارنامه رفت و این فهرست
    # مصرف‌کننده‌ای نداشت؛ نگه‌داشتنش یعنی محاسبه و انتقالِ دادهٔ مرده.
    # دادهٔ خامِ hypotheses در meta می‌ماند (برای معلم و دیباگ).

    dimension_lines = [
        f"«{d['dimension']}» — {STATUS_FA.get(d['status'], d['status'])}: {d['finding']}" for d in dimensions
    ]
    per_question_lines = [
        f"سؤال {q.get('order') or i + 1} ({q.get('exam_type') or '—'}): {STATUS_FA.get(q['status'], q['status'])} — {q['qualitative_feedback']}"
        for i, q in enumerate(per_question)
    ]
    # فاز ۲۰: بخشِ «ریشه‌ها» از PDF حذف شد؛ همان اطلاعات در dimension_lines
    # با زبانِ ساده‌تر آمده است. (نگه‌داشتنِ این متغیر، مرجعِ مرده می‌ساخت.)

    report = {
        "exam": True,
        "session_id": session.id,
        "student_id": session.student_id,
        "concept_id": session.concept_id,
        "concept_name": concept_name,
        "status": session.status,
        "questions_answered": len(session.evidence_log or []),
        "dimensions": dimensions,
        "per_question": per_question,
        "suggestions": suggestions,
        "sections": {
            "موضوع بررسی": concept_name,
            "زمینه": "زنجیرهٔ فهم‌سنجی ۵ مرحله‌ای (کل به جزء و شکار تناقض) — بدون بازخورد لحظه‌ای",
            "شکارِ تناقض (Cross-Check)": [
                f"[{f['type']}] {f['title']}: {f['description']}" for f in cross_check_findings
            ] or ["تناقضِ روشنی میان پاسخ‌ها پیدا نشد."],
            "نمای کلی وضعیت": dimension_lines,
            "تحلیل تک‌تک سوالات": per_question_lines,
            # فاز ۲۰: «تحلیل ریشه‌ای» و «موارد هنوز روشن‌نشده» حذف شدند.
            # ترتیبِ PDF حالا آینهٔ کارنامه است: تحلیل سؤال‌ها، بعد پیشنهادهای
            # عملی به‌عنوان جمع‌بندیِ نهایی.
            "پیشنهادهای بهبود": suggestions,
        },
        # --- فاز ۷: کارنامهٔ X-Ray ---
        "ai_usage": {
            "models": ai_usage.get("models") or [],
            "call_count": ai_usage.get("call_count") or 0,
            "total_tokens": ai_usage.get("total_tokens") or 0,
            "prompt_tokens": ai_usage.get("prompt_tokens") or 0,
            "completion_tokens": ai_usage.get("completion_tokens") or 0,
            "total_cost_usd": ai_usage.get("total_cost_usd") or 0.0,
        },
        # پنج بُعدِ استاندارد — منبعِ «ابعاد فهم — تحلیل کلی» در فرانت
        "stage_dimensions": stage_dimensions,
        # نامِ دقیقِ مدلِ ارزیاب (بندِ ۳) — برای بجِ بالای کارنامه
        "model_name": _model_name(meta, ai_usage),
        "mastery_status": mastery_status,
        "persona_title": persona_title,
        "executive_summary": executive_summary,
        "cross_check_findings": cross_check_findings,
        "needs_clarification": needs_clarification,
        "clarification_data": clarification_data,
        "mastery_note": meta.get("mastery_note"),
        "exam_score_note": "توجه: نمرهٔ آزمون — نه سنجش فهم. این کارنامه نمره/رتبه/درصد ندارد و فقط شواهدِ کیفی را ثبت می‌کند.",
        "generated_at": datetime.utcnow().isoformat(),
        # عمداً: هیچ نمره/رتبه/درصد/مقایسه‌ای در گزارش وجود ندارد
    }
    # ── دروازهٔ زبانِ عمومی (فاز ۱۷) ──
    # این تابع از ``cognitive_report`` ذخیره‌شده در DB می‌خواند، پس گزارش‌های
    # قدیمی هنوز نامِ متدولوژیِ داخلی را داخل خلاصه دارند. سانسور در
    # ``build_exam_report`` تنها مسیرِ تولید نیست؛ پس همین‌جا هم لازم است.
    # scrub_deep فقط رشته‌ها را عوض می‌کند و ساختار دست‌نخورده می‌ماند.
    return scrub_deep(report)
