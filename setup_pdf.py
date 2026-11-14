# -*- coding: utf-8 -*-
"""بررسی و آماده‌سازی موتور تولید PDF.

موتور PDF آزمون سه پیش‌نیاز دارد که هیچ‌کدام با «pip install» تنها تأمین
نمی‌شود:

1. باندلِ ساخته‌شدهٔ فرانت‌اند  (frontend/dist)  — چون سند در مرورگر رندر می‌شود
2. پکیج playwright                                — لایهٔ کنترل مرورگر
3. باینری Chromium                                — مرورگری که واقعاً رندر می‌کند

این اسکریپت وضعیت هر سه را گزارش می‌کند و با `--fix` هر کدام را می‌سازد.
روی ویندوز و لینوکس و مک کار می‌کند.

    python setup_pdf.py          # فقط گزارش
    python setup_pdf.py --fix    # ساخت هر چیزی که نیست
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST_ENTRY = FRONTEND / "dist" / "print.html"
DIST_ASSETS = FRONTEND / "dist" / "assets"

OK = "\033[32m✓\033[0m" if sys.platform != "win32" else "[OK]"
NO = "\033[31m✗\033[0m" if sys.platform != "win32" else "[--]"


def _run(cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a command, streaming its output; return success."""
    print(f"    $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
        return result.returncode == 0
    except FileNotFoundError:
        print(f"    ! دستور پیدا نشد: {cmd[0]}")
        return False


def check_bundle() -> tuple[bool, str]:
    if DIST_ENTRY.is_file() and DIST_ASSETS.is_dir():
        return True, "باندل فرانت‌اند ساخته شده است"
    missing = []
    if not DIST_ENTRY.is_file():
        missing.append("print.html")
    if not DIST_ASSETS.is_dir():
        missing.append("assets/")
    return False, f"باندل فرانت‌اند نیست ({'، '.join(missing)})"


def check_playwright() -> tuple[bool, str]:
    try:
        from importlib.metadata import version

        return True, f"playwright {version('playwright')}"
    except Exception:
        return False, "پکیج playwright نصب نیست"


def check_chromium() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False, "برای بررسی Chromium اول باید playwright نصب شود"
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and Path(exe).exists():
            return True, f"Chromium موجود است: {exe}"
        return False, "باینری Chromium نصب نیست"
    except Exception as exc:
        return False, f"Chromium قابل استفاده نیست: {str(exc)[:120]}"


def fix_bundle() -> bool:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("    ! npm پیدا نشد. Node.js را نصب کنید: https://nodejs.org")
        return False
    node_modules = FRONTEND / "node_modules"
    if not node_modules.is_dir():
        if not _run([npm, "install"], cwd=FRONTEND):
            return False
    return _run([npm, "run", "build"], cwd=FRONTEND)


def fix_playwright() -> bool:
    return _run([sys.executable, "-m", "pip", "install", "playwright"])


def fix_chromium() -> bool:
    # روی لینوکس اگر کتابخانه‌های سیستمی نباشند، این دستور با
    # «error while loading shared libraries» شکست می‌خورد؛ --with-deps
    # روی توزیع‌های Debian/Ubuntu آن‌ها را هم نصب می‌کند.
    ok = _run([sys.executable, "-m", "playwright", "install", "chromium"])
    if not ok and sys.platform.startswith("linux"):
        print("    تلاش دوباره همراه با وابستگی‌های سیستمی (نیازمند sudo)…")
        ok = _run(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
        )
    return ok


def main() -> int:
    do_fix = "--fix" in sys.argv

    print("\n── آماده‌سازی موتور PDF ────────────────────────────────────\n")

    checks = [
        ("باندل فرانت‌اند", check_bundle, fix_bundle),
        ("پکیج playwright", check_playwright, fix_playwright),
        ("باینری Chromium", check_chromium, fix_chromium),
    ]

    results = []
    for name, check, fixer in checks:
        ok, detail = check()
        print(f"  {OK if ok else NO}  {name}: {detail}")
        results.append((name, ok, fixer))

    if any(not ok for _, ok, _ in results):
        if not do_fix:
            print("\n  برای ساخت موارد بالا:  python setup_pdf.py --fix\n")
            return 1

        print("\n── در حال ساخت ────────────────────────────────────────────\n")
        for name, ok, fixer in results:
            if ok:
                continue
            print(f"  → {name}")
            if not fixer():
                print(f"  {NO} {name} ساخته نشد\n")
                return 1
            print(f"  {OK} {name}\n")

        # re-check after fixing
        print("── بررسی دوباره ───────────────────────────────────────────\n")
        all_ok = True
        for name, check, _ in checks:
            ok, detail = check()
            print(f"  {OK if ok else NO}  {name}: {detail}")
            all_ok &= ok
        if not all_ok:
            return 1

    print("\n── آماده است. دکمهٔ PDF حالا کار می‌کند. ────────────────────\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
