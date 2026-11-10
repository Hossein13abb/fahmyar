"""گزارش تفصیلی آزمون جامع تشخیصی (Detailed Diagnostic Report) — کیفی، بدون نمره/رتبه/درصد.

ساختار ورودی (همان چیزی که submit-test ذخیره می‌کند):
  evidence_log: [{question_id, order?, exam_type?, question_text?, response, answered_at, evidence: [record]}]
  current_hypotheses:
      [{type: "exam_meta", dimensions: [{dimension, status, finding}], suggestions: [str]},
       {type: "root_cause", concept_name, status, reasoning, cross_subject}, ...]
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus, STATUS_FA
from reports.fa_map import (
    root_cause_text,
    normalize_dimension,
    normalize_exam_type,
    fa_text,
    dimension_fallback,
    feedback_fallback,
    suggestion_fallback,
)

def _strip_hedges_local(text: str) -> str:
    """تردیدهای لفظیِ رایج را از متنِ ریشه پاک می‌کند (بدون تغییر محتوای آموزشی)."""
    s = text
    for hedge in ("به نظر می‌رسد که ", "به نظر می‌رسد ", "احتمالاً ", "ممکن است "):
        s = s.replace(hedge, "")
    return s.strip()


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
            "response": entry.get("response", ""),
            "reasoning": fa_text(record.get("reasoning", ""), feedback_fallback(record.get("status", ""))),
            "qualitative_feedback": fa_text(
                record.get("qualitative_feedback") or record.get("reasoning") or "",
                feedback_fallback(record.get("status", "")),
            ),
            "confidence": record.get("confidence", 0.0),
            "needs_teacher_review": bool(record.get("needs_teacher_review", False)),
        })
    per_question.sort(key=lambda q: (q.get("order") or 999))

    hypotheses = list(session.current_hypotheses or [])
    meta = next((h for h in hypotheses if h.get("type") == "exam_meta"), {})
    dimensions = list(meta.get("dimensions") or [])
    suggestions = list(meta.get("suggestions") or [])
    root_causes = [
        {"concept_name": root_cause_text(h.get("concept_name") or h.get("area")),
         "reasoning": _strip_hedges_local(root_cause_text(h.get("reasoning"))),
         "cross_subject": bool(h.get("cross_subject", False))}
        for h in hypotheses if h.get("type") == "root_cause"
    ]

    if not dimensions:
        # گزارش بدون تحلیل مدل (مثلاً شکست کامل) — ساختار را خالی نمی‌گذاریم
        dimensions = [{"dimension": "تحلیل یکپارچهٔ آزمون", "status": EvidenceStatus.UNCLEAR.value,
                       "finding": "تحلیل ابعادی انجام نشد؛ معلم باید شخصاً بررسی کند."}]
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
    root_causes = [
        {"concept_name": r.get("concept_name"), "area": r.get("concept_name"),
         "reasoning": r.get("reasoning"),
         "cross_subject": bool(r.get("cross_subject", False))}
        for r in root_causes
        if r.get("concept_name") or r.get("reasoning")
    ]
    # placeholderِ گمشده برای فیلدهایی که مدل اصلاً پر نکرده — هیچ جملهٔ ثابتی جایگزین نظر مدل نمی‌شود
    for r in root_causes:
        if not r["concept_name"]:
            r["concept_name"] = r["area"] = "عنوان ریشه ثبت نشد — معلم باید شخصاً بررسی کند"
        if not r["reasoning"]:
            r["reasoning"] = "تحلیل ریشه‌ای برای این بند ثبت نشد — معلم باید شخصاً بررسی کند"
    suggestions = [fa_text(x, suggestion_fallback()) for x in suggestions]

    dimension_lines = [
        f"«{d['dimension']}» — {STATUS_FA.get(d['status'], d['status'])}: {d['finding']}" for d in dimensions
    ]
    per_question_lines = [
        f"سؤال {q.get('order') or i + 1} ({q.get('exam_type') or '—'}): {STATUS_FA.get(q['status'], q['status'])} — {q['qualitative_feedback']}"
        for i, q in enumerate(per_question)
    ]
    root_cause_lines = [
        f"{r['concept_name']}{' (بین‌درسی)' if r.get('cross_subject') else ''}: {r['reasoning']}" for r in root_causes
    ] or ["بدفهمی ریشه‌دارِ تکرارشونده‌ای یافت نشد."]

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
        "root_causes": root_causes,
        "suggestions": suggestions,
        "sections": {
            "موضوع بررسی": concept_name,
            "زمینه": "آزمون جامع تشخیصی (۹–۱۰ سؤالی) — بدون بازخورد لحظه‌ای",
            "نمای کلی وضعیت": dimension_lines,
            "تحلیل تک‌تک سوالات": per_question_lines,
            "تحلیل ریشه‌ای بدفهمی‌ها": root_cause_lines,
            "پیشنهادهای بهبود": suggestions,
            "موارد هنوز روشن‌نشده": [
                f"سؤال {q.get('order') or i + 1} ({STATUS_FA.get(q['status'], q['status'])})"
                for i, q in enumerate(per_question)
                if q["status"] in (EvidenceStatus.UNCLEAR.value, EvidenceStatus.INSUFFICIENT_EVIDENCE.value)
            ] or ["موردِ مبهمی باقی نمانده است."],
        },
        "exam_score_note": "⚠️ نمرهٔ آزمون — نه سنجش فهم",
        "generated_at": datetime.utcnow().isoformat(),
        # عمداً: هیچ نمره/رتبه/درصد/مقایسه‌ای در گزارش وجود ندارد
    }
    return report
