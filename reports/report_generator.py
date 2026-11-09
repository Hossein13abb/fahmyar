"""ساخت گزارش کیفی فهم‌یار (به فارسی) — بدون نمره، رتبه یا مقایسه.

ساختار خروجی (دقیقاً مطابق قالب پروژه):
  موضوع بررسی / زمینه / مشاهدات / شواهد / موارد هنوز روشن‌نشده / پیشنهاد اقدام
  + برچسب «⚠️ نمرهٔ آزمون — نه سنجش فهم» در صورت وجود نمرهٔ امتحانی
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from config import settings
from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus

STATUS_FA_SHORT = {
    "CONFIRMED": "تأییدشده",
    "LIKELY_UNDERSTOOD": "احتمالاً آموخته‌شده",
    "UNCLEAR": "نامشخص (نیاز به گفت‌وگو/مثال‌های بیشتر)",
    "NEEDS_REVIEW": "بدفهمی شناسایی‌شده",
    "INSUFFICIENT_EVIDENCE": "فاقد شواهد کافی",
}

def _aggregate_by_proposition(session: AssessmentSession) -> dict[str, dict[str, Any]]:
    per_prop: dict[str, dict[str, Any]] = {}
    for entry in session.evidence_log or []:
        for ev in entry.get("evidence", []):
            prop = ev.get("proposition_id", "?")
            agg = per_prop.setdefault(
                prop,
                {
                    "statuses": [],
                    "reasonings": [],
                    "needs_teacher_review": False,
                    "error_types": set(),
                    "question_ids": set(),
                },
            )
            agg["statuses"].append(ev.get("status"))
            if ev.get("reasoning"):
                agg["reasonings"].append(ev["reasoning"])
            if ev.get("needs_teacher_review"):
                agg["needs_teacher_review"] = True
            if ev.get("error_type"):
                agg["error_types"].add(ev["error_type"])
            if entry.get("question_id") is not None:
                agg["question_ids"].add(entry["question_id"])
    return per_prop


def _final_prop_status(statuses: list[str]) -> str:
    """وضعیت نهایی یک گزاره بر پایهٔ همهٔ شواهدش (نسخهٔ گزارش)."""
    strong_contra = sum(1 for s in statuses if s == EvidenceStatus.NEEDS_REVIEW.value)
    confirming = sum(1 for s in statuses if s in (EvidenceStatus.CONFIRMED.value, EvidenceStatus.LIKELY_UNDERSTOOD.value))
    unclear = sum(1 for s in statuses if s == EvidenceStatus.UNCLEAR.value)
    if strong_contra and confirming:
        return EvidenceStatus.UNCLEAR.value
    if strong_contra:
        return EvidenceStatus.NEEDS_REVIEW.value
    if confirming >= 2:
        return EvidenceStatus.CONFIRMED.value
    if confirming == 1:
        return EvidenceStatus.LIKELY_UNDERSTOOD.value
    if unclear:
        return EvidenceStatus.UNCLEAR.value
    return EvidenceStatus.INSUFFICIENT_EVIDENCE.value


def build_report(db: Session, session: AssessmentSession) -> dict[str, Any]:
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    concept_name = concept.name if concept else "نامشخص"
    subject = concept.subject if concept else ""
    grade = concept.grade if concept else ""

    if session.trigger_type == "topic_selection":
        زمینه = f"شروع با انتخابِ موضوع/مفهوم ({concept_name})"
    else:
        زمینه = "شروع با پاسخِ غلط به یک سؤال (بررسی ریشهٔ خطا)"

    agg = _aggregate_by_proposition(session)

    # --- مشاهدات ---
    observations: list[str] = []
    for i, entry in enumerate(session.evidence_log or [], start=1):
        response = (entry.get("response") or "").strip().replace("\n", " ")
        quote = response[: settings.REPORT_RESPONSE_QUOTE_CHARS]
        if len(response) > settings.REPORT_RESPONSE_QUOTE_CHARS:
            quote += "…"
        if quote:
            observations.append(f"در پاسخ به سؤالِ {i}: «{quote}»")
        else:
            observations.append(f"سؤالِ {i}: پاسخی ثبت نشد.")
    needs_teacher = any(a["needs_teacher_review"] for a in agg.values())
    if needs_teacher:
        observations.append("در دست‌کم یک پاسخ، تحلیل‌گر خودکار برای قضاوت مطمئن نبود و نیازمند نگاه معلم است.")
    # بدفهمی‌های قطعی — با همان لحن قاطعِ تحلیل‌گر در مشاهدات می‌آیند
    for prop, a in agg.items():
        st = _final_prop_status(a["statuses"])
        if st == EvidenceStatus.NEEDS_REVIEW.value:
            qfs = [e.get("qualitative_feedback") for e in (e for entry in session.evidence_log or [] for e in entry.get("evidence", []))
                   if e.get("proposition_id") == prop and e.get("qualitative_feedback")]
            decisive = qfs[-1] if qfs else ((a["reasonings"] or [""])[-1])
            observations.append(f"بدفهمیِ شناسایی‌شده در گزارهٔ «{prop}»: {decisive}")

    # --- شواهد (گزاره به گزاره) ---
    evidence_lines: list[str] = []
    per_prop_status: dict[str, str] = {}
    for prop, a in agg.items():
        status = _final_prop_status(a["statuses"])
        per_prop_status[prop] = status
        reason = (a["reasonings"] or ["—"])[-1]
        evidence_lines.append(f"گزارهٔ «{prop}»: {STATUS_FA_SHORT.get(status, status)} — {reason}")
    if concept:
        for prop in concept.core_propositions or []:
            if prop not in per_prop_status:
                per_prop_status[prop] = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
                evidence_lines.append(f"گزارهٔ «{prop}»: {STATUS_FA_SHORT['INSUFFICIENT_EVIDENCE']} — در این جلسه دربارهٔ آن شواهدی جمع نشده است.")

    # --- موارد هنوز روشن‌نشده ---
    unclear_items = [
        prop for prop, st in per_prop_status.items()
        if st in (EvidenceStatus.UNCLEAR.value, EvidenceStatus.INSUFFICIENT_EVIDENCE.value)
    ]
    unclear_lines = [
        f"«{prop}» ({STATUS_FA_SHORT[per_prop_status[prop]]})" for prop in unclear_items
    ] or ["موردِ مبهمی باقی نمانده است."]

    # --- فرضیه‌های ریشهٔ خطا (مسیر B) ---
    root_cause_lines: list[str] = []
    for hyp in session.current_hypotheses or []:
        if hyp.get("type") == "root_cause":
            mark = {"pending": "بررسی‌نشده", "testing": "در حال بررسی", "supported": "تأییدشده",
                    "likely_root_cause": "مشکوک به ریشهٔ خطا", "rejected": "رد شده"}.get(hyp.get("status"), hyp.get("status"))
            cross = " (بین‌درسی)" if hyp.get("cross_subject") else ""
            root_cause_lines.append(f"{hyp.get('concept_name', hyp.get('concept_topic'))}{cross}: {mark}")

    # --- پیشنهاد اقدام ---
    student_actions: list[str] = []
    teacher_notes: list[str] = []
    for prop, st in per_prop_status.items():
        if st == EvidenceStatus.NEEDS_REVIEW.value:
            student_actions.append(f"بدفهمیِ گزارهٔ «{prop}» را مستقیم هدف بگیرید: ابتدا مثال‌های نقضِ شهودی سپس مسئله‌های ترکیبی.")
        elif st == EvidenceStatus.UNCLEAR.value:
            student_actions.append(f"گفت‌وگو و توضیحِ شفاهی دربارهٔ «{prop}»؛ از دانش‌آموز بخواهید فهمیدگیِ خود را با مثالِ خودش توضیح دهد.")
        elif st == EvidenceStatus.INSUFFICIENT_EVIDENCE.value:
            student_actions.append(f"هنوز دربارهٔ «{prop}» شواهد کافی نداریم؛ یک جلسهٔ دیگر یا تمرینِ تکمیلی لازم است.")
    if not student_actions:
        student_actions.append("عملکرد شما در این مفهوم خوب است؛ برای تثبیت، یک مسئلهٔ ترکیبیِ بین‌درسی حل کنید.")

    if needs_teacher:
        teacher_notes.append("پاسخ‌های بی‌ربط/نامفهوم که با «نیازمند بررسی معلم» علامت خورده‌اند را شخصاً بخوانید؛ تحلیل‌گر خودکار داوری نکرده است.")
    weak_props = [p for p, s in per_prop_status.items() if s == EvidenceStatus.NEEDS_REVIEW.value]
    if weak_props:
        teacher_notes.append("در جلسهٔ بعد ابتدا پیش‌نیازهای همین گزاره‌ها (و در صورت لزوم ابزارهای ریاضی) را مرور کنید.")
    if session.trigger_type == "wrong_answer":
        teacher_notes.append("این جلسه از یک پاسخ غلط شروع شد؛ مفهومِ اصلی و پیش‌نیازهایش با هم مرور شوند — به‌خصوص اگر فرضیهٔ بین‌درسی تأیید شد.")

    # --- متن گزارش (قالب ثابت) ---
    lines = [
        f"موضوع بررسی: {concept_name}" + (f" ({subject} — پایهٔ {grade})" if concept_name != "نامشخص" else ""),
        f"زمینه: {زمینه}",
        "",
        "مشاهدات:",
        *[f"- {o}" for o in (observations or ["پاسخی ثبت نشده است."])],
        "",
        "شواهد:",
        *[f"- {e}" for e in evidence_lines],
    ]
    if root_cause_lines:
        lines += ["", "فرضیه‌های ریشهٔ خطا:", *[f"- {r}" for r in root_cause_lines]]
    lines += [
        "",
        "موارد هنوز روشن‌نشده:",
        *[f"- {u}" for u in unclear_lines],
        "",
        "پیشنهاد اقدام:",
        *[f"- دانش‌آموز: {a}" for a in student_actions],
        *[f"- معلم: {t}" for t in teacher_notes],
        "",
        "⚠️ نمرهٔ آزمون — نه سنجش فهم: اگر در کنار این جلسه نمرهٔ امتحانی وجود دارد، صرفاً یک دادهٔ جداست و با «فهمیدن» یکی نیست؛ این گزارش جایگزینِ نمره‌گذاری نیست.",
    ]
    report_text = "\n".join(lines)

    return {
        "session_id": session.id,
        "student_id": session.student_id,
        "concept_id": session.concept_id,
        "concept_name": concept_name,
        "status": session.status,
        "questions_answered": len(session.evidence_log or []),
        "report_text": report_text,
        "sections": {
            "موضوع بررسی": concept_name,
            "زمینه": زمینه,
            "مشاهدات": observations,
            "شواهد": evidence_lines,
            "فرضیه‌های ریشهٔ خطا": root_cause_lines,
            "موارد هنوز روشن‌نشده": unclear_lines,
            "پیشنهاد اقدام برای دانش‌آموز": student_actions,
            "یادداشت برای معلم": teacher_notes,
        },
        "proposition_statuses": per_prop_status,
        "needs_teacher_review": needs_teacher,
        "exam_score_note": "⚠️ نمرهٔ آزمون — نه سنجش فهم",
        "generated_at": datetime.utcnow().isoformat(),
        # هیچ رتبه/درصد/مقایسه‌ای در خروجی وجود ندارد — عمداً
    }
