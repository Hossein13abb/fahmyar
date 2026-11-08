"""انتخاب سؤال بعدی — اول بانک تأییدشده، سپس تولیدِ درست‌به‌وقت (JIT).

استراتژی:
  ۱) سؤال‌های تصویب‌شدهٔ بانک که به همان گزاره منسوب‌اند (و هنوز پرسیده نشده‌اند)
  ۲) هر سؤال تصویب‌شدهٔ همان مفهوم
  ۳) تولید سؤال JIT با هوش مصنوعی (approval_status='pending')
  ۴) در صورت شکست تولید، آخرین راه: هر سؤال تصویب‌شدهٔ بانک
"""
from __future__ import annotations

import random
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.concept import Concept
from models.question import AssessmentSession, Question
from ai.question_generator import generate_diagnostic_question, QuestionGenerationError


class QuestionSelector:
    def __init__(self, db: Session):
        self.db = db

    def _used_question_ids(self, session: AssessmentSession) -> set[int]:
        used = set()
        for entry in session.evidence_log or []:
            qid = entry.get("question_id")
            if qid is not None:
                used.add(qid)
        return used

    def _bank_questions(self, concept_id: int, used: set[int]) -> list[Question]:
        return (
            self.db.query(Question)
            .filter(
                Question.concept_id == concept_id,
                Question.approval_status == "approved",
                ~Question.id.in_(used) if used else True,
            )
            .all()
        )

    async def select(
        self,
        session: AssessmentSession,
        concept: Concept,
        target_proposition: str,
        cross_subject: bool = False,
    ) -> Optional[Question]:
        used = self._used_question_ids(session)

        # ۱) بانک: سؤالی که مستقیماً همین گزاره را هدف گرفته
        bank = self._bank_questions(concept.id, used)
        matched = [q for q in bank if target_proposition in (q.mapped_propositions or [])]
        if matched:
            return random.choice(matched)
        # ۲) بانک: هر سؤال تصویب‌شدهٔ همین مفهوم
        if bank:
            return random.choice(bank)

        # رفتار هدف را بر اساس تعداد سؤالات پرسیده‌شده بچرخان
        behaviors = concept.target_behaviors or ["explain"]
        behavior = behaviors[len(used) % len(behaviors)]
        target_misconception = None
        for m in concept.common_misconceptions or []:
            target_misconception = m.get("misconception")
            break

        previous_responses = [e.get("response", "") for e in (session.evidence_log or [])]

        # ۳) تولید JIT
        try:
            question = await generate_diagnostic_question(
                concept=concept,
                target_proposition=target_proposition,
                target_misconception=target_misconception,
                behavior=behavior,
                previous_responses=previous_responses,
                cross_subject=cross_subject,
            )
            self.db.add(question)
            self.db.flush()  # id بگیرد ولی commit با جلسه انجام می‌شود
            return question
        except QuestionGenerationError:
            pass
        except Exception:
            pass

        # ۴) آخرین راه: هر سؤال تصویب‌شده (حتی از مفاهیم دیگر) — بهتر از توقف جلسه
        fallback = (
            self.db.query(Question)
            .filter(Question.approval_status == "approved", ~Question.id.in_(used) if used else True)
            .first()
        )
        return fallback
