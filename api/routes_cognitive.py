"""مسیرهای موتور فهم‌سنجی شناختی (Cognitive Assessment Engine).

    POST /api/assessment/generate  → تولیدِ آزمونِ ۵ سؤالی + نقشهٔ مفهومی
    POST /api/assessment/evaluate  → ارزیابیِ کل‌نگر و کارنامهٔ اشعهٔ ایکس
    POST /api/assessment/clarify   → حکمِ نهایی پس از بازپرسی
    GET  /api/assessment/{id}      → بازیابیِ یک آزمون (برای رفرشِ صفحه)
    GET  /api/assessment/history   → فهرستِ آزمون‌های دانش‌آموز

هر سه مسیر یک جلسهٔ ``AssessmentSession`` می‌سازند/به‌روز می‌کنند تا
تاریخچه و دسترسیِ معلم بدونِ جدولِ جدید کار کند. آزمون‌های قدیمی
(``cognitive_payload`` تهی) از این مسیرها دیده نمی‌شوند.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.routes_auth import get_current_user
from cognition.contract import QUESTION_TITLES, STAGES
from cognition.personas import PERSONAS, persona_for_status, status_label
from cognition.service import CognitionError, clarify_assessment, evaluate_assessment, generate_assessment
from models.concept import Concept
from models.database import get_db
from models.question import AssessmentSession
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assessment", tags=["cognitive-assessment"])


# ---------------------------------------------------------------------------
# اسکیماها
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300, description="مبحث، مثلاً «فشار در مایعات»")
    subject: str = Field(default="", max_length=80, description="درس، مثلاً «فیزیک»")
    grade: str = Field(default="", max_length=40, description="پایه، مثلاً «دهم»")
    concept_id: Optional[int] = Field(default=None, description="اگر از فهرستِ مفاهیم انتخاب شده")
    misconceptions: Optional[list[str]] = Field(
        default=None, description="کج‌فهمی‌های شناخته‌شدهٔ مبحث (اختیاری، به سؤالِ ۴ کمک می‌کند)"
    )


class AnswersPayload(BaseModel):
    """پاسخ‌ها با کلیدِ شمارهٔ سؤال (۱ تا ۵)."""

    answers: dict[int, str] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    session_id: int
    answers: dict[int, str] = Field(default_factory=dict, description="شمارهٔ سؤال → متنِ پاسخ")


class ClarifyRequest(BaseModel):
    session_id: int
    clarification_answer: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# کمکی‌ها
# ---------------------------------------------------------------------------
def _raise(exc: CognitionError) -> None:
    logger.warning("cognitive engine error [%s]: %s", exc.reason, exc.message)
    raise HTTPException(status_code=exc.status_code, detail={"message": exc.message, "reason": exc.reason})


def _load_session(db: Session, session_id: int, user: User) -> AssessmentSession:
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=404, detail={"message": "آزمون یافت نشد.", "reason": "session_not_found"}
        )
    if user.role == "student" and session.student_id != user.id:
        raise HTTPException(
            status_code=403, detail={"message": "دسترسی به این آزمون ندارید.", "reason": "forbidden"}
        )
    if not (session.cognitive_payload or {}).get("kind") == "cognitive":
        raise HTTPException(
            status_code=422,
            detail={"message": "این جلسه آزمونِ شناختی نیست.", "reason": "not_cognitive_session"},
        )
    return session


def _student_view(payload: dict[str, Any]) -> dict[str, Any]:
    """آزمون برای دانش‌آموز — پاسخِ درست و منطقِ انتظاری پنهان می‌شود.

    این پنهان‌سازی در سمتِ سرور انجام می‌شود، نه با اعتماد به فرانت‌اند؛
    وگرنه کلِ آزمون با یک نگاه به Network از بین می‌رفت.
    """
    questions = []
    for q in payload.get("questions") or []:
        item = {
            "id": q.get("id"),
            "type": q.get("type"),
            "title": q.get("title"),
            "question_text": q.get("question_text"),
            "options": q.get("options"),
            "forbidden_words": q.get("forbidden_words") or [],
        }
        questions.append(item)
    return {
        "topic_blueprint": payload.get("topic_blueprint") or {},
        "questions": questions,
    }


def _report_view(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """کارنامهٔ قابلِ نمایش — با متادیتای پرسونا برای UI."""
    if not report:
        return None
    evaluation = report.get("evaluation_report") or {}
    status = evaluation.get("mastery_status", "")
    persona = persona_for_status(status)
    return {
        "needs_clarification": bool(report.get("needs_clarification")),
        "clarification_data": report.get("clarification_data"),
        "evaluation_report": evaluation,
        "status_label": status_label(status),
        "persona": {
            "title": persona["title"],
            "subtitle": persona["subtitle"],
            "emoji": persona["emoji"],
            "tone": persona["tone"],
            "color": persona["color"],
            "meaning": persona["meaning"],
            "advice_focus": persona["advice_focus"],
        },
        "signals": report.get("signals") or {},
        "clarification_answer": report.get("clarification_answer"),
    }


def _session_state(session: AssessmentSession) -> dict[str, Any]:
    payload = session.cognitive_payload or {}
    report = session.cognitive_report or None
    return {
        "session_id": session.id,
        "topic": payload.get("topic"),
        "subject": payload.get("subject"),
        "status": session.status,
        "created_at": session.started_at.isoformat() if session.started_at else None,
        "assessment": _student_view(payload),
        "stages": list(STAGES),
        "report": _report_view(report),
        "stage": (
            "awaiting_clarification"
            if (report or {}).get("needs_clarification")
            else "report_ready"
            if report
            else "answering"
        ),
    }


# ---------------------------------------------------------------------------
# اندپوینت‌ها
# ---------------------------------------------------------------------------
@router.get("/meta")
def assessment_meta():
    """ساختارِ آزمون برای فرانت‌اند: مراحل، عنوان‌ها و پرسوناها."""
    return {
        "stages": list(STAGES),
        "question_titles": QUESTION_TITLES,
        "personas": {
            key: {k: v for k, v in value.items() if k != "advice_focus"}
            for key, value in PERSONAS.items()
        },
    }


@router.post("/generate", status_code=201)
async def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """مرحلهٔ ۱ — تولیدِ آزمونِ زنجیره‌ای. جلسه همین‌جا ساخته می‌شود."""
    if user.role != "student":
        raise HTTPException(
            status_code=403,
            detail={
                "message": "این آزمون مخصوصِ دانش‌آموزان است. برای ساختِ آزمون از آزمون‌ساز استفاده کنید.",
                "reason": "role_forbidden",
            },
        )

    topic = body.topic.strip()
    misconceptions = body.misconceptions
    if body.concept_id and misconceptions is None:
        concept = db.query(Concept).filter(Concept.id == body.concept_id).first()
        if concept is not None:
            topic = topic or concept.name
            misconceptions = list(concept.common_misconceptions or [])

    try:
        assessment, warnings = await generate_assessment(
            topic=topic,
            subject=body.subject,
            grade=body.grade,
            misconceptions=misconceptions,
        )
    except CognitionError as exc:
        _raise(exc)

    session = AssessmentSession(
        student_id=user.id,
        trigger_type="cognitive_assessment",
        trigger_detail=topic[:500],
        concept_id=body.concept_id,
        status="active",
        cognitive_payload={
            "kind": "cognitive",
            "topic": topic,
            "subject": body.subject,
            "grade": body.grade,
            "topic_blueprint": assessment.blueprint.to_dict(),
            "questions": assessment.questions,
            "ai_model_used": assessment.model_name,
            "generation_cost_usd": assessment.cost_usd,
            "warnings": warnings,
            "answers": {},
        },
        cognitive_report=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_id": session.id,
        "topic": topic,
        "assessment": _student_view(session.cognitive_payload or {}),
        "stages": list(STAGES),
        "warnings": warnings,
        "stage": "answering",
    }


@router.get("/history")
def history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """آزمون‌های شناختیِ دانش‌آموزِ لاگین‌شده."""
    if user.role != "student":
        raise HTTPException(status_code=403, detail={"message": "این بخش مخصوص دانش‌آموزان است.", "reason": "role_forbidden"})

    sessions = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.student_id == user.id,
            AssessmentSession.trigger_type == "cognitive_assessment",
        )
        .order_by(AssessmentSession.started_at.desc())
        .limit(50)
        .all()
    )
    items = []
    for s in sessions:
        report = s.cognitive_report or {}
        evaluation = report.get("evaluation_report") or {}
        persona = persona_for_status(evaluation.get("mastery_status", "")) if evaluation else None
        items.append(
            {
                "session_id": s.id,
                "topic": (s.cognitive_payload or {}).get("topic"),
                "status": s.status,
                "created_at": s.started_at.isoformat() if s.started_at else None,
                "persona": persona["title"] if persona else None,
                "emoji": persona["emoji"] if persona else None,
                "mastery_status": evaluation.get("mastery_status"),
                "needs_clarification": bool(report.get("needs_clarification")),
            }
        )
    return {"count": len(items), "history": items}


@router.get("/{session_id}")
def get_assessment(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """بازیابیِ وضعیتِ آزمون — برای رفرشِ صفحه میانِ پاسخ‌دهی."""
    session = _load_session(db, session_id, user)
    state = _session_state(session)
    payload = session.cognitive_payload or {}
    state["saved_answers"] = payload.get("answers") or {}
    return state


@router.post("/evaluate")
async def evaluate(
    body: EvaluateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """مرحلهٔ ۲ — ارزیابیِ کل‌نگر. هیچ سؤالی تک‌به‌تک تصحیح نمی‌شود."""
    session = _load_session(db, body.session_id, user)
    payload = session.cognitive_payload or {}

    answers = {int(k): str(v or "") for k, v in (body.answers or {}).items()}
    questions = payload.get("questions") or []
    if not answers:
        raise HTTPException(
            status_code=422,
            detail={"message": "هیچ پاسخی ثبت نشده است؛ حداقل به یک سؤال پاسخ بده.", "reason": "no_answers"},
        )

    try:
        report = await evaluate_assessment(
            topic=payload.get("topic") or "",
            blueprint=payload.get("topic_blueprint") or {},
            questions=questions,
            answers=answers,
        )
    except CognitionError as exc:
        _raise(exc)

    payload["answers"] = {str(k): v for k, v in answers.items()}
    session.cognitive_payload = payload
    session.cognitive_report = report
    # تا وقتی بازپرسی باز است، جلسه «ثبت‌نشده» می‌ماند تا در تاریخچه نیمه‌کاره دیده نشود.
    session.status = "completed" if not report.get("needs_clarification") else "awaiting_clarification"
    db.commit()
    db.refresh(session)
    return _session_state(session)


@router.post("/clarify")
async def clarify(
    body: ClarifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """مرحلهٔ ۳ — ایستگاهِ بازپرسی: تناقض را با خودِ دانش‌آموز حل می‌کند."""
    session = _load_session(db, body.session_id, user)
    payload = session.cognitive_payload or {}
    report = session.cognitive_report or {}

    if not report.get("needs_clarification"):
        # اگر بازپرسی باز نیست، پاسخِ تازه چیزی را عوض نمی‌کند؛ نباید بی‌صدا نادیده گرفته شود.
        raise HTTPException(
            status_code=422,
            detail={
                "message": "این آزمون در انتظارِ بازپرسی نیست؛ کارنامهٔ آن صادر شده است.",
                "reason": "clarification_not_required",
            },
        )

    answers = {int(k): str(v or "") for k, v in (payload.get("answers") or {}).items()}
    try:
        final = await clarify_assessment(
            topic=payload.get("topic") or "",
            blueprint=payload.get("topic_blueprint") or {},
            questions=payload.get("questions") or [],
            answers=answers,
            clarification_answer=body.clarification_answer,
            previous_report=report,
        )
    except CognitionError as exc:
        _raise(exc)

    session.cognitive_report = final
    session.status = "completed"
    db.commit()
    db.refresh(session)
    return _session_state(session)


@router.delete("/{session_id}")
def delete_assessment(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """حذفِ آزمونِ ناتمام (توسط مالک). برای پاک‌سازیِ آزمون‌های رهاشده."""
    session = _load_session(db, session_id, user)
    if session.student_id != user.id and user.role not in ("admin", "school_staff"):
        raise HTTPException(status_code=403, detail={"message": "اجازهٔ حذف ندارید.", "reason": "forbidden"})
    db.delete(session)
    db.commit()
    return {"ok": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# دسترسیِ معلم
# ---------------------------------------------------------------------------
@router.get("/teacher/student/{student_id}")
def teacher_view(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """کارنامه‌های شناختیِ یک دانش‌آموز برای معلم — همان دادهٔ کارنامه، بدونِ بازپرسی."""
    if user.role not in ("teacher", "admin", "school_staff"):
        raise HTTPException(status_code=403, detail={"message": "دسترسی ندارید.", "reason": "forbidden"})

    student = db.query(User).filter(User.id == student_id, User.role == "student").first()
    if student is None:
        raise HTTPException(status_code=404, detail={"message": "دانش‌آموز یافت نشد.", "reason": "not_found"})

    sessions = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.student_id == student_id,
            AssessmentSession.trigger_type == "cognitive_assessment",
        )
        .order_by(AssessmentSession.started_at.desc())
        .limit(20)
        .all()
    )
    rows = []
    for s in sessions:
        report = s.cognitive_report or {}
        evaluation = report.get("evaluation_report") or {}
        rows.append(
            {
                "session_id": s.id,
                "topic": (s.cognitive_payload or {}).get("topic"),
                "status": s.status,
                "date": s.started_at.isoformat() if s.started_at else None,
                "mastery_status": evaluation.get("mastery_status"),
                "persona_title": evaluation.get("persona_title"),
                "executive_summary": evaluation.get("executive_summary"),
                "findings": evaluation.get("cross_check_findings") or [],
                "advice": evaluation.get("actionable_advice"),
            }
        )
    return {"student": student.to_public_dict(), "count": len(rows), "assessments": rows}
