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

from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import json
import re

from reports.report_generator import build_report, _aggregate_by_proposition, _final_prop_status
from reports.exam_pdf import DIFFICULTY_LABELS, build_exam_pdf
from ai.model_abstraction import get_router

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
# آزمون‌ساز کنکوری — پیش‌نمایش چهارگزینه‌ای (AI) + PDF نهایی از لیست تأییدشده
# ─────────────────────────────────────────────────────────────────────────────

SUBJECT_SLUGS = {
    "math": {
        "calculus": "حسابان",
        "geometry": "هندسه",
        "discrete": "گسسته",
        "physics": "فیزیک",
        "chemistry": "شیمی",
    },
    "tajrobi": {
        "biology": "زیست‌شناسی",
        "math": "ریاضیات",
        "physics": "فیزیک",
        "chemistry": "شیمی",
    },
}

FIELD_LABELS = {"math": "ریاضی و فیزیک", "tajrobi": "علوم تجربی"}

GRADE_LABELS = {"10": "دهم", "11": "یازدهم", "12": "دوازدهم", "comprehensive": "جامع (دهم تا دوازدهم)"}

QUESTION_TYPE_LABELS = {
    "conceptual": "مفهومی",
    "recall": "حفظی",
    "computational": "محاسباتی",
    "problem": "مسئله",
    "mixed": "ترکیبی",
}

KONKUR_PREVIEW_PROMPT = """شما «مؤلف ارشد سؤالات کنکوری» در سامانهٔ فهم‌یار هستید.

دستورات اکید:
۱. دقیقاً COUNT سؤالِ چهارگزینه‌ایِ سطح‌کنکورِ سراسری (نه سطح مدرسه) در مبحث خواسته‌شده طراحی کن.
۲. هر سؤال دقیقاً ۴ گزینه دارد و فقط یک گزینه درست است. گزینه‌های انحرافی باید «دام‌های» حلال باشند که بدفهمی‌های رایج همان مبحث را هدف بگیرند.
۳. خروجی را فقط و فقط به صورت یک آرایهٔ JSON خالص برگردان؛ هیچ توضیح، مقدمه یا Markdown اضافه ننویس.
۴. ساختار هر عنصر آرایه دقیقاً این است:
   {{"id": 1, "text": "متن سؤال (فارسی)", "options": ["گزینهٔ ۱", "گزینهٔ ۲", "گزینهٔ ۳", "گزینهٔ ۴"], "correct_answer": 2, "source_tag": "تألیفی AI", "explanation": "یک خط استدلال کوتاه برای کلید"}}
   - correct_answer شمارهٔ گزینهٔ درست است (از ۱ تا ۴).
   - source_tag یکی از این‌ها باشد: «کنکور ۱۴۰۱» تا «کنکور ۱۴۰۴»، «قلم‌چی»، «گاج»؛ اگر سؤالِ تألیفیِ خودت است دقیقاً «تألیفی AI» بگذار.
۵. سطح سختی باید «{difficulty_label}» باشد و سبک سؤال‌ها متناسب با «{question_type_label}».
۶. اگر «دستورالعمل سفارشی» کاربر چیزی خواست، آن را رعایت کن ولی ساختار JSON و چهارگزینه‌بودن حفظ شود.

<<<FIELD>>>{field_label}<<<END>>>
<<<SUBJECT>>>{subject_slug}<<<END>>>
<<<SUBJECT_LABEL>>>{subject_label}<<<END>>>
<<<GRADE>>>{grade_label}<<<END>>>
<<<TOPIC>>>{topic}<<<END>>>
<<<QUESTION_TYPE>>>{question_type_label}<<<END>>>
<<<DIFFICULTY>>>{difficulty_label}<<<END>>>
<<<COUNT>>>{count}<<<END>>>
<<<CUSTOM>>>{custom_prompt}<<<END>>>
"""


class GenerateExamPreviewRequest(BaseModel):
    field: str = Field(pattern="^(math|tajrobi)$")
    grade: str = Field(pattern="^(10|11|12|comprehensive)$")
    subject: str = Field(min_length=1, max_length=30)
    topic: str = Field(min_length=1, max_length=140)
    question_type: str = Field(pattern="^(conceptual|recall|computational|problem|mixed)$")
    difficulty: str = Field(pattern="^(easy|medium|hard|challenging)$")
    count: int = Field(default=10, ge=1, le=20)
    custom_prompt: str = Field(default="", max_length=600)


def _extract_json_array(raw: str):
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    match = re.search(r"\[.*\]", text, flags=re.S)
    if match:
        text = match.group(0)
    return json.loads(text)


_LETTER_TO_INDEX = {"A": 1, "B": 2, "C": 3, "D": 4, "الف": 1, "ب": 2, "ج": 3, "د": 4}


def _validate_preview_questions(data) -> list[dict]:
    if not isinstance(data, list):
        raise ValueError("خروجی مدل آرایه نیست")
    clean: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        options = [str(o).strip() for o in (item.get("options") or [])][:4]
        if not text or len(options) != 4 or any(not o for o in options):
            continue
        ca = item.get("correct_answer")
        try:
            ca = int(str(ca).strip())
        except (TypeError, ValueError):
            ca = _LETTER_TO_INDEX.get(str(ca).strip().upper(), 0)
        if not 1 <= ca <= 4:
            continue
        tag = str(item.get("source_tag") or "").strip()[:60] or "تألیفی AI"
        explanation = str(item.get("explanation") or "").strip()
        clean.append(
            {
                "id": len(clean) + 1,
                "text": text,
                "options": options,
                "correct_answer": ca,
                "source_tag": tag,
                "explanation": explanation,
            }
        )
    return clean


