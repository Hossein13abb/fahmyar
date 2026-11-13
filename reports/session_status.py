"""منطق مشترک «وضعیت درک» (ECD) برای داشبوردها و اندپوینت‌ها.

هیچ نمره/رتبه/درصدی تولید نمی‌شود — خروجی صرفاً کیفی است (stable / growing / remedial / insufficient).
"""
from __future__ import annotations

from models.question import AssessmentSession, EvidenceStatus
from reports.report_generator import _aggregate_by_proposition, _final_prop_status

COMPREHENSION_LABELS = {
    "stable": "تثبیت شده",
    "growing": "در حال پرورش",
    "remedial": "نیازمند آموزش جبرانی",
    "insufficient": "شواهد ناکافی",
}

_CONFIRMING = (EvidenceStatus.CONFIRMED.value, EvidenceStatus.LIKELY_UNDERSTOOD.value)


def is_exam_session(session: AssessmentSession) -> bool:
    return any(h.get("type") in ("exam_booklet", "exam_meta") for h in (session.current_hypotheses or [])) or any(
        entry.get("exam_type") for entry in (session.evidence_log or [])
    )


def comprehension_status(session: AssessmentSession) -> str:
    """وضعیت درک دانش‌آموز در یک جلسهٔ تکمیل‌شده — بر پایهٔ خروجی موتور ECD."""
    if session.status == "insufficient_evidence":
        return "insufficient"
    entries = session.evidence_log or []
    if not entries:
        return "insufficient"

    if is_exam_session(session):
        statuses = []
        for entry in entries:
            evidence = entry.get("evidence") or []
            status = evidence[0].get("status") if evidence else None
            if status:
                statuses.append(str(status).upper())
    else:
        agg = _aggregate_by_proposition(session)
        statuses = [_final_prop_status(a["statuses"]) for a in agg.values()]

    if not statuses:
        return "insufficient"
    if any(s == EvidenceStatus.NEEDS_REVIEW.value for s in statuses):
        return "remedial"
    if all(s in _CONFIRMING for s in statuses):
        return "stable"
    if any(s in _CONFIRMING for s in statuses):
        return "growing"
    if all(s == EvidenceStatus.INSUFFICIENT_EVIDENCE.value for s in statuses):
        return "insufficient"
    return "growing"


def needs_teacher_review(session: AssessmentSession) -> bool:
    if is_exam_session(session):
        return any(
            bool((entry.get("evidence") or [{}])[0].get("needs_teacher_review"))
            for entry in (session.evidence_log or [])
        )
    return any(
        ev.get("needs_teacher_review")
        for entry in (session.evidence_log or [])
        for ev in entry.get("evidence", [])
    )
