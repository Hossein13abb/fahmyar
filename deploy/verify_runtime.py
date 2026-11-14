# -*- coding: utf-8 -*-
"""نصب‌پذیری تصویر را در زمان build تأیید می‌کند.

اجرای این اسکریپت در Dockerfile سه چیز را ثابت می‌کند:

1. Playwright و باینری Chromium حاضرند و **اجرا می‌شوند** — نه فقط نصب.
2. باندل فرانت‌اند ساخته شده و ورودی چاپ (``print.html``) در آن هست.
3. فونت Vazirmatn همراه باندل است، پس رندر فارسی به فونت سیستم وابسته نیست.

اگر هر کدام نبود، build شکست می‌خورد — بهتر از آن است که اولین درخواست
کاربر با ۵۰۳ مواجه شود.
"""
from __future__ import annotations

import sys
from pathlib import Path

MIN_CHROMIUM_MAJOR = 100


def fail(message: str) -> None:
    print(f"  ✗ {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    print("── verify_runtime ─────────────────────────────────────────────")

    # ۱. باندل فرانت‌اند
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    print_entry = dist / "print.html"
    if not print_entry.is_file():
        fail(f"ورودی چاپ پیدا نشد: {print_entry} — مرحلهٔ frontend-build اجرا نشده؟")
    assets = list((dist / "assets").glob("*.js"))
    if not assets:
        fail(f"هیچ فایل جاوااسکریپتی در {dist / 'assets'} نیست")
    print(f"  ✓ باندل فرانت‌اند: {len(assets)} فایل js، print.html موجود")

    fonts = list(dist.rglob("Vazirmatn-*.ttf"))
    if not fonts:
        fail("فونت Vazirmatn در باندل نیست — رندر فارسی بی‌سرویس می‌ماند")
    print(f"  ✓ فونت‌ها: {', '.join(sorted(f.name for f in fonts))}")

    # ۲. پکیج پایتون
    try:
        from importlib.metadata import version as pkg_version

        pw_version = pkg_version("playwright")
    except Exception as exc:  # pragma: no cover
        fail(f"playwright نصب نیست: {exc}")
    print(f"  ✓ playwright {pw_version}")

    # ۳. باینری و اجرای واقعی
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        fail(f"import playwright.sync_api شکست خورد: {exc}")

    with sync_playwright() as p:
        exe = p.chromium.executable_path
        if not exe or not Path(exe).exists():
            fail(
                "باینری Chromium پیدا نشد — `python -m playwright install chromium` "
                "در تصویر اجرا نشده است"
            )
        print(f"  ✓ باینری: {exe}")

        try:
            browser = p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        except Exception as exc:
            fail(
                "Chromium اجرا نشد. اگر پیام «error while loading shared "
                f"libraries» بود، کتابخانهٔ سیستمی جا افتاده است: {exc}"
            )

        try:
            info = browser.version
            major = int("".join(ch for ch in info.split(".")[0] if ch.isdigit()) or 0)
            if major < MIN_CHROMIUM_MAJOR:
                fail(f"نسخهٔ Chromium قدیمی است: {info}")
            print(f"  ✓ Chromium {info}")

            page = browser.new_page(viewport={"width": 400, "height": 300})
            page.set_content(
                "<html><body style='font-family:sans-serif'>"
                "<p>سلام — render OK</p></body></html>"
            )
            shot = page.screenshot(type="png")
            if len(shot) < 500:
                fail("اسکرین‌شات آزمایشی خالی بود")
            print(f"  ✓ رندر و اسکرین‌شات: {len(shot)} بایت PNG")
        finally:
            browser.close()

    # ۴. فونت فارسی در همان مسیرهایی که CSS انتظار دارد
    css_font = dist / "print-fonts"
    if not css_font.is_dir() or not list(css_font.glob("*.ttf")):
        fail("پوشهٔ print-fonts در باندل نیست")

    print("── همهٔ بررسی‌ها موفق ─────────────────────────────────────────")


if __name__ == "__main__":
    main()
