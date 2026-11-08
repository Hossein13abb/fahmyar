"""راه‌اندازی پایگاه داده (SQLite + SQLAlchemy) و دیپندنسی FastAPI."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """دیپندنسی FastAPI: یک سشن دیتابیس برای هر درخواست باز می‌کند و در پایان می‌بندد."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """ایجاد جدول‌ها (در صورت نبود). مدل‌ها ابتدا ایمپورت می‌شوند تا رجیستر شوند."""
    from models import concept, question, user, ai_log  # noqa: F401

    Base.metadata.create_all(bind=engine)
