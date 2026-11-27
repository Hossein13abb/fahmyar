"""فاز ۳۳ — «database disk image is malformed» نباید دوباره اتفاق بیفتد.

── سابقهٔ باگ (خطای واقعیِ کاربر) ──
صفحهٔ «تاریخچهٔ آزمون‌های من» با این خطا از کار افتاد:

    sqlite3.DatabaseError: database disk image is malformed
    [SQL: SELECT assessment_sessions...]

علت: در فاز ۳۱ دستورِ ``git add -A`` فایل‌های موقتِ WAL دیتابیسِ توسعه
(``fahmyar.db-wal`` و ``fahmyar.db-shm``) را به ریپو برد، چون ``.gitignore``
فقط ``*.db`` را می‌گرفت و این دو با آن الگو جور نبودند. با ``git pull`` روی
سیستمِ کاربر، این فایل‌ها کنارِ دیتابیسِ **او** نشستند و SQLite کوشید
تغییرهای یک دیتابیس را روی دیگری اعمال کند.

── دو درسِ این فایل ──
۱. فایل‌های جانبیِ SQLite هرگز نباید در گیت باشند (تستِ ``.gitignore``).
۲. تشخیصِ WALِ ناهمخوان با «تلاش برای باز کردن» کافی نیست: در آزمایشِ واقعی
   دیدم SQLite **بدونِ هیچ خطایی** محتوای WALِ غریبه را اعمال می‌کند و
   گزارش «سالم» می‌دهد — با دادهٔ اشتباه. پس ``tools/repair_db.py`` دو
   خواندن می‌کند و شمارش‌ها را مقایسه می‌کند.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPAIR = ROOT / "tools" / "repair_db.py"


# ─────────────────────────────────────────────────────────────────────────
# ۱) رگرسیونِ ریشه‌ای: فایل‌های WAL هرگز در گیت نباشند
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "name",
    [
        "fahmyar.db-wal",
        "fahmyar.db-shm",
        "fahmyar.db-journal",
        "any.sqlite-wal",
        "any.sqlite-shm",
    ],
)
def test_gitignore_covers_sqlite_sidecar_files(name: str):
    """``.gitignore`` باید فایل‌های جانبیِ WAL را بگیرد، نه فقط ``*.db``.

    الگوی ``*.db`` این‌ها را نمی‌گیرد چون نامشان به ``-wal`` ختم می‌شود.
    همین شکاف باعث شد فایل‌های موقتِ دیتابیسِ من وارد گیت شوند.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", name],
        cwd=str(ROOT),
        capture_output=True,
    )
    assert result.returncode == 0, f"«{name}» در .gitignore پوشش داده نشده است"


