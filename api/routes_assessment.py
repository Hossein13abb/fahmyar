"""مسیرهای ارزیابی: شروع جلسه، ثبت پاسخ، گزارش، مکث/ادامه، مفاهیم و گراف."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import json
from datetime import datetime

from api.routes_auth import get_current_user
from ai.question_generator import generate_test_booklet
from ai.response_analyzer import analyze_exam
from config import settings
from engine.session_manager import SessionManager, SessionError, question_to_student_dict
from graph.knowledge_graph import load_graph
from models.concept import Concept
from models.database import get_db
from models.question import QUESTION_TYPES, AssessmentSession, Question
from models.user import User
from reports.exam_report import build_exam_report
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


class StartTestRequest(BaseModel):
    concept_id: int = Field(description="شناسهٔ مفهوم آزمون")
    trigger_type: Literal["topic_selection", "wrong_answer"] = "topic_selection"
    wrong_answer: Optional[WrongAnswerIn] = None


class ExamAnswerIn(BaseModel):
    question_id: int
    response_text: str = Field(min_length=0, max_length=20000)


class SubmitTestRequest(BaseModel):
    answers: list[ExamAnswerIn] = Field(min_length=1, max_length=12)


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


def _question_to_exam_dict(q: Question, order: int) -> dict[str, Any]:
    """خروجی سؤال برای دانش‌آموز در آزمون جامع — بدون rubric، همراه با SVG (اگر باشد)."""
    return {
        "id": q.id,
        "order": order,
        "concept_id": q.concept_id,
        "text": q.text,
        "type": q.question_type,
        "question_type": q.question_type,
        "difficulty": q.difficulty,
        "cognitive_type": q.cognitive_type,
        "diagram_svg": (q.rubric or {}).get("diagram_svg"),
    }


def _booklet_ids(session: AssessmentSession) -> list[int]:
    for h in session.current_hypotheses or []:
        if h.get("type") == "exam_booklet":
            return [int(i) for i in (h.get("question_ids") or [])]
    # گوشهٔ سازگاری: جلساتی که از /assess/start با دفترچهٔ متصل ساخته می‌شوند
    raw = (session.trigger_detail or "").strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if payload.get("kind") == "exam_booklet":
            return [int(i) for i in (payload.get("question_ids") or [])]
    return []


def _load_booklet(db: Session, session: AssessmentSession) -> list[Question]:
    ids = _booklet_ids(session)
    if not ids:
        return []
    rows = {q.id: q for q in db.query(Question).filter(Question.id.in_(ids)).all()}
    return [rows[i] for i in ids if i in rows]


def _session_dict(s: AssessmentSession, remaining: int | None = None) -> dict[str, Any]:
    data = s.to_public_dict()
    if remaining is not None:
        data["remaining_seconds"] = remaining
    return data


def _exam_payload(db: Session, session: AssessmentSession, questions: list[Question]) -> dict[str, Any]:
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    return {
        "session": _session_dict(session),
        "session_id": session.id,
        "concept_name": concept.name if concept else "آزمون جامع",
        "questions": [_question_to_exam_dict(q, i + 1) for i, q in enumerate(questions)],
    }


def _load_exam_session(db: Session, session_id: int, user: User) -> tuple[AssessmentSession, list[Question]]:
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="آزمون یافت نشد.")
    if user.role == "student" and session.student_id != user.id:
        raise HTTPException(status_code=403, detail="دسترسی به این آزمون ندارید.")
    if session.status == "completed":
        raise HTTPException(status_code=422, detail="این آزمون قبلاً ثبت و تحلیل شده است.")
    questions = _load_booklet(db, session)
    if not questions:
        raise HTTPException(status_code=422, detail="دفترچهٔ آزمون جامع برای این جلسه پیدا نشد.")
    return session, questions


# ---------- اندپوینت‌ها ----------
@router.get("/assess/session/{session_id}")
def get_assessment_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """اطلاعات جلسهٔ آزمون جامع + آرایهٔ کامل سؤالات (برای ExamRoom)."""
    session, questions = _load_exam_session(db, session_id, user)
    return _exam_payload(db, session, questions)


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

    # دفترچهٔ آزمون جامع را هم به همان جلسه متصل می‌کنیم تا فرانت بتواند به /exam/:id برود.
    # (سازگاری با مسیر قدیمی: next_question همچنان برگردانده می‌شود.)
    questions: list[Question] = []
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    if concept is not None:
        try:
            wrong = body.wrong_answer.model_dump() if body.wrong_answer else None
            questions, model_name, cost = await generate_test_booklet(concept, wrong_answer=wrong)
            for q in questions:
                db.add(q)
            db.flush()
            original_detail = session.trigger_detail or ""
            session.trigger_detail = json.dumps(
                {
                    "kind": "exam_booklet",
                    "question_ids": [q.id for q in questions],
                    "ai_model_used": model_name,
                    "generation_cost_usd": cost,
                    "original_trigger_detail": original_detail[:500],
                },
                ensure_ascii=False,
            )
            db.commit()
            db.refresh(session)
        except Exception as exc:
            # شکست دفترچه نباید شروع جلسهٔ قدیمی را خراب کند
            db.rollback()
            print(f"[start-test-attach] booklet generation failed for session {session.id}: {exc}")
            questions = []

    return {
        "session": _session_dict(session, int(manager.remaining_seconds(session))),
        "session_id": session.id,
        "hypotheses": session.current_hypotheses or [],
        "next_question": question_to_student_dict(first_question) if first_question else None,
        "questions": [_question_to_exam_dict(q, i + 1) for i, q in enumerate(questions)],
        "concept_name": concept.name if concept is not None else None,
        "message": (
            "جلسه شروع شد. به سؤال‌ها با دلیل پاسخ دهید — هدف فهم است نه نمره."
            if first_question
            else "سؤال مناسبی یافت نشد؛ لطفاً بانک سؤال را با دستور seed پر کنید."
        ),
    }


@router.post("/assess/start-test", status_code=201)
async def start_test(
    body: StartTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """شروع آزمون جامع تشخیصی — دفترچهٔ ۹ سؤالی یکجا تولید می‌شود."""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="فقط دانش‌آموزان می‌توانند آزمون جامع شروع کنند.")
    concept = db.query(Concept).filter(Concept.id == body.concept_id).first()
    if concept is None:
        raise HTTPException(status_code=404, detail="مفهوم مورد نظر پیدا نشد.")

    # ابتدا دفترچه تولید می‌شود؛ هنوز هیچ تراکنشِ نوشتنی روی این اتصال باز نیست،
    # تا لاگِ فراخوانیِ AI بتواند از اتصال جداگانه خود را ثبت کند.
    wrong = body.wrong_answer.model_dump() if body.wrong_answer else None
    questions, model_name, cost = await generate_test_booklet(concept, wrong_answer=wrong)

    session = AssessmentSession(
        student_id=user.id,
        trigger_type=body.trigger_type,
        concept_id=concept.id,
        trigger_detail=(
            json.dumps(body.wrong_answer.model_dump(), ensure_ascii=False)
            if body.wrong_answer
            else concept.name
        ),
        status="active",
        time_limit_seconds=settings.SESSION_TIME_LIMIT_SECONDS,
        current_hypotheses=[],
        evidence_log=[],
    )
    db.add(session)
    db.flush()  # لازم برای session.id

    for q in questions:
        db.add(q)
    db.flush()  # لازم برای q.id

    # شناسه‌های دفترچه را در hypotheses ذخیره می‌کنیم (برای بازیابی در رفرش/ثبت)
    session.current_hypotheses = [{"type": "exam_booklet", "question_ids": [q.id for q in questions],
                                   "ai_model_used": model_name, "generation_cost_usd": cost}]
    db.commit()
    db.refresh(session)

    return {
        "session": _session_dict(session),
        "concept_name": concept.name,
        "questions": [_question_to_exam_dict(q, i + 1) for i, q in enumerate(questions)],
        "message": "آزمون جامع آماده است؛ با آرامش و دلیل پاسخ دهید. هیچ بازخورد لحظه‌ای داده نمی‌شود.",
    }


@router.get("/assess/{session_id}/exam")
def get_exam(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """بازیابی دفترچهٔ آزمون برای ادامه/رفرش صفحه — فقط صاحب جلسه."""
    session, questions = _load_exam_session(db, session_id, user)
    return _exam_payload(db, session, questions)


@router.post("/assess/{session_id}/submit-test")
async def submit_test(
    session_id: int,
    body: SubmitTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ثبت نهاییِ آزمون جامع → تحلیل یکپارچه (Holistic) → گزارش تفصیلی."""
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="آزمون یافت نشد.")
    if user.role != "student" or session.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط صاحب آزمون می‌تواند آن را ثبت کند.")

    # دوبارثبت: همان گزارش موجود را برگردان (idempotent)
    if session.status == "completed" and session.evidence_log:
        return build_exam_report(db, session)

    questions = _load_booklet(db, session)
    if not questions:
        raise HTTPException(status_code=422, detail="دفترچهٔ این جلسه قابل بازیابی نیست.")

    answers = {a.question_id: a.response_text.strip() for a in body.answers}
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    items = [
        {
            "question_id": q.id,
            "order": i + 1,
            "exam_type": q.question_type,
            "text": q.text,
            "mapped_propositions": list(q.mapped_propositions or []),
            "response_text": answers.get(q.id, ""),
        }
        for i, q in enumerate(questions)
    ]
    result = await analyze_exam(
        concept.name if concept else "مفهوم",
        list(concept.core_propositions or []) if concept else [],
        items,
    )

    now_iso = datetime.utcnow().isoformat()
    evidence_log = []
    for record in result["per_question"]:
        qid = record["question_id"]
        entry = {
            "question_id": qid,
            "order": record.get("order"),
            "exam_type": record.get("exam_type"),
            "question_text": record.get("question_text"),
            "response": answers.get(qid, ""),
            "answered_at": now_iso,
            "evidence": [{k: v for k, v in record.items()
                          if k not in ("order", "exam_type", "question_text")}],
        }
        evidence_log.append(entry)

    meta = {
        "type": "exam_meta",
        "question_ids": [q.id for q in questions],
        "dimensions": result["dimension_findings"],
        "suggestions": result["improvement_suggestions"],
    }
    root_causes = [
        {"type": "root_cause", "concept_name": rc["area"], "status": "likely_root_cause",
         "reasoning": rc["reasoning"], "cross_subject": rc["cross_subject"]}
        for rc in result["root_cause_hypotheses"]
    ]
    session.evidence_log = evidence_log
    session.current_hypotheses = [meta] + root_causes
    session.status = "completed"
    db.commit()
    db.refresh(session)
    return build_exam_report(db, session)


@router.get("/assess/{session_id}/exam-report")
def get_exam_report(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """گزارش تفصیلی آزمون جامع — مالک جلسه یا معلم/مدیر."""
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="آزمون یافت نشد.")
    if user.role == "student" and session.student_id != user.id:
        raise HTTPException(status_code=403, detail="دسترسی به این گزارش ندارید.")
    if session.status != "completed":
        raise HTTPException(status_code=422, detail="این آزمون هنوز ثبت نهایی نشده است.")
    return build_exam_report(db, session)


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


def _is_exam_session(session: AssessmentSession) -> bool:
    for h in session.current_hypotheses or []:
        if h.get("type") in ("exam_booklet", "exam_meta"):
            return True
    return any(entry.get("exam_type") for entry in (session.evidence_log or []))


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
    if _is_exam_session(session):
        return build_exam_report(db, session)
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
