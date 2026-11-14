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

from reports.report_generator import build_report
from reports.pdf_shared import DIFFICULTY_LABELS
from reports.pdf_browser import BrowserRenderError, build_exam_pdf_browser
from reports.session_status import (
    COMPREHENSION_LABELS,
    comprehension_status,
    needs_teacher_review,
)
from ai.exam_generator import (
    DIFFICULTY_MAP_FA,
    FALLBACK_FREE_MODELS,
    build_exam_preview_prompt,
    generate_exam_questions,
    persianize_json_values,
    persianize_svg_texts,
    to_persian_numbers,
)
from ai.json_sanitize import extract_json_array, safe_parse_json
from ai.model_abstraction import get_router

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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

@router.get("/student-results")
def student_results(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
            comprehension = comprehension_status(latest)
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
                    "needs_teacher_review": needs_teacher_review(latest),
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

_EXPERIMENTAL_SUBJECTS = {
    "biology": "زیست‌شناسی",
    "math": "ریاضیات",
    "physics": "فیزیک",
    "chemistry": "شیمی",
}

SUBJECT_SLUGS = {
    "math": {
        "10": {"math": "ریاضی", "geometry": "هندسه", "physics": "فیزیک", "chemistry": "شیمی"},
        "11": {"calculus": "حسابان", "geometry": "هندسه", "statistics": "آمار و احتمال", "physics": "فیزیک", "chemistry": "شیمی"},
        "12": {"calculus": "حسابان", "geometry": "هندسه", "discrete": "گسسته", "physics": "فیزیک", "chemistry": "شیمی"},
        "comprehensive": {
            "math": "ریاضی",
            "calculus": "حسابان",
            "geometry": "هندسه",
            "statistics": "آمار و احتمال",
            "discrete": "گسسته",
            "physics": "فیزیک",
            "chemistry": "شیمی",
        },
    },
    "tajrobi": {grade: dict(_EXPERIMENTAL_SUBJECTS) for grade in ("10", "11", "12", "comprehensive")},
}

FIELD_LABELS = {"math": "ریاضی و فیزیک", "tajrobi": "علوم تجربی"}

GRADE_LABELS = {"10": "دهم", "11": "یازدهم", "12": "دوازدهم", "comprehensive": "جامع (دهم تا دوازدهم)"}

QUESTION_TYPE_LABELS = {
    "conceptual": "مفهومی",
    "recall": "حفظی",
    "computational": "محاسباتی",
    "problem": "مسئله",
    "mixed": "نامشخص / ترکیبی",
}

KONKUR_PREVIEW_PROMPT = """شما «مؤلف ارشد سؤالات کنکوری» در سامانهٔ فهم‌یار هستید.

دستورات اکید:
۱. دقیقاً COUNT سؤالِ چهارگزینه‌ایِ سطح‌کنکورِ سراسری (نه سطح مدرسه) طراحی کن.
۲. سؤالات را به‌طور متوازن بین این درس‌ها تقسیم کن: {subjects_labels}.
   - اگر COUNT بر تعداد درس‌ها بخش‌پذیر نبود، سؤال‌های باقی‌مانده را به ترتیب به درس‌های اول بده.
   - هر سؤال باید «subject» داشته باشد و دقیقاً نام فارسیِ همان درسی باشد که سؤال از آن است.
   - اگر «مبحث» مشخص شده باشد، سؤالاتِ هر درس را حول همان مبحث/موضوع بچین؛ اگر مبحث خالی باشد، از پُرتکرارترین و مهم‌ترین مطالبِ هر درس طرح کن و ترکیبی پوشش بده.
۳. هر سؤال دقیقاً ۴ گزینه دارد و فقط یک گزینه درست است. گزینه‌های انحرافی باید «دام‌های» حلال باشند که بدفهمی‌های رایجِ همان مبحثِ همان درس را هدف بگیرند.
۴. خروجی را فقط و فقط به صورت یک آرایهٔ JSON خالص برگردان؛ هیچ توضیح، مقدمه یا Markdown اضافه ننویس.
۵. ساختار هر عنصر آرایه دقیقاً این است:
   {{"id": 1, "text": "متن سؤال (فارسی)", "options": ["گزینهٔ ۱", "گزینهٔ ۲", "گزینهٔ ۳", "گزینهٔ ۴"], "correct_answer": 2, "subject": "فیزیک", "source_tag": "تألیفی AI", "explanation": "یک خط استدلال کوتاه برای کلید"}}
   - correct_answer شمارهٔ گزینهٔ درست است (از ۱ تا ۴).
   - subject دقیقاً یکی از این نام‌ها باشد: {subjects_labels}.
   - source_tag یکی از این‌ها باشد: «کنکور ۱۴۰۱» تا «کنکور ۱۴۰۴»، «قلم‌چی»، «گاج»؛ اگر سؤالِ تألیفیِ خودت است دقیقاً «تألیفی AI» بگذار.
۶. سطح سختی باید «{difficulty_label}» باشد و سبک سؤال‌ها متناسب با «{question_type_label}». اگر سبک «نامشخص / ترکیبی» بود، سبک‌ها را عمداً ترکیبی از مفهومی/محاسباتی/مسئله‌ای/نموداری بچین.
۷. اگر «دستورالعمل سفارشی» کاربر چیزی خواست، آن را رعایت کن ولی ساختار JSON و چهارگزینه‌بودن حفظ شود.

<<<FIELD>>>{field_label}<<<END>>>
<<<SUBJECTS>>>{subjects_slugs}<<<END>>>
<<<SUBJECT_LABELS>>>{subjects_labels}<<<END>>>
<<<SUBJECT_CONFIGS>>>{subject_configs_json}<<<END>>>
<<<AI_PERCENTAGE>>>{ai_percentage}<<<END>>>
<<<GRADE>>>{grade_label}<<<END>>>
<<<TOPIC>>>{topic}<<<END>>>
<<<QUESTION_TYPE>>>{question_type_label}<<<END>>>
<<<DIFFICULTY>>>{difficulty_label}<<<END>>>
<<<COUNT>>>{count}<<<END>>>
<<<CUSTOM>>>{custom_prompt}<<<END>>>
"""


class SubjectConfigItem(BaseModel):
    subject: str = Field(min_length=1, max_length=40)
    count: int = Field(default=2, ge=1, le=20)
    difficulty: str = Field(default="متوسط", max_length=30)
    subTopics: list[str] = Field(default_factory=list, max_length=60)
    topics: list[str] = Field(default_factory=list, max_length=60)


class GenerateExamPreviewRequest(BaseModel):
    field: str = Field(pattern="^(math|tajrobi)$")
    grade: str = Field(pattern="^(10|11|12|comprehensive)$")
    subjects: list[str] = Field(default_factory=list, max_length=10)
    subject_configs: Optional[list[SubjectConfigItem]] = Field(default=None)
    subTopics: list[str] = Field(default_factory=list, max_length=120)
    ai_ratio: Optional[int] = Field(default=None, ge=0, le=100)
    ai_percentage: int = Field(default=100, ge=0, le=100)
    topic: Optional[str] = Field(default=None, max_length=300)
    question_type: str = Field(default="mixed", pattern="^(conceptual|recall|computational|problem|mixed)$")
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|challenging|konkuri|آسان|متوسط|سخت|کنکوری)$")
    count: int = Field(default=10, ge=1, le=60)
    custom_prompt: str = Field(default="", max_length=600)


