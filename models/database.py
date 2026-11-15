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


def _ensure_columns() -> None:
    """ستون‌های تازه‌ای که ``create_all`` به جدولِ موجود اضافه نمی‌کند.

    ``Base.metadata.create_all`` فقط جدولِ غایب را می‌سازد؛ اگر جدول از قبل
    باشد، ستونِ جدید بی‌صدا نادیده گرفته می‌شود و کوئری با «no such column»
    می‌شکند. این تابع همان کمبود را با یک ALTER TABLE ساده جبران می‌کند —
    برای SQLite و PostgreSQL هر دو کار می‌کند و idempotent است.
    """
    from sqlalchemy import inspect, text

    additions = {
        "assessment_sessions": {
            "cognitive_payload": "JSON",
            "cognitive_report": "JSON",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name in present:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def init_db() -> None:
    """ایجاد جدول‌ها (در صورت نبود). مدل‌ها ابتدا ایمپورت می‌شوند تا رجیستر شوند."""
    from models import concept, question, user, ai_log  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
