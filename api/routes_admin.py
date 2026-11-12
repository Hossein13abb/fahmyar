"""مسیرهای معلم/مدیر — داشبورد، گزارش دانش‌آموزان، تصویبِ سؤالات AI."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.routes_auth import get_current_user, require_roles
from api.routes_assessment import _concept_dict
from engine.session_manager import question_to_teacher_dict
from models.ai_log import AIUsageLog
from models.concept import Concept
from models.database import get_db
from models.question import AssessmentSession, EvidenceStatus, Question
from models.user import User
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi.responses import Response
from pydantic import BaseModel, Field

from reports.report_generator import build_report, _aggregate_by_proposition, _final_prop_status
from reports.exam_pdf import SUBJECT_LABELS, DIFFICULTY_LABELS, gather_questions, build_exam_pdf

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    from sqlalchemy import func

    return {
        "students": db.query(func.count(User.id)).filter(User.role == "student").scalar(),
        "concepts": db.query(func.count(Concept.id)).scalar(),
        "questions_total": db.query(func.count(Question.id)).scalar(),
        "questions_pending_approval": db.query(func.count(Question.id)).filter(Question.approval_status == "pending").scalar(),
        "sessions_total": db.query(func.count(AssessmentSession.id)).scalar(),
        "sessions_active": db.query(func.count(AssessmentSession.id)).filter(AssessmentSession.status == "active").scalar(),
        "ai_cost_usd": float(db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).scalar() or 0.0),
        "ai_calls": db.query(func.count(AIUsageLog.id)).scalar(),
    }


@router.get("/students/{student_id}/reports")
def student_reports(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    student = db.query(User).filter(User.id == student_id, User.role == "student").first()
    if student is None:
        raise HTTPException(status_code=404, detail="دانش‌آموز یافت نشد.")
    sessions = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.student_id == student_id)
        .order_by(AssessmentSession.started_at.desc())
        .all()
    )
    reports = []
    for s in sessions:
        concept = db.query(Concept).filter(Concept.id == s.concept_id).first() if s.concept_id else None
        reports.append(
            {
                "session_id": s.id,
                "concept_id": s.concept_id,
                "concept_name": concept.name if concept else None,
                "trigger_type": s.trigger_type,
                "status": s.status,
                "questions_answered": len(s.evidence_log or []),
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "needs_teacher_review": any(
                    ev.get("needs_teacher_review")
                    for entry in (s.evidence_log or [])
                    for ev in entry.get("evidence", [])
                ),
            }
        )
    return {"student": student.to_public_dict(), "sessions": reports}


@router.get("/students/{student_id}/reports/{session_id}")
def student_report_detail(
    student_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    session = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.id == session_id, AssessmentSession.student_id == student_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="جلسه یافت نشد.")
    exam_session = any(h.get("type") in ("exam_booklet", "exam_meta") for h in (session.current_hypotheses or [])) or any(
        entry.get("exam_type") for entry in (session.evidence_log or []))
    if exam_session:
        from reports.exam_report import build_exam_report

        report = build_exam_report(db, session)
        report["evidence_log"] = session.evidence_log or []
        report["hypotheses"] = session.current_hypotheses or []
        return report
    report = build_report(db, session)
    report["evidence_log"] = session.evidence_log or []
    report["hypotheses"] = session.current_hypotheses or []
    return report


@router.get("/students")
def list_students(
    grade: Optional[int] = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    q = db.query(User).filter(User.role == "student")
    if grade is not None:
        q = q.filter(User.grade == grade)
    students = q.order_by(User.grade, User.id).all()
    return {"count": len(students), "students": [s.to_public_dict() for s in students]}


@router.get("/questions/pending")
def pending_questions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    pending = (
        db.query(Question)
        .filter(Question.approval_status == "pending")
        .order_by(Question.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"count": len(pending), "questions": [question_to_teacher_dict(q) for q in pending]}


@router.post("/questions/{question_id}/approve")
def approve_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="سؤال یافت نشد.")
    question.approval_status = "approved"
    if question.source == "ai_generated":
        question.source = "teacher_approved"
    db.commit()
    return {"ok": True, "question": question_to_teacher_dict(question)}


@router.post("/questions/{question_id}/reject")
def reject_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="سؤال یافت نشد.")
    question.approval_status = "rejected"
    db.commit()
    return {"ok": True, "question_id": question.id, "approval_status": question.approval_status}


@router.get("/concepts/{concept_id}")
def concept_detail(
    concept_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if concept is None:
        raise HTTPException(status_code=404, detail="مفهوم یافت نشد.")
    data = _concept_dict(concept, include_propositions=True)
    data["common_misconceptions"] = concept.common_misconceptions or []
    return data
# ─────────────────────────────────────────────────────────────────────────────
# نتایج واقعی دانش‌آموزان (خروجی موتور تشخیص) — بدون هیچ دادهٔ Mock
# ─────────────────────────────────────────────────────────────────────────────

COMPREHENSION_LABELS = {
    "stable": "تثبیت شده",
    "growing": "در حال پرورش",
    "remedial": "نیازمند آموزش جبرانی",
    "insufficient": "شواهد ناکافی",
}

_CONFIRMING = (EvidenceStatus.CONFIRMED.value, EvidenceStatus.LIKELY_UNDERSTOOD.value)


def _is_exam_session(session: AssessmentSession) -> bool:
    return any(h.get("type") in ("exam_booklet", "exam_meta") for h in (session.current_hypotheses or [])) or any(
        entry.get("exam_type") for entry in (session.evidence_log or [])
    )


def _comprehension_status(session: AssessmentSession) -> str:
    """وضعیت درک دانش‌آموز در یک جلسهٔ تکمیل‌شده — بر پایهٔ خروجی موتور ECD."""
    if session.status == "insufficient_evidence":
        return "insufficient"
    entries = session.evidence_log or []
    if not entries:
        return "insufficient"

    if _is_exam_session(session):
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


def _needs_teacher_review(session: AssessmentSession) -> bool:
    if _is_exam_session(session):
        return any(
            bool((entry.get("evidence") or [{}])[0].get("needs_teacher_review"))
            for entry in (session.evidence_log or [])
        )
    return any(
        ev.get("needs_teacher_review")
        for entry in (session.evidence_log or [])
        for ev in entry.get("evidence", [])
    )


@router.get("/student-results")
def student_results(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    """فهرست واقعی دانش‌آموزان + آخرین آزمونِ ثبت‌شدهٔ هر کدام + وضعیت درک (ECD)."""
    students = db.query(User).filter(User.role == "student").order_by(User.grade, User.id).all()
    cutoff = datetime.utcnow() - timedelta(days=30)

    rows = []
    summary = {
        "students_total": len(students),
        "sessions_completed_total": 0,
        "reports_last_30_days": 0,
        "stable_count": 0,
        "growing_count": 0,
        "remedial_count": 0,
        "insufficient_count": 0,
    }

    for student in students:
        sessions = (
            db.query(AssessmentSession)
            .filter(
                AssessmentSession.student_id == student.id,
                AssessmentSession.status.in_(("completed", "insufficient_evidence")),
            )
            .order_by(AssessmentSession.started_at.desc())
            .all()
        )
        completed = len(sessions)
        summary["sessions_completed_total"] += completed
        summary["reports_last_30_days"] += sum(1 for s in sessions if s.started_at and s.started_at >= cutoff)

        latest = sessions[0] if sessions else None
        if latest is not None:
            concept = db.query(Concept).filter(Concept.id == latest.concept_id).first() if latest.concept_id else None
            comprehension = _comprehension_status(latest)
            rows.append(
                {
                    "student": student.to_public_dict(),
                    "grade": student.grade,
                    "last_session_id": latest.id,
                    "concept_id": latest.concept_id,
                    "concept_name": concept.name if concept else None,
                    "subject": concept.subject if concept else None,
                    "session_status": latest.status,
                    "comprehension": comprehension,
                    "comprehension_label": COMPREHENSION_LABELS[comprehension],
                    "questions_answered": len(latest.evidence_log or []),
                    "exam_date": latest.started_at.isoformat() if latest.started_at else None,
                    "completed_exams": completed,
                    "needs_teacher_review": _needs_teacher_review(latest),
                }
            )
        else:
            rows.append(
                {
                    "student": student.to_public_dict(),
                    "grade": student.grade,
                    "last_session_id": None,
                    "concept_id": None,
                    "concept_name": None,
                    "subject": None,
                    "session_status": None,
                    "comprehension": "insufficient",
                    "comprehension_label": COMPREHENSION_LABELS["insufficient"],
                    "questions_answered": 0,
                    "exam_date": None,
                    "completed_exams": 0,
                    "needs_teacher_review": False,
                }
            )
        summary[f"{rows[-1]['comprehension']}_count"] += 1

    return {"count": len(rows), "summary": summary, "students": rows}


# ─────────────────────────────────────────────────────────────────────────────
# تولید PDF واقعی آزمون — دفترچهٔ سؤالات + پاسخنامهٔ تشریحی (کلید معلم)
# ─────────────────────────────────────────────────────────────────────────────

class GenerateExamPdfRequest(BaseModel):
    title: str = Field(default="", max_length=140)
    school_name: str = Field(default="مدرسهٔ نمونه", max_length=140)
    subjects: list[str] = Field(min_length=1, max_length=len(SUBJECT_LABELS))
    counts: dict[str, int] = Field(default_factory=dict)
    duration_minutes: int = Field(default=75, ge=10, le=240)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|challenging)$")
    source: str = Field(default="hybrid", pattern="^(bank|ai|hybrid)$")
    bank_share: int = Field(default=60, ge=10, le=90)


@router.post("/generate-exam-pdf")
def generate_exam_pdf(
    payload: GenerateExamPdfRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin")),
):
    """یک آزمون واقعی می‌سازد (بانک مؤسسات + مدل فعال) و یک PDF دوبخشی برمی‌گرداند:
    ۱) دفترچهٔ سؤالات با سربرگ استاندارد  ۲) پاسخنامهٔ تشریحی (مختص دبیر)."""
    unknown = [s for s in payload.subjects if s not in SUBJECT_LABELS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"درسِ نامعتبر: {', '.join(unknown)}")

    school_name = (payload.school_name or "").strip() or "مدرسهٔ نمونه"
    title = (payload.title or "").strip() or (
        "آزمون جامع تشخیصی — " + " + ".join(SUBJECT_LABELS[s] for s in dict.fromkeys(payload.subjects))
    )

    counts = {s: int(payload.counts.get(s) or 0) for s in payload.subjects}
    questions, meta = gather_questions(
        db,
        list(dict.fromkeys(payload.subjects)),
        counts,
        payload.difficulty,
        payload.source,
        payload.bank_share,
    )
    if not questions:
        raise HTTPException(
            status_code=422,
            detail="سؤالِ کافی برای این ترکیب (درس/سطح سختی) در بانک یافت نشد و تولید خودکار هم نتیجه‌ای نداد؛ ترکیب دیگری انتخاب کنید.",
        )

    pdf_bytes = build_exam_pdf(
        school_name=school_name,
        title=title,
        questions=questions,
        duration_minutes=payload.duration_minutes,
        difficulty=payload.difficulty,
        source=payload.source,
    )

    filename = "fahmyar-exam.pdf"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote('آزمون-فهم‌یار.pdf')}",
        "X-Exam-Total-Questions": str(len(questions)),
        "X-Exam-AI-Used": str(meta.get("ai_used", 0)),
        "X-Exam-Bank-Used": str(meta.get("bank_used", 0)),
        "X-Exam-Difficulty": payload.difficulty,
    }
    if meta.get("shortfalls"):
        headers["X-Exam-Shortfalls"] = ",".join(f"{k}:{v}" for k, v in meta["shortfalls"].items())
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
