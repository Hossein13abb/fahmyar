"""مدل کاربر و نقش‌ها."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from models.database import Base

ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN}
VALID_MAJORS = {"math", "experimental", "general"}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), nullable=False, default=ROLE_STUDENT)  # student | teacher | admin
    grade = Column(Integer, nullable=True)  # 10 | 11 | 12 (برای دانش‌آموزان)
    major = Column(String(20), nullable=True)  # math | experimental | general
    full_name = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "grade": self.grade,
            "major": self.major,
            "full_name": self.full_name,
        }