@router.post("/generate-exam-preview")
async def generate_exam_preview(
    payload: GenerateExamPreviewRequest,
    user: User = Depends(require_roles("teacher", "admin")),
):
    subjects = SUBJECT_SLUGS[payload.field]
    if payload.subject not in subjects:
        raise HTTPException(status_code=422, detail="درس انتخابی برای این رشته معتبر نیست.")
    subject_label = subjects[payload.subject]
    grade_fa = GRADE_LABELS[payload.grade]
    difficulty_label = DIFFICULTY_LABELS.get(payload.difficulty, payload.difficulty)
    qtype_label = QUESTION_TYPE_LABELS[payload.question_type]

    prompt = KONKUR_PREVIEW_PROMPT.format(
        count=payload.count,
        field_label=FIELD_LABELS[payload.field],
        subject_slug=payload.subject,
        subject_label=subject_label,
        grade_label=grade_fa,
        topic=payload.topic.strip(),
        question_type_label=qtype_label,
        difficulty_label=difficulty_label,
        custom_prompt=(payload.custom_prompt or "").strip() or "—",
    )

    try:
        response = await get_router().generate(prompt, "generate_konkur_preview", temperature=0.8)
    except Exception as exc:  # خطای مدل/شبکه — هیچ سؤال جعلی‌ای ساخته نمی‌شود
        raise HTTPException(status_code=502, detail=f"ارتباط با مدل هوش مصنوعی برقرار نشد: {exc.__class__.__name__}")

    try:
        raw_questions = _extract_json_array(response.text or "")
        questions = _validate_preview_questions(raw_questions)
    except (json.JSONDecodeError, ValueError, re.error):
        questions = []

    if not questions:
        raise HTTPException(
            status_code=502,
            detail="مدل خروجی ساختارمند و معتبری نداد؛ لطفاً دوباره تلاش کنید یا دستورالعمل سفارشی را خلاصه‌تر بنویسید.",
        )

    return {
        "questions": questions,
        "meta": {
            "field": payload.field,
            "field_label": FIELD_LABELS[payload.field],
            "grade": payload.grade,
            "grade_label": grade_fa,
            "subject": payload.subject,
            "subject_label": subject_label,
            "topic": payload.topic.strip(),
            "question_type": payload.question_type,
            "question_type_label": qtype_label,
            "difficulty": payload.difficulty,
            "difficulty_label": difficulty_label,
            "count_requested": payload.count,
            "count_returned": len(questions),
        },
    }


class KonkurQuestion(BaseModel):
    """یک سؤال چهارگزینه‌ای تأییدشده توسط کادر مدرسه — منبع آن (source_tag) در PDF چاپ نمی‌شود."""

    id: Optional[int] = None
    text: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_answer: int = Field(ge=1, le=4)
    source_tag: str = Field(default="", max_length=60)
    explanation: str = Field(default="", max_length=1200)


class GenerateExamPdfRequest(BaseModel):
    title: str = Field(default="", max_length=140)
    school_name: str = Field(default="مدرسهٔ نمونه", max_length=140)
    grade: str = Field(default="comprehensive", pattern="^(10|11|12|comprehensive)$")
    major: str = Field(default="", max_length=80)
    subject_label: str = Field(default="", max_length=60)
    topic: str = Field(default="", max_length=140)
    duration_minutes: int = Field(default=90, ge=10, le=240)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|challenging)$")
    questions: list[KonkurQuestion] = Field(min_length=1, max_length=120)


@router.post("/generate-exam-pdf")
def generate_exam_pdf(
    payload: GenerateExamPdfRequest,
    user: User = Depends(require_roles("teacher", "admin")),
):
    """PDF نهایی کنکوری از لیستِ تأییدشدهٔ سؤال‌ها — تگِ منبع مطلقاً چاپ نمی‌شود."""
    school_name = (payload.school_name or "").strip() or "مدرسهٔ نمونه"
    title = (payload.title or "").strip() or "آزمون کنکوری — فهم‌یار"
    major = (payload.major or "").strip()
    subject_label = (payload.subject_label or "").strip() or "کنکور"
    topic = (payload.topic or "").strip()

    questions = []
    for i, q in enumerate(payload.questions, start=1):
        questions.append(
            {
                "order": i,
                "text": q.text.strip(),
                "options": [str(o).strip() for o in q.options],
                "correct_answer": int(q.correct_answer),
                "explanation": (q.explanation or "").strip(),
            }
        )

    pdf_bytes = build_exam_pdf(
        school_name=school_name,
        title=title,
        questions=questions,
        duration_minutes=payload.duration_minutes,
        difficulty=payload.difficulty,
        grade=payload.grade,
        major=major,
        subject_label=subject_label,
        topic=topic,
    )

    filename = "fahmyar-konkur-exam.pdf"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote('آزمون-کنکوری-فهم‌یار.pdf')}",
        "Content-Length": str(len(pdf_bytes)),
        "X-Exam-Total-Questions": str(len(questions)),
        "X-Exam-Difficulty": payload.difficulty,
    }
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers=headers)

