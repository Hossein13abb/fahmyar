"""مدل‌های سؤال و جلسهٔ ارزیابی + enum وضعیت شواهد (کیفی، نه عددی)."""
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON

from models.database import Base


class EvidenceStatus(str, enum.Enum):
    """وضعیت کیفی هر گزاره در ذهن دانش‌آموز — هرگز به عدد تبدیل نمی‌شود."""

    CONFIRMED = "CONFIRMED"
    LIKELY_UNDERSTOOD = "LIKELY_UNDERSTOOD"
    UNCLEAR = "UNCLEAR"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


STATUS_FA = {
    EvidenceStatus.CONFIRMED.value: "تأییدشده",
    EvidenceStatus.LIKELY_UNDERSTOOD.value: "احتمالاً آموخته‌شده",
    EvidenceStatus.UNCLEAR.value: "نامشخص",
    EvidenceStatus.NEEDS_REVIEW.value: "نیاز به بررسی",
    EvidenceStatus.INSUFFICIENT_EVIDENCE.value: "فاقد شواهد کافی",
}

# مقادیر معتبر question_type
QUESTION_TYPES = {
    "phenomenon_explain",
    "compare_explanations",
    "predict",
    "categorize",
    "error_identify",
    "novel_application",
}


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=False, index=True)

    text = Column(Text, nullable=False)
    question_type = Column(String(40), nullable=False, default="phenomenon_explain")
    difficulty = Column(String(10), nullable=False, default="medium")  # easy | medium | hard
    cognitive_type = Column(String(20), nullable=False, default="conceptual")
    # recall | conceptual | computational | combined

    # rubric = {correct_reasoning, misconception_indicators: {...},
    #           partial_credit_signs: [...], non_conceptual_errors: [...],
    #           phenomenon_description?, required_data?}
    rubric = Column(JSON, default=dict)
    mapped_propositions = Column(JSON, default=list)  # list[str] — همان متن گزاره‌ها
    mapped_misconceptions = Column(JSON, default=list)  # list[str]

    source = Column(String(20), nullable=False, default="ai_generated")
    # "ai_generated" | "teacher_approved" | "bank"
    approval_status = Column(String(20), nullable=False, default="pending", index=True)
    # "pending" | "approved" | "rejected"
    ai_model_used = Column(String(100), nullable=True)
    generation_cost_usd = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:  # pragma: no cover - دیباگ
        return f"<Question id={self.id} type={self.question_type} status={self.approval_status}>"


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    trigger_type = Column(String(30), nullable=False)  # topic_selection | wrong_answer
    trigger_detail = Column(Text, nullable=True)  # مفهوم انتخابی یا متن پاسخ غلط

    concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=True, index=True)

    started_at = Column(DateTime, default=datetime.utcnow)
    time_limit_seconds = Column(Integer, default=1800)  # ۳۰ دقیقه — سقف سخت
    total_paused_seconds = Column(Float, default=0.0)
    paused_at = Column(DateTime, nullable=True)

    status = Column(String(30), nullable=False, default="active", index=True)
    # active | completed | paused | insufficient_evidence

    # hypotheses: [{type, concept_id?, concept_topic?, proposition, status, reason, depth?}]
    current_hypotheses = Column(JSON, default=list)
    # evidence_log: [{question_id, response, answered_at, evidence: [ {proposition_id, status,
    #                   evidence_type, reasoning, confidence, needs_teacher_review, error_type} ]}]
    evidence_log = Column(JSON, default=list)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "trigger_type": self.trigger_type,
            "concept_id": self.concept_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "time_limit_seconds": self.time_limit_seconds,
            "total_paused_seconds": self.total_paused_seconds,
            "questions_answered": len(self.evidence_log or []),
        }