def test_no_sqlite_sidecar_is_tracked_by_git():
    """هیچ فایلِ wal/shm/journal نباید در ایندکسِ گیت باشد."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("گیت در دسترس نیست")
    tracked = [
        line
        for line in result.stdout.splitlines()
        if line.endswith(("-wal", "-shm", "-journal"))
    ]
    assert tracked == [], f"این فایل‌های موقت در گیت ردیابی می‌شوند: {tracked}"


# ─────────────────────────────────────────────────────────────────────────
# ۲) ابزارِ تعمیر — روی دیتابیس‌های ساختگی
# ─────────────────────────────────────────────────────────────────────────
def _make_db(path: Path, rows: int, *, wal: bool = False) -> None:
    conn = sqlite3.connect(str(path))
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS assessment_sessions "
            "(id INTEGER PRIMARY KEY, student_id INT)"
        )
        conn.executemany(
            "INSERT INTO assessment_sessions (student_id) VALUES (?)",
            [(1,)] * rows,
        )
        conn.commit()
    finally:
        conn.close()


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPAIR), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )


def test_tool_reports_healthy_db_without_touching_it(tmp_path):
    db = tmp_path / "healthy.db"
    _make_db(db, 7)
    before = db.read_bytes()

    result = _run("--db", str(db))
    assert "سالم" in result.stdout
    assert result.returncode == 0
    # هیچ بایتی عوض نشده باشد
    assert db.read_bytes() == before
    assert not list(tmp_path.glob("*.bak-*"))


def test_tool_detects_truly_malformed_file(tmp_path):
    """فایلِ واقعاً خراب باید «نیازمندِ تعمیر» گزارش شود، نه سالم."""
    db = tmp_path / "bad.db"
    _make_db(db, 60)
    # خرابیِ میانِ فایل — شبیهِ سکتورِ خراب
    size = db.stat().st_size
    with open(db, "r+b") as fh:
        fh.seek(size // 3)
        fh.write(b"\xde\xad\xbe\xef" * 400)

    result = _run("--db", str(db))
    assert result.returncode == 1
    assert "نیازمندِ تعمیر" in result.stdout or "malformed" in result.stdout


def test_tool_detects_foreign_wal_by_row_count(tmp_path):
    """WALِ دیتابیسِ دیگر باید با **مقایسهٔ شمارش** گرفته شود.

    این همان باگی است که در نسخهٔ اولِ ابزارِ خودم بود: SQLite خطا نمی‌داد
    و تعدادِ ردیف‌های دیتابیسِ بیگانه را برمی‌گرداند. تنها راهِ تشخیص،
    خواندنِ دوم بدونِ WAL است.
    """
    db = tmp_path / "victim.db"
    _make_db(db, 5)

    # WAL از یک دیتابیسِ دیگر با تعدادِ ردیفِ متفاوت
    source = tmp_path / "source.db"
    conn = sqlite3.connect(str(source))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE assessment_sessions (id INTEGER PRIMARY KEY, student_id INT, pad TEXT)"
        )
        conn.executemany(
            "INSERT INTO assessment_sessions (student_id, pad) VALUES (?, ?)",
            [(i, "x" * 80) for i in range(40)],
        )
        conn.commit()
        wal_src = tmp_path / "source.db-wal"
        if wal_src.exists():
            (tmp_path / "victim.db-wal").write_bytes(wal_src.read_bytes())
    finally:
        conn.close()

    if not (tmp_path / "victim.db-wal").exists():
        pytest.skip("WAL مبدأ در این نسخهٔ SQLite ساخته نشد")

    result = _run("--db", str(db))
    assert "ناهمخوان" in result.stdout, result.stdout
    assert result.returncode == 1


def test_repair_quarantines_sidecars_instead_of_deleting(tmp_path):
    """تعمیر باید فایل‌ها را **کنار بگذارد** نه پاک کند.

    حذفِ خودکارِ داده بدتر از خطای قابلِ رفع است: اگر معلوم شود WAL
    دادهٔ مهمی داشت، کاربر باید بتواند برگرداندش.
    """
    db = tmp_path / "victim2.db"
    _make_db(db, 3)
    (tmp_path / "victim2.db-wal").write_bytes(b"not a real wal" * 100)

    result = _run("--db", str(db), "--repair")
    assert result.returncode == 0, result.stdout

    backups = list(tmp_path.glob("victim2.db-wal.bak-*"))
    assert backups, "فایل به‌جای کنارگذاشتن، حذف شد"


def test_tool_never_modifies_the_main_db_file(tmp_path):
    """فایلِ اصلیِ دیتابیس در هیچ حالتی نباید تغییر کند."""
    db = tmp_path / "keep.db"
    _make_db(db, 9)
    (tmp_path / "keep.db-wal").write_bytes(b"x" * 5000)
    original = db.read_bytes()

    _run("--db", str(db), "--repair")
    assert db.read_bytes() == original


# ─────────────────────────────────────────────────────────────────────────
# ۳) رفتارِ خودِ SQLite که باعثِ سردرگمی می‌شد
# ─────────────────────────────────────────────────────────────────────────
def test_sqlite_silently_accepts_foreign_wal(tmp_path):
    """مستندسازیِ همان دامی که ابزار باید جبرانش کند.

    اگر روزی SQLite سخت‌گیرتر شود و این‌جا خطا داد، یعنی می‌توانیم
    ساده‌سازی کنیم — و آن خبرِ خوبی است.
    """
    db = tmp_path / "silent.db"
    _make_db(db, 4)

    source = tmp_path / "src.db"
    conn = sqlite3.connect(str(source))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE assessment_sessions (id INTEGER PRIMARY KEY, student_id INT, pad TEXT)")
        conn.executemany(
            "INSERT INTO assessment_sessions (student_id, pad) VALUES (?, ?)",
            [(i, "y" * 60) for i in range(25)],
        )
        conn.commit()
        wal_src = tmp_path / "src.db-wal"
        if not wal_src.exists():
            pytest.skip("WAL مبدأ ساخته نشد")
        (tmp_path / "silent.db-wal").write_bytes(wal_src.read_bytes())
    finally:
        conn.close()

    # انتظار: SQLite خطا **نمی‌دهد** و حتی ممکن است تعدادِ اشتباه بدهد.
    conn = sqlite3.connect(str(db), timeout=5)
    try:
        count = conn.execute("SELECT COUNT(*) FROM assessment_sessions").fetchone()[0]
    finally:
        conn.close()
    # فقط ثبت می‌کنیم که خطا نداد — هر عددی که باشد، درس همان است.
    assert isinstance(count, int)


# ─────────────────────────────────────────────────────────────────────────
# ۴) پیامِ خطا نباید SQL و جزئیاتِ داخلی را لو بدهد
# ─────────────────────────────────────────────────────────────────────────
def test_unhandled_error_hides_sql_and_internals():
    """خطای ۵۰۰ نباید متنِ SQL، نامِ جدول یا مسیرِ فایل را به کاربر بدهد.

    سابقه: در خطای «malformed» دانش‌آموز کلِ کوئریِ SELECT با نامِ
    جدول‌ها و پارامترها را دید. هم لو دادنِ ساختار، هم بی‌فایده برای او.
    """
    from fastapi.testclient import TestClient

    import main as app_module

    app = app_module.app

    @app.get("/__test_boom")
    def _boom():
        raise RuntimeError(
            "(sqlite3.DatabaseError) database disk image is malformed "
            "[SQL: SELECT assessment_sessions.id FROM assessment_sessions] "
            "[parameters: (1, 'completed')]"
        )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__test_boom")

    assert response.status_code == 500
    body = response.json()["detail"]
    # هیچ‌کدام از این‌ها نباید به کاربر برسد
    for leak in ("SQL:", "SELECT", "assessment_sessions", "parameters", "sqlite3"):
        assert leak not in body, f"«{leak}» در پیامِ کاربر ماند: {body}"
    # ولی باید یک راهنمای قابلِ اقدام داشته باشد
    assert len(body) > 20


def test_malformed_error_gives_actionable_hint():
    """خطای malformed باید بگوید کاربر چه کار کند، نه فقط «خطا شد»."""
    from fastapi.testclient import TestClient

    import main as app_module

    app = app_module.app

    @app.get("/__test_boom2")
    def _boom2():
        raise RuntimeError("database disk image is malformed")

    client = TestClient(app, raise_server_exceptions=False)
    body = client.get("/__test_boom2").json()["detail"]
    assert "repair_db" in body
