"""مسیرهای ارزیابی: شروع جلسه، ثبت پاسخ، گزارش، مکث/ادامه، مفاهیم و گراف."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from urllib.parse import quote

import json
from datetime import datetime

from api.routes_auth import get_current_user
from ai.cross_check import normalize_suggestions
from ai.question_generator import generate_test_booklet
from config import settings
from engine.session_manager import SessionManager, SessionError, question_to_student_dict
from graph.knowledge_graph import load_graph
from models.concept import Concept
from models.database import get_db
from ai.stage_chain import QUESTIONS_PER_STAGE, TOTAL_QUESTIONS, stage_of_order
from models.question import QUESTION_TYPES, AssessmentSession, Question
from models.user import User
from reports.exam_report import build_exam_report
from reports.fa_map import scrub_english_leaks
from reports.report_generator import build_report
from reports.report_pdf import build_report_pdf
from reports.session_status import COMPREHENSION_LABELS, comprehension_status, is_exam_session

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
    response_text: str = Field(default="", min_length=0, max_length=20000)
    # انتخابِ صریحِ گزینه در تستِ ۴ گزینه‌ای — صفرمبنا.
    # این تنها منبعِ معتبرِ انتخاب است؛ response_text (توضیحِ اختیاری/پاسخِ
    # تشریحی) هرگز برای استخراجِ انتخاب پارس نمی‌شود.
    selected_option_index: Optional[int] = Field(default=None, ge=0, le=3)
    # متنِ گزینهٔ انتخاب‌شده — کلاینت آن را می‌فرستد و بک‌اند با گزینهٔ همان
    # اندیس در rubric تطبیق می‌دهد. اگر ناهمخوان بود، متنِ rubric حاکم است؛
    # به این ترتیب داده‌ای که به مدل و کارنامه می‌رود همیشه از منبعِ معتبر است.
    selected_option_text: Optional[str] = Field(default=None, max_length=500)


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
    """خروجی سؤال برای دانش‌آموز در زنجیرهٔ ۵ مرحله‌ای.

    **محرمانه‌ها به فرانت نمی‌روند:** correct_option_index و expected_logic
    هرگز در این دیکشنری نیستند؛ در submit از ``q.rubric`` خوانده می‌شوند.
    """
    rubric = q.rubric or {}
    data = {
        "id": q.id,
        "order": order,
        "concept_id": q.concept_id,
        # نشتِ واژه‌های انگلیسیِ ترجمه‌پذیر، پیش از رسیدن به دانش‌آموز پاک می‌شود
        # (فرمول‌های داخل `$...$` دست‌نخورده می‌مانند).
        "text": scrub_english_leaks(q.text),
        "type": q.question_type,
        "question_type": q.question_type,
        "difficulty": q.difficulty,
        "cognitive_type": q.cognitive_type,
        "stage_title": rubric.get("stage_title"),
        "exam_type": rubric.get("exam_type") or q.question_type,
        "diagram_svg": rubric.get("diagram_svg"),
    }
    options = rubric.get("options")
    if isinstance(options, list) and options:
        data["options"] = [scrub_english_leaks(str(o)) for o in options]
    forbidden = rubric.get("forbidden_words")
    if isinstance(forbidden, list) and forbidden:
        data["forbidden_words"] = [str(w) for w in forbidden]
    return data


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
    """شروع زنجیرهٔ فهم‌سنجی ۵ مرحله‌ای — هر پنج مرحله یکجا تولید می‌شوند."""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="فقط دانش‌آموزان می‌توانند آزمون جامع شروع کنند.")
    concept = db.query(Concept).filter(Concept.id == body.concept_id).first()
    if concept is None:
        raise HTTPException(status_code=404, detail="مفهوم مورد نظر پیدا نشد.")

    # دفترِ مصرف پیش از تولید باز می‌شود تا فراخوانیِ تولید هم در مجموعِ
    # هزینهٔ همین آزمون حساب شود (پیش‌تر فقط تحلیل شمرده می‌شد).
    from ai.model_abstraction import reset_usage_ledger

    reset_usage_ledger()

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


def _answer_map(questions: list[Question], answers) -> dict[int, str]:
    """پاسخ‌ها را از question_id به order نگاشت می‌کند (منبعِ تحلیل: ترتیبِ مرحله)."""
    id_to_order = {q.id: i + 1 for i, q in enumerate(questions)}
    return {
        id_to_order[a.question_id]: (a.response_text or "").strip()
        for a in answers
        if a.question_id in id_to_order
    }


def _selected_map(questions: list[Question], answers) -> dict[int, int]:
    """انتخابِ صریحِ گزینه، بر اساسِ ترتیبِ مرحله — فقط برای سؤالِ چهارگزینه‌ای."""
    id_to_order = {q.id: i + 1 for i, q in enumerate(questions)}
    by_id = {q.id: q for q in questions}
    chosen: dict[int, int] = {}
    for a in answers:
        order = id_to_order.get(a.question_id)
        if order is None:
            continue
        rubric = by_id[a.question_id].rubric or {}
        options = rubric.get("options") or []
        index = a.selected_option_index
        if index is None or not options:
            continue
        if 0 <= int(index) < len(options):
            chosen[order] = int(index)
    return chosen


def _rows_for(questions: list[Question]) -> list[dict[str, Any]]:
    """ردیف‌های زنجیره — محرمانه‌ها اینجا از rubric خوانده می‌شوند، نه از فرانت."""
    rows = []
    for i, q in enumerate(questions):
        rubric = q.rubric or {}
        stage = int(rubric.get("stage") or stage_of_order(i + 1))
        rows.append(
            {
                "question_id": q.id,
                "order": i + 1,
                "stage": stage,
                "stage_slot": rubric.get("stage_slot") or ((i) % QUESTIONS_PER_STAGE + 1),
                "exam_type": rubric.get("exam_type") or q.question_type,
                "stage_title": rubric.get("stage_title"),
                "text": q.text,
                "options": rubric.get("options") or [],
                "correct_option_index": rubric.get("correct_option_index"),
                "forbidden_words": rubric.get("forbidden_words") or [],
                "expected_logic": rubric.get("expected_logic"),
            }
        )
    return rows


def _option_text(question: Optional[Question], index: Optional[int]) -> Optional[str]:
    """متنِ گزینهٔ انتخاب‌شده از rubricِ همان سؤال — نه از حافظهٔ کلاینت."""
    if question is None or index is None:
        return None
    try:
        options = (question.rubric or {}).get("options") or []
        i = int(index)
        if 0 <= i < len(options):
            return str(options[i])
    except (TypeError, ValueError):
        return None
    return None


def _assessment_model_name(ai_usage: dict[str, Any]) -> str:
    """نامِ مدلی که این آزمون را تولید/ارزیابی کرده — ترجیحاً از usageِ واقعی."""
    models = [str(m).strip() for m in (ai_usage.get("models") or []) if str(m).strip()]
    if models:
        return models[0]
    try:
        from config import settings

        return str(settings.OPENROUTER_ASSESSMENT_MODEL or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _persist_analysis(
    session: AssessmentSession,
    result: dict[str, Any],
    questions: list[Question],
    answers: dict[int, str],
    status: str,
    selected_indices: Optional[dict[int, int]] = None,
) -> None:
    """نتیجهٔ تحلیل را در جلسه می‌نشاند — ساختار سازگار با PDF و گزارش‌های قدیمی."""
    now_iso = datetime.utcnow().isoformat()
    by_order = {i + 1: q for i, q in enumerate(questions)}
    evidence_log = []
    for record in result.get("per_question") or []:
        order = record.get("order")
        question = by_order.get(order)
        evidence_log.append(
            {
                "question_id": record.get("question_id") or (question.id if question else None),
                "order": order,
                "exam_type": (question.question_type if question else None),
                "stage_title": record.get("stage_title"),
                "question_text": (question.text if question else None),
                # گزینه‌ها برای نمایشِ «پاسخ شما» در کارنامه ذخیره می‌شوند؛
                # کلیدِ صحیح عمداً این‌جا نیست.
                "options": ((question.rubric or {}).get("options") if question else None),
                # response فقط متنِ واقعیِ ثبت‌شدهٔ دانش‌آموز است.
                # cognitive_verdict / qualitative_feedback / reasoning هرگز
                # جای آن نمی‌نشیند — این فیلد در کارنامه «پاسخِ تو» نام دارد.
                "response": answers.get(order, ""),
                # انتخابِ گزینه با اندیسِ صفرمبنا ذخیره می‌شود؛ نمایشِ
                # «گزینهٔ n» همیشه از index+1 ساخته می‌شود.
                "selected_option_index": (selected_indices or {}).get(order),
                # متنِ گزینهٔ انتخاب‌شده هم صریحاً ذخیره می‌شود تا کارنامه
                # برای خواندنِ «پاسخ شما» به بازسازیِ آن وابسته نباشد.
                "selected_option_text": _option_text(
                    question, (selected_indices or {}).get(order)
                ),
                "answered_at": now_iso,
                "evidence": [
                    {
                        k: v
                        for k, v in record.items()
                        if k not in ("order", "question_text", "question_id")
                    }
                ],
            }
        )

    meta = {
        "type": "exam_meta",
        "engine": "stage_chain_5",
        "question_ids": [q.id for q in questions],
        "dimensions": result.get("dimension_findings") or [],
        # پیشنهادها در مرزِ API به رشته‌های تمیز نرمال می‌شوند؛ هیچ دیکشنریِ
        # خامی به فرانت/PDF نمی‌رسد.
        "suggestions": normalize_suggestions(result.get("improvement_suggestions")),
        "mastery_status": result.get("mastery_status"),
        "persona_title": result.get("persona_title"),
        "executive_summary": result.get("executive_summary"),
        "cross_check_findings": [
            dict(f) for f in (result.get("cross_check_findings") or []) if isinstance(f, dict)
        ],
        # فاز ۲۱ — دادهٔ ساختاریافتهٔ دو بخشِ تازهٔ کارنامه. نرمال‌سازی در
        # لایهٔ مدل انجام شده؛ این‌جا فقط منتقل می‌شود.
        "root_cause_chains": result.get("root_cause_chains") or [],
        "learning_gaps": result.get("learning_gaps") or [],
        "needs_clarification": bool(result.get("needs_clarification")),
        "clarification_data": result.get("clarification_data"),
        "mastery_note": result.get("mastery_note"),
        "signals": result.get("signals") or {},
        "analyzer": result.get("analyzer"),
        # ردیابیِ مدل/توکن/هزینه — مجموعِ همهٔ فراخوانی‌های همین آزمون
        "ai_usage": result.get("ai_usage") or {},
        # نامِ مدلِ ارزیاب، برای بجِ بالای کارنامه (بندِ ۳)
        "assessment_model": _assessment_model_name(result.get("ai_usage") or {}),
    }
    root_causes = [
        {
            "type": "root_cause",
            "concept_name": rc.get("area") or rc.get("concept_name") or "",
            "status": "likely_root_cause",
            "reasoning": rc.get("reasoning") or "",
            "cross_subject": rc.get("cross_subject") or "",
        }
        for rc in (result.get("root_cause_hypotheses") or [])
        if isinstance(rc, dict)
    ]
    session.evidence_log = evidence_log
    session.current_hypotheses = [meta] + root_causes
    session.status = status


@router.post("/assess/{session_id}/submit-test")
async def submit_test(
    session_id: int,
    body: SubmitTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ثبتِ زنجیرهٔ ۵ مرحله‌ای → تحلیلِ مقایسه‌ای (Cross-Check).

    اگر موتور تشخیص دهد میان دو پاسخِ دانش‌آموز تناقض است، جلسه **completed
    نمی‌شود**؛ در وضعیتِ ``awaiting_clarification`` می‌ماند تا پاسخِ بازپرسی برسد.
    """
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="آزمون یافت نشد.")
    if user.role != "student" or session.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط صاحب آزمون می‌تواند آن را ثبت کند.")

    # دوبارثبت: همان گزارش موجود را برگردان (idempotent)
    if session.status == "completed" and session.evidence_log:
        report = build_exam_report(db, session)
        report["needs_clarification"] = False
        return report

    questions = _load_booklet(db, session)
    if not questions:
        raise HTTPException(status_code=422, detail="دفترچهٔ این جلسه قابل بازیابی نیست.")

    answers = _answer_map(questions, body.answers)
    selected_indices = _selected_map(questions, body.answers)
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None

    from ai.cross_check import analyze_stage_chain

    result = await analyze_stage_chain(
        concept.name if concept else "مفهوم",
        _rows_for(questions),
        answers,
        selected_indices=selected_indices,
    )

    needs_clarification = bool(
        result.get("needs_interrogation") or result.get("needs_clarification")
    )
    _persist_analysis(
        session, result, questions, answers,
        "awaiting_clarification" if needs_clarification else "completed",
        selected_indices=selected_indices,
    )
    db.commit()
    db.refresh(session)

    if needs_clarification:
        clar = result.get("interrogation") or result.get("clarification_data") or {}
        return {
            "session_id": session.id,
            "status": session.status,
            # فاز ۱۱ — قراردادِ «سؤالِ تکمیلی برای رفعِ ابهام»
            "needs_interrogation": True,
            "interrogation": {
                "contradicting_questions": clar.get("contradicting_questions") or [],
                "mirror_prompt": clar.get("mirror_prompt") or "",
                "question": clar.get("question") or "کدام یکی را واقعاً باور داری؟",
            },
            # سازگاریِ عقب‌رو
            "needs_clarification": True,
            "clarification": {
                "contradicting_questions": clar.get("contradicting_questions") or [],
                "mirror_prompt": clar.get("mirror_prompt") or "",
            },
            "mastery_status": result.get("mastery_status"),
            "persona_title": result.get("persona_title"),
            "executive_summary": result.get("executive_summary"),
            "cross_check_findings": [
            dict(f) for f in (result.get("cross_check_findings") or []) if isinstance(f, dict)
        ],
        }

    report = build_exam_report(db, session)
    report["needs_clarification"] = False
    return report


