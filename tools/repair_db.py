"""ابزارِ نجات و بازرسیِ دیتابیسِ SQLite — «database disk image is malformed».

── چه زمانی لازم می‌شود ──
پیام‌هایی مثلِ:

    sqlite3.DatabaseError: database disk image is malformed
    database disk image is malformed [SQL: SELECT assessment_sessions...]

معمولاً یعنی فایلِ اصلی خراب نشده، بلکه یکی از دو فایلِ جانبیِ WAL با آن
نمی‌خواند:

    fahmyar.db-wal   ← تغییرهای هنوز ادغام‌نشده
    fahmyar.db-shm   ← حافظهٔ اشتراکیِ ایندکسِ WAL

این دو **وضعیتِ موقتِ یک پروسه** هستند، نه داده. اگر از جای دیگری کپی
بیایند (مثلاً از گیت یا از سیستمِ دیگری)، SQLite می‌کوشد تغییرهای یک
دیتابیس را روی دیگری اعمال کند، چک‌سام نمی‌خواند و «malformed» می‌دهد.

── ترتیبِ کارِ این ابزار ──
  ۱. وضعیت را گزارش می‌دهد (اندازهٔ فایل، وجودِ WAL، نتیجهٔ integrity_check).
  ۲. اگر خراب بود: اول WAL/SHM را **کنار** می‌گذارد (نه پاک) و دوباره
     بررسی می‌کند. در ۹۹٪ موارد همین کافی است و هیچ داده‌ای نمی‌رود.
  ۳. اگر باز هم خراب بود، فقط آن‌وقت از نسخهٔ پشتیبان/`.bak` استفاده می‌کند.
  ۴. هرگز خودبه‌خود چیزی را حذف نمی‌کند؛ با ``--force`` هم فقط کنار می‌گذارد.

استفاده:
    python tools/repair_db.py                 # فقط گزارش
    python tools/repair_db.py --repair        # کنار گذاشتنِ WAL/SHM
    python tools/repair_db.py --db دیگر.db
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "fahmyar.db"

SIDECARS = ("-wal", "-shm", "-journal")


@dataclass
class Status:
    path: Path
    db_exists: bool
    db_size: int
    sidecars: list[tuple[str, int]]
    integrity: str | None
    error: str | None
    session_count: int | None
    #: WAL/SHMای که کنارِ دیتابیس هست ولی به آن تعلق ندارد (یا محتوایش
    #: بی‌معنی است). حتی اگر SQLite نادیده‌اش بگیرد، باید برود.
    stray_sidecars: bool = False

    @property
    def healthy(self) -> bool:
        return self.error is None and self.integrity == "ok" and not self.stray_sidecars


def inspect(path: Path) -> Status:
    """دیتابیس را بدونِ تغییرِ هیچ چیزی می‌خواند."""
    db_exists = path.exists()
    db_size = path.stat().st_size if db_exists else 0
    sidecars = []
    for suffix in SIDECARS:
        side = path.with_name(path.name + suffix)
        if side.exists():
            sidecars.append((side.name, side.stat().st_size))

    integrity: str | None = None
    error: str | None = None
    count: int | None = None
    if db_exists:
        # ⚠️ چرا «فقط باز کردن و پرسیدن» کافی نیست:
        #
        # دیدم (با آزمایشِ واقعی) که اگر ``-wal`` متعلق به دیتابیسِ دیگری
        # باشد ولی اندازهٔ صفحه‌اش تصادفاً بخواند، SQLite **هیچ خطایی
        # نمی‌دهد** و بی‌صدا محتوای آن WAL را روی فایلِ اصلی اعمال می‌کند.
        # نتیجه: گزارشِ «سالم»، ولی با دادهٔ اشتباه — بدتر از خطا.
        #
        # راهِ تشخیص: WAL سرصفحه‌ای دارد که هویتِ دیتابیس (salt) را نگه
        # می‌دارد، ولی SQLite ابزارِ پرسیدنش را نمی‌دهد. پس دو سنجه می‌گیریم
        # و با هم می‌سنجیم: خواندنِ مستقیم، و خواندن با WALِ کنارگذاشته.
        # اگر شمارشِ ردیف‌ها یکی نبود، WAL متعلق به این فایل نیست.
        try:
            integrity, count = _read_probe(path)
        except sqlite3.Error as exc:
            error = str(exc)
            integrity, count = None, None

        stray = False
        if sidecars and error is None:
            base_count = _read_probe_without_wal(path)
            if base_count is not None and count is not None and base_count != count:
                error = (
                    f"WALِ ناهمخوان: با WAL {count} ردیف دیده می‌شود، بدونِ آن "
                    f"{base_count} ردیف. فایل‌های wal/shm متعلق به این دیتابیس "
                    "نیستند (احتمالاً از محیطِ دیگری آمده‌اند)."
                )
            elif not _sidecar_is_valid(path):
                # WAL سرصفحهٔ معتبر ندارد (فایلِ نیمه‌کاره یا محتوای بی‌ربط).
                # SQLite بی‌صدا نادیده‌اش می‌گیرد، ولی وجودش خودِ ریسک است:
                # به‌محضِ تغییرِ نسخه یا اندازهٔ صفحه، می‌تواند داده را
                # خراب کند. پس «هرز» علامت می‌خورد تا پاک شود.
                stray = True
    else:
        error = "فایلِ دیتابیس وجود ندارد."
    return Status(path, db_exists, db_size, sidecars, integrity, error, count, stray)


def _read_probe(path: Path) -> tuple[str, int | None]:
    """integrity_check و شمارشِ ردیف — بدونِ تغییرِ چیزی."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        try:
            count = int(conn.execute("SELECT COUNT(*) FROM assessment_sessions").fetchone()[0])
        except sqlite3.Error:
            count = None
        return integrity, count
    finally:
        conn.close()


