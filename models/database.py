"""راه‌اندازی پایگاه داده (SQLite + SQLAlchemy) و دیپندنسی FastAPI."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# ── قفلِ نوشتن در SQLite (فاز ۳۱) ──
#
# سابقه: در آزمونِ زندهٔ واقعی، هنگامِ ذخیرهٔ لاگِ مصرفِ مدل در پس‌زمینه،
# پیامِ «database is locked» در لاگ ظاهر شد. SQLite در حالتِ پیش‌فرض
# (rollback journal) هر نوشتن را قفلِ انحصاریِ کلِ فایل می‌کند؛ اگر همان
# لحظه درخواستِ دیگری (مثلاً ثبتِ پاسخ یا ساختِ کارنامه) بنویسد، منتظر
# نمی‌ماند و فوراً خطا می‌دهد.
#
# سه تنظیم این را حل می‌کند:
#   • timeout=30     — به‌جای خطای فوری، تا ۳۰ ثانیه برای قفل صبر کن.
#   • WAL            — خواندن و نوشتن هم‌زمان ممکن می‌شود (نوشتن‌ها سریالی
#                      ولی خواندن‌ها بلوکه نمی‌شوند).
#   • busy_timeout   — همان صبر، در سطحِ درایور، برای قفل‌های لحظه‌ای.
connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

if _is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
        """WAL و busy_timeout روی هر اتصالِ تازه اعمال می‌شود.

        ``journal_mode=WAL`` یک‌بار برای همیشه روی فایل ذخیره می‌شود، ولی
        ``busy_timeout`` مخصوصِ همان اتصال است — پس هر دو این‌جا لازم‌اند.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
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
