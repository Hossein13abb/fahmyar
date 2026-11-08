"""مدل‌های مفهوم (گره گراف دانش) و وابستگی مفاهیم (یال‌های DAG)."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, JSON

from models.database import Base


class Concept(Base):
    """یک گره در گراف دانش — یک مفهوم آموزشی در یک درس و پایه."""

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("subject", "topic", name="uq_concept_subject_topic"),)

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(50), nullable=False, index=True)  # math | physics | chemistry | ...
    grade = Column(Integer, nullable=False, index=True)  # 10 | 11 | 12
    chapter = Column(String(200), default="")
    topic = Column(String(100), nullable=False)  # کلید انگلیسی مثل "coulomb_law"
    name = Column(String(200), nullable=False)  # نام نمایشی فارسی مثل «قانون کولن»

    # فهرست گزاره‌های اصلی مفهوم — فهم واقعی = تسلط بر همین گزاره‌ها
    core_propositions = Column(JSON, default=list)  # list[str]
    # فهرست بدفهمی‌های رایج: {misconception, root_cause, diagnostic_signs: [...]}
    common_misconceptions = Column(JSON, default=list)
    # فهرست رفتارهای هدف — از میان: recall, explain, convert_representation,
    # identify_conditions, predict, solve, apply_novel, identify_error, connect
    target_behaviors = Column(JSON, default=list)

    def __repr__(self) -> str:  # pragma: no cover - دیباگ
        return f"<Concept {self.subject}/{self.topic}>"


class ConceptDependency(Base):
    """یال گراف: source برای فهمیدنِ target لازم است (پیش‌نیاز / ابزار / مرتبط)."""

    __tablename__ = "concept_dependencies"

    id = Column(Integer, primary_key=True)
    source_concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=False, index=True)
    target_concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=False, index=True)
    dependency_type = Column(String(20), nullable=False, default="prerequisite")
    # "prerequisite" | "tool" | "related"
    cross_subject = Column(Boolean, default=False)