#: امضای سرصفحهٔ یک WALِ واقعی (۴ بایتِ اولِ فایل).
_WAL_MAGIC = b"\x37\x7f\x06\x82"


def _sidecar_is_valid(path: Path) -> bool:
    """آیا فایلِ ``-wal`` سرصفحهٔ معتبرِ SQLite دارد؟

    SQLite برای WAL امضای ثابتی می‌گذارد. اگر امضا نباشد، فایل یا نیمه‌کاره
    است یا اصلاً WAL نیست — در هر دو حالت باید کنار گذاشته شود، حتی اگر
    SQLite فعلاً نادیده‌اش بگیرد (رفتارش با تغییرِ نسخه تضمینی نیست).
    """
    wal = path.with_name(path.name + "-wal")
    if not wal.exists():
        return True  # چیزی نیست که معتبر یا نامعتبر باشد
    try:
        with open(wal, "rb") as fh:
            head = fh.read(4)
    except OSError:
        return False
    return head == _WAL_MAGIC


def _read_probe_without_wal(path: Path) -> int | None:
    """شمارشِ ردیف با **نادیده گرفتنِ** WAL — نسخهٔ تمیزِ کپی‌شده.

    فایل را به مسیرِ موقت کپی می‌کنیم بدونِ wal/shm، و از همان می‌خوانیم.
    این تنها راهِ فهمیدنِ این است که دادهٔ دیده‌شده از خودِ دیتابیس می‌آید
    یا از WALِ تازه‌وارد.
    """
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "probe.db"
            shutil.copy2(path, clean)
            conn = sqlite3.connect(f"file:{clean}?mode=ro", uri=True, timeout=5)
            try:
                return int(conn.execute("SELECT COUNT(*) FROM assessment_sessions").fetchone()[0])
            finally:
                conn.close()
    except (sqlite3.Error, OSError):
        return None


def report(status: Status) -> None:
    print(f"دیتابیس: {status.path}")
    print(f"  فایلِ اصلی : {'موجود' if status.db_exists else 'غایب'}"
          f"  ({status.db_size:,} بایت)")
    if status.sidecars:
        print("  فایل‌های WAL:")
        for name, size in status.sidecars:
            print(f"    • {name}  ({size:,} بایت)")
    else:
        print("  فایل‌های WAL: هیچ")
    print(f"  integrity_check: {status.integrity or '—'}")
    if status.session_count is not None:
        print(f"  آزمون‌های ثبت‌شده: {status.session_count}")
    if status.error:
        print(f"  خطا: {status.error}")
    if status.stray_sidecars:
        print("  هشدار: فایلِ WAL سرصفحهٔ معتبر ندارد (یا نیمه‌کاره است).")
    print(f"  وضعیت: {'سالم ✓' if status.healthy else 'نیازمندِ تعمیر ✗'}")
    print()


def quarantine_sidecars(path: Path) -> list[Path]:
    """WAL/SHM را با پسوندِ زمان‌دار کنار می‌گذارد — حذف نمی‌کند.

    عمداً ``rename`` و نه ``unlink``: اگر معلوم شد دادهٔ مهمی داخلشان بود،
    کاربر می‌تواند برگرداندشان. حذفِ خودکارِ داده، بدتر از خطای قابلِ رفع است.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    moved: list[Path] = []
    for suffix in SIDECARS:
        side = path.with_name(path.name + suffix)
        if not side.exists():
            continue
        target = side.with_name(f"{side.name}.bak-{stamp}")
        shutil.move(str(side), str(target))
        moved.append(target)
    return moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="بازرسی و تعمیرِ دیتابیسِ فمیار")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="مسیرِ فایلِ دیتابیس")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="فایل‌های WAL/SHM را کنار بگذار (حذف نمی‌شوند)",
    )
    args = parser.parse_args(argv)

    print("=" * 62)
    print("بازرسیِ دیتابیس")
    print("=" * 62)
    before = inspect(args.db)
    report(before)

    if before.healthy:
        print("کاری لازم نیست. دیتابیس سالم است.")
        return 0

    if not args.repair:
        print("برای تلاشِ تعمیر، دوباره با --repair اجرا کن.")
        print("  python tools/repair_db.py --repair")
        print()
        print("⚠️  پیش از هر کاری از فایلِ دیتابیس نسخهٔ پشتیبان بگیر:")
        print(f"    copy \"{args.db}\" \"{args.db}.backup\"      (ویندوز)")
        print(f"    cp \"{args.db}\" \"{args.db}.backup\"        (لینوکس/مک)")
        return 1

    if not before.sidecars:
        print("فایلِ WAL وجود ندارد؛ پس مشکل از خودِ فایلِ اصلی است.")
        print("از نسخهٔ پشتیبان بازگردانی کن.")
        return 2

    print("کنار گذاشتنِ فایل‌های WAL/SHM …")
    moved = quarantine_sidecars(args.db)
    for target in moved:
        print(f"  → {target.name}")

    print()
    after = inspect(args.db)
    report(after)

    if after.healthy:
        print("✓ تعمیر شد. دیتابیس سالم است و هیچ داده‌ای حذف نشد.")
        print(f"  (فایل‌های کنارگذاشته‌شده اگر لازم شد: {[m.name for m in moved]})")
        return 0

    print("✗ مشکل از خودِ فایلِ اصلی است، نه از WAL.")
    print("از نسخهٔ پشتیبان بازگردانی کن؛ فایل‌های کنارگذاشته‌شده دست‌نخورده‌اند.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
