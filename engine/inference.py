"""موتور استنتاج کیفی فهم‌یار — منطق ۵ وضعیته، بدون عدد و رتبه.

قواعد ترکیب شواهد (به ازای هر گزاره):
  ۱) ≥۲ شواهدِ تأییدکنندهٔ مستقل (سؤال‌های متفاوت) + بدون تناقض قوی → CONFIRMED
  ۲) ۱ تأییدکنندهٔ قوی یا ۲ تأییدکنندهٔ ضعیف/وابسته → LIKELY_UNDERSTOOD
  ۳) شواهد متناقض (هم تأییدکننده هم ردکننده) → UNCLEAR
  ۴) ≥۱ شواهدِ ردکنندهٔ قوی → NEEDS_REVIEW
  ۵) بدون هیچ شواهدی → INSUFFICIENT_EVIDENCE

اصل حیاتی: گزاره‌های اصلی (core propositions) بر موفقیتِ محاسباتی مقدم‌اند.
موفقیت صرفاً محاسباتی (computational_success) هیچ‌گاه گزارهٔ اصلیِ دارای
شواهدِ ردکننده را به CONFIRMED ارتقا نمی‌دهد.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from config import settings
from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus

CONFIRMING = {EvidenceStatus.CONFIRMED.value, EvidenceStatus.LIKELY_UNDERSTOOD.value}


def _now() -> datetime:
    return datetime.utcnow()


def _iter_log_entries(session: AssessmentSession):
    for entry in session.evidence_log or []:
        yield entry


def _aggregate(session: AssessmentSession) -> dict[str, dict[str, Any]]:
    """یکجاسازی همهٔ شواهدِ ثبت‌شده در جلسه به تفکیک گزاره."""
    per_prop: dict[str, dict[str, Any]] = {}
    for entry in _iter_log_entries(session):
        qid = entry.get("question_id")
        for ev in entry.get("evidence", []):
            prop = ev.get("proposition_id", "?")
            agg = per_prop.setdefault(
                prop,
                {
                    "confirming_qids": set(),
                    "weak_confirming": 0,
                    "strong_confirming": 0,
                    "computational_only": 0,
                    "contradicting_qids": set(),
                    "strong_contradicting": 0,
                    "weak_contradicting": 0,
                    "unclear": 0,
                    "needs_teacher_review": 0,
                    "evidences": [],
                },
            )
            status = ev.get("status")
            etype = ev.get("evidence_type", "weak_confirming")
            confidence = float(ev.get("confidence", 0.0) or 0.0)
            is_strong = etype in ("strong_confirming",) or confidence >= 0.7

            if status in CONFIRMING:
                if etype == "computational_success":
                    # موفقیت صرفاً محاسباتی: ثبت می‌شود ولی هیچ گزارهٔ اصلی را ارتقا نمی‌دهد
                    agg["computational_only"] += 1
                elif is_strong:
                    agg["strong_confirming"] += 1
                    if qid is not None:
                        agg["confirming_qids"].add(qid)
                else:
                    agg["weak_confirming"] += 1
                    if qid is not None:
                        agg["confirming_qids"].add(qid)
            elif status == EvidenceStatus.NEEDS_REVIEW.value:
                if etype == "strong_contradicting" or confidence >= 0.6:
                    agg["strong_contradicting"] += 1
                else:
                    agg["weak_contradicting"] += 1
                if qid is not None:
                    agg["contradicting_qids"].add(qid)
            elif status == EvidenceStatus.UNCLEAR.value:
                agg["unclear"] += 1

            if ev.get("needs_teacher_review"):
                agg["needs_teacher_review"] += 1
            agg["evidences"].append(ev)
    return per_prop


def _status_for_prop(agg: dict[str, Any]) -> str:
    indep_confirming = len(agg["confirming_qids"])  # فقط شواهدِ مفهومیِ مستقل (سؤال‌های متفاوت)
    strong_contra = agg["strong_contradicting"]
    contra_any = strong_contra + agg["weak_contradicting"]
    confirm_any = agg["strong_confirming"] + agg["weak_confirming"]  # فقط مفهومی

    # ۴) حداقل یک شاهدِ ردکنندهٔ قوی → نیاز به بررسی (مقدم)
    if strong_contra >= 1:
        return EvidenceStatus.NEEDS_REVIEW.value
    # ۳) شواهد متناقض → نامشخص
    if confirm_any >= 1 and contra_any >= 1:
        return EvidenceStatus.UNCLEAR.value
    # ۱) ≥۲ تأیید مستقل → تأییدشده
    if indep_confirming >= 2 and contra_any == 0:
        return EvidenceStatus.CONFIRMED.value
    # ۲) ۱ تأیید قوی یا ≥۲ تأیید ضعیف → احتمالاً آموخته‌شده
    if (agg["strong_confirming"] >= 1 or confirm_any >= 2) and contra_any == 0:
        return EvidenceStatus.LIKELY_UNDERSTOOD.value
    if confirm_any == 1:
        return EvidenceStatus.LIKELY_UNDERSTOOD.value
    # فقط موفقیت محاسباتی: فهم مفهومی هنوز معلوم نیست → نامشخص
    if agg["computational_only"] >= 1:
        return EvidenceStatus.UNCLEAR.value
    if agg["unclear"] >= 1:
        return EvidenceStatus.UNCLEAR.value
    return EvidenceStatus.INSUFFICIENT_EVIDENCE.value


class InferenceEngine:
    def __init__(self, db: Session):
        self.db = db

    # ---------- به‌روزرسانی شواهد ----------
    def update_evidence(
        self,
        session: AssessmentSession,
        new_evidence: list,
        question_id: int | None = None,
        response_text: str | None = None,
    ) -> dict[str, Any]:
        """شواهد جدید را در evidence_log جلسه ثبت و وضعیت همهٔ گزاره‌ها را بازمحاسبه می‌کند.

        new_evidence: فهرست EvidenceRecord (یا dict). question_id/response_text برای ثبت در لاگ.
        خروجی: {proposition_statuses, concept_status, conflicts, needs_teacher_review, log_entry}
        """
        serialized = []
        for ev in new_evidence:
            serialized.append(ev if isinstance(ev, dict) else ev.to_dict())

        log = list(session.evidence_log or [])
        if serialized:
            log.append(
                {
                    "question_id": question_id,
                    "response": response_text or "",
                    "answered_at": _now().isoformat(),
                    "evidence": serialized,
                }
            )
            session.evidence_log = log

        aggregates = _aggregate(session)
        proposition_statuses = {prop: _status_for_prop(agg) for prop, agg in aggregates.items()}

        # گزاره‌های بدون شواهدِ این جلسه ولی هدفِ جلسه → INSUFFICIENT_EVIDENCE
        target_propositions = self._target_propositions(session)
        for prop in target_propositions:
            proposition_statuses.setdefault(prop, EvidenceStatus.INSUFFICIENT_EVIDENCE.value)

        conflicts = [
            prop
            for prop, agg in aggregates.items()
            if (agg["strong_confirming"] + agg["weak_confirming"] > 0)
            and (agg["strong_contradicting"] + agg["weak_contradicting"] > 0)
        ]
        needs_teacher_review = any(agg["needs_teacher_review"] > 0 for agg in aggregates.values())

        concept_status = self._concept_status(session, proposition_statuses)

        return {
            "proposition_statuses": proposition_statuses,
            "concept_status": concept_status,
            "conflicts": conflicts,
            "needs_teacher_review": needs_teacher_review,
            "answered_count": len(log),
        }

    # ---------- شرایط ادامه/توقف ----------
    def should_continue(
        self,
        session: AssessmentSession,
        time_remaining_seconds: float,
        student_requested_stop: bool = False,
        no_more_questions: bool = False,
    ) -> bool:
        if student_requested_stop:
            return False
        if time_remaining_seconds <= 0:
            return False
        if no_more_questions:
            return False
        if len(session.evidence_log or []) >= settings.MAX_SESSION_QUESTIONS:
            return False

        aggregates = _aggregate(session)
        statuses = {prop: _status_for_prop(agg) for prop, agg in aggregates.items()}
        targets = self._target_propositions(session)

        if targets:
            resolved = {EvidenceStatus.CONFIRMED.value, EvidenceStatus.NEEDS_REVIEW.value}
            all_resolved = all(statuses.get(p, EvidenceStatus.INSUFFICIENT_EVIDENCE.value) in resolved for p in targets)
            if all_resolved:
                # همهٔ گزاره‌های هدف یا تأیید شده‌اند یا به‌قطع نیاز به بررسی دارند → توقف
                # مگر فرضیهٔ بین‌درسیِ معلق هنوز باقی باشد
                if self._has_pending_cross_subject_hypothesis(session):
                    return True
                return False
            # هر گزارهٔ مبهمی که زمان برایش مانده → ادامه
            if any(statuses.get(p) == EvidenceStatus.UNCLEAR.value for p in targets):
                return True
            return True  # هنوز گزاره‌ای بدون شواهدِ کافی هست
        # بدون هدف مشخص: اگر چیزی مبهم هست ادامه بده
        if any(s == EvidenceStatus.UNCLEAR.value for s in statuses.values()):
            return True
        return bool(self._has_pending_cross_subject_hypothesis(session))

    # ---------- انتخاب هدف بعدی ----------
    def select_next_investigation_target(
        self, session: AssessmentSession
    ) -> Optional[tuple[Concept, str]]:
        """اولویت:
        ۱) گزاره‌های اصلیِ UNCLEAR در مفهومِ هدف
        ۲) تعارض‌های حل‌نشده (همان UNCLEAR هستند — صریحاً هم پوشش داده می‌شود)
        ۳) فرضیه‌های ریشهٔ خطای بین‌درسی که هنوز تست نشده‌اند
        ۴) گزاره‌های LIKELY_UNDERSTOOD برای تأیید قطعی
        ۵) گزاره‌های بدون شواهدِ کافی (شروع جلسه)
        """
        concept = self.db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
        aggregates = _aggregate(session)
        statuses = {prop: _status_for_prop(agg) for prop, agg in aggregates.items()}

        target_props = self._target_propositions(session)

        def status_of(p: str) -> str:
            return statuses.get(p, EvidenceStatus.INSUFFICIENT_EVIDENCE.value)

        # ۱ + ۲) مبهم‌ها / تعارض‌ها
        if concept is not None:
            unclear = [p for p in target_props if status_of(p) == EvidenceStatus.UNCLEAR.value]
            if unclear:
                # ابتدا گزارهٔ دارای بیشترین تعارض
                unclear.sort(
                    key=lambda p: len(aggregates.get(p, {}).get("evidences", [])),
                    reverse=True,
                )
                return concept, unclear[0]

        # ۳) فرضیهٔ بین‌درسیِ معلق — تستِ پیش‌نیازِ کم‌عمق‌تر/ابزار ریاضی
        hypotheses = list(session.current_hypotheses or [])
        hyp_changed = False
        for hyp in hypotheses:
            if hyp.get("status") != "pending":
                continue
            hyp_concept_id = hyp.get("concept_id")
            if not hyp_concept_id:
                continue
            hyp_concept = self.db.query(Concept).filter(Concept.id == hyp_concept_id).first()
            if hyp_concept and hyp_concept.core_propositions:
                hyp["status"] = "testing"
                hyp_changed = True
                if hyp_changed:
                    session.current_hypotheses = hypotheses  # بازتخصیص برای ردیابی JSON توسط SQLAlchemy
                return hyp_concept, hyp_concept.core_propositions[0]

        # ۴) احتمالاً آموخته‌شده → به‌دنبال تأیید قطعی
        if concept is not None:
            likely = [p for p in target_props if status_of(p) == EvidenceStatus.LIKELY_UNDERSTOOD.value]
            if likely:
                return concept, likely[0]

        # ۵) بدون شواهد → شروع از اولین گزارهٔ هدف
        if concept is not None:
            untested = [p for p in target_props if status_of(p) == EvidenceStatus.INSUFFICIENT_EVIDENCE.value]
            if untested:
                return concept, untested[0]
            # هیچ‌چیز نمانده → None (یعنی توقف)
        return None

    # ---------- ابزارهای داخلی ----------
    def _target_propositions(self, session: AssessmentSession) -> list[str]:
        """گزاره‌های هدف جلسه: برای مسیر A گزاره‌های اصلی مفهوم؛ برای مسیر B همان‌ها + فرضیه‌ها."""
        props: list[str] = []
        if session.concept_id:
            concept = self.db.query(Concept).filter(Concept.id == session.concept_id).first()
            if concept:
                props.extend(concept.core_propositions or [])
        for hyp in session.current_hypotheses or []:
            p = hyp.get("proposition")
            if p and p not in props:
                props.append(p)
        # حذف تکراری با حفظ ترتیب
        seen, ordered = set(), []
        for p in props:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered

    def _has_pending_cross_subject_hypothesis(self, session: AssessmentSession) -> bool:
        return any(
            hyp.get("status") == "pending" and hyp.get("concept_id")
            for hyp in session.current_hypotheses or []
        )

    def _concept_status(self, session: AssessmentSession, proposition_statuses: dict[str, str]) -> str:
        """وضعیت کلی مفهوم — گزاره‌های اصلی مقدم‌اند:
        اگر حتی یک گزارهٔ اصلی NEEDS_REVIEW باشد، مفهوم NEEDS_REVIEW است؛
        موفقیت محاسباتی نمی‌تواند آن را ارتقا دهد."""
        concept = self.db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
        core = list(concept.core_propositions or []) if concept else []
        core_statuses = [proposition_statuses.get(p, EvidenceStatus.INSUFFICIENT_EVIDENCE.value) for p in core]

        if not core_statuses:
            values = list(proposition_statuses.values())
            if not values:
                return EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            core_statuses = values

        if any(s == EvidenceStatus.NEEDS_REVIEW.value for s in core_statuses):
            return EvidenceStatus.NEEDS_REVIEW.value
        if all(s == EvidenceStatus.CONFIRMED.value for s in core_statuses):
            return EvidenceStatus.CONFIRMED.value
        if all(s == EvidenceStatus.INSUFFICIENT_EVIDENCE.value for s in core_statuses):
            return EvidenceStatus.INSUFFICIENT_EVIDENCE.value
        if any(s == EvidenceStatus.UNCLEAR.value for s in core_statuses):
            return EvidenceStatus.UNCLEAR.value
        return EvidenceStatus.LIKELY_UNDERSTOOD.value
