"""مدیریت جلسهٔ ارزیابی — سقف ۳۰ دقیقه، مکث/ادامه، دو مسیر شروع.

مسیر A (انتخاب موضوع): کاربر مفهومی را انتخاب می‌کند → گزاره‌های اصلی همان مفهوم بررسی می‌شوند.
مسیر B (پاسخ غلط): کاربر پاسخ غلط می‌دهد → باید تجزیهٔ مسیر حل انجام شود،
    فرضیه‌های ریشهٔ خطا (احتمالاً بین‌درسی) ساخته شود، و از محتمل‌ترین ریشه شروع کنیم.
    ⚠️ هرگز پاسخِ همان سؤالِ اصلی به دانش‌آموز داده نمی‌شود؛ موقعیت‌های متفاوتی
    روی همان مفاهیم پرسیده می‌شود.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from config import settings
from graph.knowledge_graph import load_graph
from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus, Question
from models.user import User
from engine.inference import InferenceEngine
from engine.question_selector import QuestionSelector
from ai.response_analyzer import analyze_response


def _now() -> datetime:
    return datetime.utcnow()


class SessionError(Exception):
    pass


class SessionManager:
    def __init__(self, db: Session):
        self.db = db
        self.engine = InferenceEngine(db)
        self.selector = QuestionSelector(db)

    # ------------------------------------------------------------------
    # شروع جلسه
    # ------------------------------------------------------------------
    async def start_session(
        self,
        student: User,
        trigger_type: str,
        concept_id: Optional[int] = None,
        wrong_answer: Optional[dict] = None,
    ) -> tuple[AssessmentSession, Optional[Question]]:
        if trigger_type == "topic_selection":
            if not concept_id:
                raise SessionError("برای مسیرِ انتخاب موضوع باید concept_id داده شود.")
            concept = self.db.query(Concept).filter(Concept.id == concept_id).first()
            if concept is None:
                raise SessionError("مفهومِ مورد نظر یافت نشد.")
            trigger_detail = f"topic:{concept.subject}/{concept.topic}"
            hypotheses = [
                {
                    "type": "proposition",
                    "proposition": prop,
                    "status": "pending",
                    "reason": "گزارهٔ اصلیِ مفهومِ انتخاب‌شده",
                }
                for prop in concept.core_propositions or []
            ]

        elif trigger_type == "wrong_answer":
            if not wrong_answer:
                raise SessionError("برای مسیرِ پاسخ غلط باید wrong_answer داده شود.")
            problem_text = str(wrong_answer.get("problem_text", "")).strip()
            student_answer = str(wrong_answer.get("student_answer", "")).strip()
            if not problem_text and not student_answer:
                raise SessionError("متن مسئله یا پاسخِ دانش‌آموز لازم است.")
            # مفهومِ هدف: از ورودی صریح، وگرنه تطبیقِ کلیدواژه‌ای با مفاهیم بانک
            concept = None
            wa_concept_id = wrong_answer.get("concept_id")
            if wa_concept_id:
                concept = self.db.query(Concept).filter(Concept.id == wa_concept_id).first()
            if concept is None:
                concept = self._match_concept(problem_text + " " + student_answer)
            if concept is None:
                raise SessionError(
                    "مفهومِ مرتبط با این پاسخ غلط پیدا نشد. لطفاً concept_id را صریح بفرستید."
                )
            concept_id = concept.id
            trigger_detail = f"wrong_answer: {problem_text[:500]} || پاسخ دانش‌آموز: {student_answer[:500]}"

            # تجزیهٔ مسیر حل → فرضیه‌های ریشهٔ خطا (بین‌درسی)
            hypotheses = self._build_root_cause_hypotheses(concept, problem_text, student_answer)
        else:
            raise SessionError(f"trigger_type نامعتبر: {trigger_type}")

        session = AssessmentSession(
            student_id=student.id,
            trigger_type=trigger_type,
            trigger_detail=trigger_detail,
            concept_id=concept_id,
            started_at=_now(),
            time_limit_seconds=settings.SESSION_TIME_LIMIT_SECONDS,
            total_paused_seconds=0.0,
            status="active",
            current_hypotheses=hypotheses,
            evidence_log=[],
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        first_question = await self._next_question(session)
        return session, first_question

    # ------------------------------------------------------------------
    # تجزیهٔ مسیر حل و فرضیه‌سازی (مسیر B)
    # ------------------------------------------------------------------
    def _match_concept(self, text: str) -> Optional[Concept]:
        """تطبیقِ سادهٔ کلیدواژه‌ای بین متن و مفاهیم بانک (آفلاین، بدون AI)."""
        normalized = re.sub(r"\s+", " ", text.lower())
        best: Optional[Concept] = None
        best_score = 0
        keywords = {
            "exponents": ["توان", "exponent", "power", "2^", "3^"],
            "ratio_proportion": ["نسبت", "تناسب", "ratio", "proportion"],
            "vectors": ["بردار", "vector", "مؤلفه"],
            "functions": ["تابع", "f(x)", "function"],
            "linear_equations": ["معادله", "مجهول", "equation", "x ="],
            "coulomb_law": ["کولن", "بار الکتریکی", "coulomb", "q1", "q2", "بار نقطه‌ای"],
            "ohm_law": ["اهم", "ولتاژ", "جریان", "مقاومت", "ohm", "ولت", "آمپر"],
            "newton_second_law": ["نیوتن", "شتاب", "newton", "f=ma", "نیروی خالص"],
            "work_energy": ["کار", "انرژی", "work", "energy", "ژول"],
            "force_decomposition": ["تجزیه", "مؤلفهٔ نیرو", "cos", "sin نیرو"],
            "force": ["نیرو", "force", "جرم", "وزن"],
            "oxidation_number": ["عدد اکسیداسیون", "اکسیداسیون", "oxidation"],
            "redox_reactions": ["اکسایش", "کاهش", "redox", "اکسنده", "کاهنده"],
            "stoichiometry": ["استوکیومتری", "موازنه", "مول", "stoichiometry"],
            "chemical_equilibrium": ["تعادل", "equilibrium", "kc", "لوشاتلیه"],
            "reaction_rate": ["سرعت واکنش", "reaction rate", "کاتالیزور", "انرژی فعال‌سازی"],
        }
        for concept in self.db.query(Concept).all():
            score = 0
            for kw in keywords.get(concept.topic, [concept.name]):
                if kw.lower() in normalized:
                    score += len(kw)
            if concept.name and concept.name in text:
                score += 10
            if score > best_score:
                best_score, best = score, concept
        return best

    def _build_root_cause_hypotheses(
        self, concept: Concept, problem_text: str, student_answer: str
    ) -> list[dict]:
        """فرضیه‌های ریشهٔ خطا را از گراف دانش می‌سازد؛ بین‌درسی‌ها مقدم‌اند."""
        graph = load_graph(self.db)
        candidates = graph.get_root_cause_candidates(concept.id, error_type=None)

        hypotheses: list[dict] = []
        # ابتدا فرضیه‌های کاندیدا (پیش‌نیازها/ابزارها) — از محتمل‌ترین شروع می‌کنیم
        for cand in candidates[:5]:
            cand_concept = self.db.query(Concept).filter(Concept.id == cand["id"]).first()
            if not cand_concept:
                continue
            hypotheses.append(
                {
                    "type": "root_cause",
                    "concept_id": cand_concept.id,
                    "concept_topic": cand_concept.topic,
                    "concept_name": cand_concept.name,
                    "subject": cand_concept.subject,
                    "cross_subject": bool(cand.get("cross_subject")),
                    "proposition": (cand_concept.core_propositions or [""])[0],
                    "status": "pending",
                    "reason": f"پیش‌نیاز/ابزارِ «{concept.name}» است ({'بین‌درسی' if cand.get('cross_subject') else 'هم‌درس'})",
                    "depth": cand.get("depth", 1),
                    "dependency_type": cand.get("dependency_type"),
                }
            )
        # سپس خودِ مفهومِ هدف (اگر مشکل از خودش باشد نه پیش‌نیازها)
        for prop in concept.core_propositions or []:
            hypotheses.append(
                {
                    "type": "target_proposition",
                    "concept_id": concept.id,
                    "concept_topic": concept.topic,
                    "concept_name": concept.name,
                    "cross_subject": False,
                    "proposition": prop,
                    "status": "pending",
                    "reason": f"گزارهٔ اصلیِ «{concept.name}»",
                    "depth": 0,
                    "dependency_type": None,
                }
            )
        return hypotheses

    # ------------------------------------------------------------------
    # زمان
    # ------------------------------------------------------------------
    def remaining_seconds(self, session: AssessmentSession) -> float:
        now = session.paused_at or _now()
        elapsed = (now - session.started_at).total_seconds() - float(session.total_paused_seconds or 0.0)
        return max(0.0, float(session.time_limit_seconds) - elapsed)

    def is_expired(self, session: AssessmentSession) -> bool:
        return self.remaining_seconds(session) <= 0

    def pause(self, session: AssessmentSession) -> AssessmentSession:
        if session.status == "paused":
            return session
        if session.status != "active":
            raise SessionError("فقط جلسهٔ فعال را می‌توان مکث کرد.")
        session.status = "paused"
        session.paused_at = _now()
        self.db.commit()
        return session

    def resume(self, session: AssessmentSession) -> AssessmentSession:
        if session.status != "paused":
            raise SessionError("جلسه مکث‌شده نیست.")
        if session.paused_at:
            session.total_paused_seconds = float(session.total_paused_seconds or 0.0) + (
                _now() - session.paused_at
            ).total_seconds()
        session.paused_at = None
        session.status = "active"
        self.db.commit()
        return session

    # ------------------------------------------------------------------
    # سؤال بعدی / ثبت پاسخ
    # ------------------------------------------------------------------
    async def _next_question(self, session: AssessmentSession) -> Optional[Question]:
        target = self.engine.select_next_investigation_target(session)
        if target is None:
            return None
        concept, proposition = target
        cross = concept.id != session.concept_id  # هدف بین‌درسی/پیش‌نیاز
        return await self.selector.select(session, concept, proposition, cross_subject=cross)

    async def submit_answer(
        self,
        session: AssessmentSession,
        question_id: int,
        response_text: str,
    ) -> dict[str, Any]:
        if session.status == "paused":
            raise SessionError("جلسه مکث شده است؛ ابتدا resume کنید.")
        if session.status != "active":
            raise SessionError("این جلسه دیگر فعال نیست.")

        # سقف زمانی — حتی در میانهٔ پاسخ
        if self.is_expired(session):
            session.status = self._final_status(session)
            self.db.commit()
            return {
                "done": True,
                "reason": "time_limit",
                "session_status": session.status,
                "message": "زمان ۳۰ دقیقه‌ای جلسه به پایان رسید.",
                "remaining_seconds": 0,
            }

        question = self.db.query(Question).filter(Question.id == question_id).first()
        if question is None:
            raise SessionError("سؤال یافت نشد.")

        # ۱) تحلیل پاسخ → شواهد
        evidence = await analyze_response(question, response_text, question.rubric or {})

        # ۲) ثبت شواهد + بازمحاسبهٔ وضعیت گزاره‌ها
        summary = self.engine.update_evidence(
            session, evidence, question_id=question.id, response_text=response_text
        )

        # ۳) به‌روزرسانی فرضیه‌ها بر اساس شواهد تازه
        self._update_hypotheses(session, summary)

        # ۴) ادامه یا توقف؟
        answered = len(session.evidence_log or [])
        remaining = self.remaining_seconds(session)
        next_question = None

        want_more = self.engine.should_continue(session, remaining)
        if want_more:
            next_question = await self._next_question(session)
            if next_question is None:
                want_more = False

        if not want_more:
            session.status = self._final_status(session)

        self.db.commit()
        self.db.refresh(session)

        result: dict[str, Any] = {
            "done": not want_more,
            "session_status": session.status,
            "questions_answered": answered,
            "remaining_seconds": int(self.remaining_seconds(session)),
            "evidence": [e.to_dict() for e in evidence],
            "proposition_statuses": summary["proposition_statuses"],
            "concept_status": summary["concept_status"],
            "conflicts": summary["conflicts"],
            "needs_teacher_review": summary["needs_teacher_review"],
        }
        if next_question is not None:
            result["next_question"] = question_to_student_dict(next_question)
        else:
            result["message"] = (
                "ارزیابی کامل شد." if session.status == "completed"
                else "شواهد کافی به دست نیامد؛ جلسه با وضعیت «فاقد شواهد کافی» بسته شد."
            )
        return result

    def _final_status(self, session: AssessmentSession) -> str:
        has_evidence = any((e.get("evidence") or []) for e in session.evidence_log or [])
        return "completed" if has_evidence else "insufficient_evidence"

    def _update_hypotheses(self, session: AssessmentSession, summary: dict) -> None:
        """فرضیه‌ها را بر اساس شواهد تازه علامت می‌زند (supported / rejected / testing)."""
        statuses = summary.get("proposition_statuses", {})
        hypotheses = list(session.current_hypotheses or [])
        changed = False
        for hyp in hypotheses:
            prop = hyp.get("proposition")
            if not prop:
                continue
            st = statuses.get(prop)
            if st == EvidenceStatus.CONFIRMED.value:
                hyp["status"], changed = "supported", True
            elif st in (EvidenceStatus.NEEDS_REVIEW.value, EvidenceStatus.UNCLEAR.value):
                if hyp.get("status") == "testing":
                    hyp["status"], changed = "likely_root_cause", True
            elif st == EvidenceStatus.LIKELY_UNDERSTOOD.value and hyp.get("status") == "pending":
                hyp["status"], changed = "testing", True
        if changed:
            session.current_hypotheses = hypotheses

    def get_session(self, session_id: int, student: User) -> AssessmentSession:
        session = (
            self.db.query(AssessmentSession)
            .filter(AssessmentSession.id == session_id)
            .first()
        )
        if session is None:
            raise SessionError("جلسه یافت نشد.")
        if student.role == "student" and session.student_id != student.id:
            raise SessionError("دسترسی به این جلسه مجاز نیست.")
        return session


def question_to_student_dict(q: Question) -> dict[str, Any]:
    """خروجیِ سؤال برای دانش‌آموز — بدون rubric و بدون پاسخ (هرگز نشت نکند)."""
    return {
        "id": q.id,
        "concept_id": q.concept_id,
        "text": q.text,
        "question_type": q.question_type,
        "difficulty": q.difficulty,
        "cognitive_type": q.cognitive_type,
        "source": q.source,
        "approval_status": q.approval_status,
    }


def question_to_teacher_dict(q: Question) -> dict[str, Any]:
    """خروجیِ کامل سؤال برای معلم/مدیر (شامل rubric)."""
    data = question_to_student_dict(q)
    data.update(
        {
            "rubric": q.rubric or {},
            "mapped_propositions": q.mapped_propositions or [],
            "mapped_misconceptions": q.mapped_misconceptions or [],
            "ai_model_used": q.ai_model_used,
            "generation_cost_usd": q.generation_cost_usd,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
    )
    return data
