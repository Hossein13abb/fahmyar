"""مسیرهای ارزیابی: شروع جلسه، ثبت پاسخ، گزارش، مکث/ادامه، مفاهیم و گراف."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.routes_auth import get_current_user
from config import settings
from engine.session_manager import SessionManager, SessionError, question_to_student_dict
from graph.knowledge_graph import load_graph
from models.concept import Concept
from models.database import get_db
from models.question import QUESTION_TYPES, AssessmentSession
from models.user import User
from reports.report_generator import build_report

router = APIRouter(prefix="/api", tags=["assessment"])


# ---------- اسکیماها ----------
class WrongAnswerIn(BaseModel):
    problem_text: str = Field(default="", description="متن صورت مسئله")
    student_answer: str = Field(default="", description="پاسخِ غلطِ دانش‌آموز")
    concept_id: Optional[int] = Field(default=None, description="اگر بدانید خطا متعلق به کدام مفهوم است")


class StartSessionRequest(BaseModel):
    trigger_type: Literal["topic_selection", "wrong_answer"]
    concept_id: Optional[int] = Field(default=None, description="برای مسیر انتخاب موضوع الزامی است")
    wrong_answer: Optional[WrongAnswerIn] = Field(default=None, description="برای مسیر پاسخ غلط الزامی است")


class SubmitAnswerRequest(BaseModel):
    question_id: int
    response_text: str = Field(min_length=0, max_length=20000)


# ---------- سریالایزرها ----------
def _concept_dict(c: Concept, include_propositions: bool = True) -> dict[str, Any]:
    data = {
        "id": c.id,
        "subject": c.subject,
        "grade": c.grade,
        "chapter": c.chapter,
        "topic": c.topic,
        "name": c.name,
        "target_behaviors": c.target_behaviors or [],
        "misconception_count": len(c.common_misconceptions or []),
    }
    if include_propositions:
        data["core_propositions"] = c.core_propositions or []
    return data


def _session_dict(s: AssessmentSession, remaining: int | None = None) -> dict[str, Any]:
    data = s.to_public_dict()
    if remaining is not None:
        data["remaining_seconds"] = remaining
    return data


# ---------- اندپوینت‌ها ----------
@router.post("/assess/start", status_code=201)
async def start_assessment(
    body: StartSessionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="فقط دانش‌آموزان می‌توانند جلسهٔ ارزیابی شروع کنند.")
    manager = SessionManager(db)
    try:
        session, first_question = await manager.start_session(
            student=user,
            trigger_type=body.trigger_type,
            concept_id=body.concept_id,
            wrong_answer=body.wrong_answer.model_dump() if body.wrong_answer else None,
        )
    except SessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "session": _session_dict(session, int(manager.remaining_seconds(session))),
        "hypotheses": session.current_hypotheses or [],
        "next_question": question_to_student_dict(first_question) if first_question else None,
        "message": (
            "جلسه شروع شد. به سؤال‌ها با دلیل پاسخ دهید — هدف فهم است نه نمره."
            if first_question
            else "سؤال مناسبی یافت نشد؛ لطفاً بانک سؤال را با دستور seed پر کنید."
        ),
    }


@router.post("/assess/{session_id}/answer")
async def submit_answer(
    session_id: int,
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    manager = SessionManager(db)
    try:
        session = manager.get_session(session_id, user)
        result = await manager.submit_answer(session, body.question_id, body.response_text)
    except SessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.get("/assess/{session_id}/report")
def get_report(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    manager = SessionManager(db)
    try:
        session = manager.get_session(session_id, user)
    except SessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return build_report(db, session)


@router.post("/assess/{session_id}/pause")
def pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    manager = SessionManager(db)
    try:
        session = manager.get_session(session_id, user)
        session = manager.pause(session)
    except SessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"session": _session_dict(session, int(manager.remaining_seconds(session))), "message": "جلسه مکث شد."}


@router.post("/assess/{session_id}/resume")
async def resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    manager = SessionManager(db)
    try:
        session = manager.get_session(session_id, user)
        session = manager.resume(session)
    except SessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if manager.is_expired(session):
        return {
            "session": _session_dict(session, 0),
            "next_question": None,
            "message": "جلسه از سر گرفته شد ولی زمانش تمام شده است؛ گزارش تولید کنید.",
        }
    next_question = await manager._next_question(session)
    return {
        "session": _session_dict(session, int(manager.remaining_seconds(session))),
        "next_question": question_to_student_dict(next_question) if next_question else None,
        "message": "جلسه ادامه یافت.",
    }


@router.get("/concepts/{subject}/{grade}")
def list_concepts(
    subject: str,
    grade: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    concepts = (
        db.query(Concept)
        .filter(Concept.subject == subject.lower(), Concept.grade == grade)
        .order_by(Concept.chapter, Concept.id)
        .all()
    )
    return {"subject": subject.lower(), "grade": grade, "count": len(concepts),
            "concepts": [_concept_dict(c, include_propositions=(user.role != "student")) for c in concepts]}


@router.get("/concepts")
def list_all_concepts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    concepts = db.query(Concept).order_by(Concept.subject, Concept.grade, Concept.id).all()
    return {"count": len(concepts),
            "concepts": [_concept_dict(c, include_propositions=(user.role != "student")) for c in concepts]}


@router.get("/graph/{concept_id}/prerequisites")
def prerequisites(
    concept_id: int,
    depth: int = 2,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if concept is None:
        raise HTTPException(status_code=404, detail="مفهوم یافت نشد.")
    graph = load_graph(db)
    depth = max(1, min(4, depth))
    chain = graph.get_prerequisites(concept_id, depth=depth)
    return {
        "concept": _concept_dict(concept, include_propositions=(user.role != "student")),
        "depth": depth,
        "prerequisites": chain,
        "cross_subject_count": sum(1 for p in chain if p["cross_subject"]),
    }


@router.get("/question-types")
def question_types():
    return {"question_types": sorted(QUESTION_TYPES)}
