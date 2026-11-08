"""لاگ استفاده از هوش مصنوعی — همهٔ فراخوانی‌ها ثبت می‌شوند:

model_name, token_count, cost_usd, task_type, timestamp (+ provider, success)
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from models.database import Base


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    provider = Column(String(50), default="")
    model_name = Column(String(100), default="")
    task_type = Column(String(50), default="", index=True)  # generate_question | analyze_response | ...
    token_count = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
