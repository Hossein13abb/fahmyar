"""ساخت آزمون (نسخهٔ پایه با بخش‌ها) — از بانکِ سؤالاتِ تصویب‌شده.

⚠️ خروجی آزمون هرگز با «فهم» یکسان نیست؛ برچسب «نمرهٔ آزمون — نه سنجش فهم»
همیشه همراه آزمون برگردانده می‌شود.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.routes_auth import get_current_user, require_roles
from models.concept import Concept
from models.database import get_db
from models.question import Question
from models.user import User

router = APIRouter(prefix="/api/exam", tags=["exam"])

DISCLAIMER = "⚠️ نمرهٔ آزمون — نه سنجش فهم: نمرهٔ این آزمون صرفاً عملکرد امتحانی را می‌سنجد و با فهمیدنِ مفهوم یکی نیست."


class ExamSectionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    concept_ids: Optional[list[int]] = None
    subject: Optional[str] = None
    grade: Optional[int] = None
    num_questions: int = Field(default=5, ge=1, le=50)
    difficulty: Optional[str] = Field(default=None, pattern="^(easy|medium|hard)$")


class BuildExamRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    sections: list[ExamSectionRequest] = Field(min_length=1, max_length=10)
    shuffle: bool = True


@router.post("/build")
def build_exam(
    body: BuildExamRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher", "admin", "school_staff")),
):
    exam_sections: list[dict[str, Any]] = []
    warnings: list[str] = []
    total = 0

    for section in body.sections:
        q = db.query(Question).filter(Question.approval_status == "approved")
        # بازهٔ مفهوم‌ها
        concept_ids = list(section.concept_ids or [])
        if section.subject or section.grade is not None:
            cq = db.query(Concept)
            if section.subject:
                cq = cq.filter(Concept.subject == section.subject.lower())
            if section.grade is not None:
                cq = cq.filter(Concept.grade == section.grade)
            concept_ids += [c.id for c in cq.all()]
        if concept_ids:
            q = q.filter(Question.concept_id.in_(set(concept_ids)))
        if section.difficulty:
            q = q.filter(Question.difficulty == section.difficulty)

        pool = q.all()
        random.shuffle(pool)
        chosen = pool[: section.num_questions]
        if len(chosen) < section.num_questions:
            warnings.append(
                f"بخش «{section.title}»: فقط {len(chosen)} سؤالِ تصویب‌شده از {section.num_questions} خواسته‌شده در بانک موجود بود."
            )
        questions = [
            {
                "id": item.id,
                "concept_id": item.concept_id,
                "text": item.text,
                "question_type": item.question_type,
                "difficulty": item.difficulty,
                "cognitive_type": item.cognitive_type,
            }
            for item in chosen
        ]
        exam_sections.append({"title": section.title, "questions": questions, "count": len(questions)})
        total += len(questions)

    return {
        "title": body.title,
        "built_by": user.username,
        "sections": exam_sections,
        "total_questions": total,
        "warnings": warnings,
        "exam_score_note": DISCLAIMER,
        "note": "نمره‌گذاری خودکار این آزمون در این نسخه انجام نمی‌شود؛ نتایج آزمون باید جدا از گزارش فهم تفسیر شوند.",
    }