class ClarifyRequest(BaseModel):
    clarification_response: str


@router.post("/assess/{session_id}/clarify")
async def submit_clarification(
    session_id: int,
    body: ClarifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """پاسخِ بازپرسی → بستنِ حلقه و صدورِ گزارشِ نهایی."""
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="آزمون یافت نشد.")
    if user.role != "student" or session.student_id != user.id:
        raise HTTPException(status_code=403, detail="فقط صاحب آزمون می‌تواند پاسخ دهد.")
    if session.status not in ("awaiting_clarification", "completed"):
        raise HTTPException(status_code=422, detail="این آزمون در وضعیتِ بازپرسی نیست.")

    text = (body.clarification_response or "").strip()
    if len(text) < 3:
        raise HTTPException(status_code=422, detail="پاسخِ بازپرسی خیلی کوتاه است؛ کمی توضیح بده.")

    # ستون JSON تغییرِ درجا (in-place) را ردیابی نمی‌کند؛ یک دیکشنریِ نو
    # بساز و کلِ فهرست را از نو تخصیص بده، وگرنه هیچ‌چیز ذخیره نمی‌شود.
    hypotheses = [dict(h) for h in (session.current_hypotheses or []) if isinstance(h, dict)]
    meta = next((h for h in hypotheses if h.get("type") == "exam_meta"), None)
    if meta is None:
        meta = {"type": "exam_meta"}
    else:
        hypotheses = [h for h in hypotheses if h.get("type") != "exam_meta"]

    # تناقض با پاسخِ صریحِ دانش‌آموز حل شد: یافتهٔ CONTRADICTION به SLIP_RESOLVED تبدیل می‌شود.
    findings = []
    for finding in meta.get("cross_check_findings") or []:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        if item.get("type") == "CONTRADICTION":
            item["type"] = "SLIP_RESOLVED"
            item["resolution"] = text[:600]
        findings.append(item)
    meta["cross_check_findings"] = findings
    meta["clarification_response"] = text[:2000]
    meta["needs_clarification"] = False
    meta["clarification_data"] = None
    meta["mastery_note"] = (
        "تناقضِ میان پاسخ‌هایت را خودت روشن کردی؛ این بهترین نشانهٔ یادگیریِ واقعی است."
    )
    session.current_hypotheses = [meta] + hypotheses

    session.status = "completed"
    db.commit()
    db.refresh(session)
    report = build_exam_report(db, session)
    report["needs_clarification"] = False
    report["resolved_clarification"] = True
    return report


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
    if is_exam_session(session):
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