def _extract_json_array(raw: str):
    return extract_json_array(raw or "")


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
        tag = to_persian_numbers(str(item.get("source_tag") or "").strip()[:60] or "تألیفی AI")
        explanation = to_persian_numbers(str(item.get("explanation") or "").strip())
        subject_label = to_persian_numbers(str(item.get("subject") or "").strip()[:40])
        diff_label = to_persian_numbers(str(item.get("difficulty") or "").strip()[:30])
        raw_svg = item.get("diagram_svg")
        diagram_svg = None
        if isinstance(raw_svg, str) and "<svg" in raw_svg.lower() and "</svg>" in raw_svg.lower():
            diagram_svg = persianize_svg_texts(raw_svg.strip())
        clean.append(
            {
                "id": len(clean) + 1,
                "text": to_persian_numbers(text),
                "options": [to_persian_numbers(o) for o in options],
                "correct_answer": ca,
                "source_tag": tag,
                "explanation": explanation,
                "subject": subject_label,
                "difficulty": diff_label,
                "diagram_svg": diagram_svg,
            }
        )
    return clean


@router.post("/generate-exam-preview")
async def generate_exam_preview(
    payload: GenerateExamPreviewRequest,
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
):
    slug_map = SUBJECT_SLUGS[payload.field][payload.grade]
    raw_subjects = list(payload.subjects or [])
    if payload.subject_configs:
        for cfg in payload.subject_configs:
            if cfg.subject not in raw_subjects:
                raw_subjects.append(cfg.subject)
    # حذف تکراری‌ها با حفظ ترتیب
    requested = list(dict.fromkeys(raw_subjects))
    if not requested:
        raise HTTPException(status_code=422, detail="حداقل یک درس را انتخاب کنید.")
    invalid = [s_ for s_ in requested if s_ not in slug_map]
    if invalid:
        raise HTTPException(status_code=422, detail="درس انتخابی برای این رشته و پایه معتبر نیست.")

    effective_ai_ratio = payload.ai_ratio if payload.ai_ratio is not None else payload.ai_percentage
    configs_normalized: list[dict] = []
    aggregated_subtopics: list[str] = [str(t).strip() for t in (payload.subTopics or []) if str(t).strip()]
    if payload.subject_configs:
        for cfg in payload.subject_configs:
            if cfg.subject not in slug_map:
                raise HTTPException(status_code=422, detail="درس انتخابی برای این رشته و پایه معتبر نیست.")
            raw_subs = list(cfg.subTopics or []) or list(cfg.topics or [])
            clean_topics = [str(t).strip() for t in raw_subs if str(t).strip()]
            for st in clean_topics:
                if st not in aggregated_subtopics:
                    aggregated_subtopics.append(st)
            diff_fa = DIFFICULTY_MAP_FA.get(str(cfg.difficulty or "").strip(), "متوسط")
            configs_normalized.append(
                {
                    "subject": cfg.subject,
                    "label": slug_map[cfg.subject],
                    "count": int(cfg.count),
                    "difficulty": diff_fa,
                    "subTopics": clean_topics,
                    "topics": clean_topics,
                }
            )
    effective_count = sum(c["count"] for c in configs_normalized) if configs_normalized else payload.count

    subject_labels = [slug_map[s_] for s_ in requested]
    subjects_labels = "، ".join(subject_labels)
    subject_label = subjects_labels  # برای سازگاری با خروجی‌های قبلی
    subjects_slugs = "، ".join(requested)
    topic_text = (payload.topic or "").strip()
    if not topic_text and configs_normalized:
        per_subj_topics = [
            f"{c['label']} ({c['difficulty']}): {'، '.join(c['subTopics'])}"
            for c in configs_normalized
            if c.get("subTopics")
        ]
        if per_subj_topics:
            topic_text = " | ".join(per_subj_topics)[:300]
    grade_fa = GRADE_LABELS[payload.grade]
    difficulty_label = DIFFICULTY_MAP_FA.get(payload.difficulty, DIFFICULTY_LABELS.get(payload.difficulty, payload.difficulty))
    qtype_label = QUESTION_TYPE_LABELS[payload.question_type]

    prompt = build_exam_preview_prompt(
        count=effective_count,
        field_label=FIELD_LABELS[payload.field],
        subjects_slugs=subjects_slugs,
        subjects_labels=subjects_labels,
        subject_configs=configs_normalized,
        sub_topics=aggregated_subtopics,
        ai_ratio=effective_ai_ratio,
        grade_label=grade_fa,
        topic=topic_text or "—",
        question_type_label=qtype_label,
        difficulty_label=difficulty_label,
        custom_prompt=(payload.custom_prompt or "").strip() or "—",
    )

    questions, provider_exc = await generate_exam_questions(
        prompt,
        validator_fn=_validate_preview_questions,
        temperature=0.8,
    )
    if provider_exc is not None and not questions:
        raise HTTPException(
            status_code=502,
            detail=f"ارتباط با مدل هوش مصنوعی برقرار نشد: {provider_exc.__class__.__name__}",
        )

    if not questions:
        raise HTTPException(
            status_code=400,
            detail="مدل هوش مصنوعی پاسخ نامعتبری داد. لطفاً دوباره تلاش کنید",
        )

    return {
        "questions": persianize_json_values(questions),
        "meta": {
            "field": payload.field,
            "field_label": to_persian_numbers(FIELD_LABELS[payload.field]),
            "grade": payload.grade,
            "grade_label": to_persian_numbers(grade_fa),
            "subjects": requested,
            "subjects_labels": [to_persian_numbers(lbl) for lbl in subject_labels],
            "subject_label": to_persian_numbers(subject_label),
            "topic": to_persian_numbers(topic_text),
            "subTopics": [to_persian_numbers(st) for st in aggregated_subtopics],
            "question_type": payload.question_type,
            "question_type_label": to_persian_numbers(qtype_label),
            "difficulty": payload.difficulty,
            "difficulty_label": to_persian_numbers(difficulty_label),
            "subject_configs": persianize_json_values(configs_normalized),
            "ai_ratio": effective_ai_ratio,
            "ai_percentage": effective_ai_ratio,
            "count_requested": effective_count,
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
    difficulty: Optional[str] = Field(default="", max_length=40)
    subject: Optional[str] = Field(default="", max_length=60)
    diagram_svg: Optional[str] = Field(default=None, max_length=20000)


class GenerateExamPdfRequest(BaseModel):
    title: str = Field(default="", max_length=140)
    school_name: str = Field(default="مدرسهٔ نمونه", max_length=140)
    grade: str = Field(default="comprehensive", pattern="^(10|11|12|comprehensive)$")
    major: str = Field(default="", max_length=80)
    subject_label: str = Field(default="", max_length=120)
    topic: str = Field(default="", max_length=140)
    duration_minutes: int = Field(default=90, ge=10, le=240)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|challenging|konkuri|آسان|متوسط|سخت|کنکوری)$")
    questions: list[KonkurQuestion] = Field(min_length=1, max_length=120)


@router.post("/generate-exam-pdf")
def generate_exam_pdf(
    payload: GenerateExamPdfRequest,
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
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
                # فرمول‌های LaTeX دست‌نخورده می‌مانند تا در PDF به تصویر واقعی رندر شوند
                "text": (q.text or "").strip(),
                "options": [str(o).strip() for o in q.options],
                "correct_answer": int(q.correct_answer),
                "explanation": (q.explanation or "").strip(),
                "difficulty": (q.difficulty or "").strip(),
                "subject": (q.subject or "").strip(),
                "diagram_svg": q.diagram_svg,
            }
        )

    # رندر با مرورگر: همان کامپوننت‌های پیش‌نمایش، سپس بسته‌بندیِ تصویرها به PDF.
    # امضای فراخوانی نسبت به موتور قدیم تفاوتی ندارد.
    try:
        pdf_bytes = build_exam_pdf_browser(
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
    except BrowserRenderError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ساخت PDF با موتور مرورگری ممکن نشد: {exc}",
        ) from exc

    filename = "fahmyar-konkur-exam.pdf"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote('آزمون-کنکوری-فهم‌یار.pdf')}",
        "Content-Length": str(len(pdf_bytes)),
        "X-Exam-Total-Questions": str(len(questions)),
        "X-Exam-Difficulty": {"آسان": "easy", "متوسط": "medium", "سخت": "hard", "کنکوری": "challenging"}.get(payload.difficulty, payload.difficulty.encode("ascii", "ignore").decode("ascii") or "medium"),
    }
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers=headers)

