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
from models.question import AssessmentSession, Question
from models.user import User
from reports.report_generator import build_report

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