@router.get("/student/history")
def get_student_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """تاریخچهٔ آزمون‌های دانش‌آموزِ لاگین‌شده — کیفی، بدون نمره/رتبه/درصد."""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="این بخش مخصوص دانش‌آموزان است.")
    sessions = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.student_id == user.id,
            AssessmentSession.status.in_(("completed", "insufficient_evidence")),
        )
        .order_by(AssessmentSession.started_at.desc())
        .all()
    )
    concept_ids = {s.concept_id for s in sessions if s.concept_id}
    concepts = (
        {c.id: c for c in db.query(Concept).filter(Concept.id.in_(concept_ids)).all()}
        if concept_ids
        else {}
    )
    items = []
    for s in sessions:
        concept = concepts.get(s.concept_id)
        comprehension = comprehension_status(s)
        items.append(
            {
                "session_id": s.id,
                "concept_id": s.concept_id,
                "concept_name": concept.name if concept else "نامشخص",
                "subject": concept.subject if concept else None,
                "grade": concept.grade if concept else None,
                "exam_date": s.started_at.isoformat() if s.started_at else None,
                "status": s.status,
                "trigger_type": s.trigger_type,
                "is_exam": is_exam_session(s),
                "comprehension": comprehension,
                "comprehension_label": COMPREHENSION_LABELS[comprehension],
                "questions_answered": len(s.evidence_log or []),
            }
        )
    return {"count": len(items), "history": items}


@router.get("/assess/{session_id}/report-pdf")
def download_report_pdf(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """دانلود «کارنامهٔ تحلیلی کیفی» — PDF راست‌چین؛ هیچ نمره/درصد/رتبه‌ای چاپ نمی‌شود."""
    manager = SessionManager(db)
    try:
        session = manager.get_session(session_id, user)
    except SessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    student = db.query(User).filter(User.id == session.student_id).first()
    if is_exam_session(session):
        report = build_exam_report(db, session)
    else:
        report = build_report(db, session)
    pdf_bytes = build_report_pdf(
        student_name=(student.full_name if student else None) or (student.username if student else "دانش‌آموز"),
        student_username=student.username if student else "",
        student_grade=student.grade if student else None,
        student_major=student.major if student else None,
        report=report,
    )
    headers = {
        "Content-Disposition": "attachment; filename=\"fahmyar-qualitative-report.pdf\"; filename*=UTF-8''" + quote("کارنامه-کیفی-فهم‌یار.pdf"),
        "Content-Length": str(len(pdf_bytes)),
        "X-Report-Session-Id": str(session.id),
    }
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers=headers)


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
