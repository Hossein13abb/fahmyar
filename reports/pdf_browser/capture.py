# -*- coding: utf-8 -*-
"""Headless-Chromium capture of the exam document.

The page rendered here is ``frontend/dist/print.html`` — the project's own React
print entry point, built by Vite.  It composes the exam with the *same*
components the on-screen preview uses (notably ``MathText``, which carries the
LaTeX-repair pipeline).  This module therefore never builds markup: it serves
the built bundle, injects the exam data, waits for a real readiness signal, and
photographs each A4 sheet.

Serving over ``http://127.0.0.1:<port>`` rather than ``file://`` is deliberate.
The bundle is an ES module with absolute asset paths (``/assets/…``), so a
``file://`` origin would break both the module graph and the KaTeX fonts.
"""
from __future__ import annotations

import functools
import http.server
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "CapturedPage",
    "CaptureResult",
    "CaptureError",
    "capture_exam",
    "browser_available",
    "DIST_DIR",
    "PRINT_ENTRY",
]

BASE_DIR = Path(__file__).resolve().parent.parent.parent
#: Vite's build output.  ``npm run build`` writes both the app and the print
#: entry point here.
DIST_DIR = BASE_DIR / "frontend" / "dist"
PRINT_ENTRY = "print.html"

#: 2x of CSS pixels ≈ 192 dpi: comfortably above the 150 dpi usually quoted as
#: the floor for sharp text in print.
DEVICE_SCALE = 2.0

#: A4 at 96 dpi (the CSS reference resolution)
A4_H = 1123


class CaptureError(RuntimeError):
    """Raised when the browser is missing, the bundle is stale, or capture fails.

    ``reason`` lets the API layer produce a message an operator can act on
    instead of a stack trace.  Two reasons are distinguished because they need
    different fixes:

    ``bundle_missing``  the Vite build never ran        → run `npm run build`
    ``chromium_missing`` the browser binary is absent   → run `playwright install`
    """

    def __init__(self, message: str, reason: str = "capture_failed") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class CapturedPage:
    """One rendered sheet."""

    png: bytes
    width_px: int
    height_px: int


@dataclass
class CaptureResult:
    pages: List[CapturedPage]
    scale: float = DEVICE_SCALE
    #: sheets taller than A4 by more than 1 %; non-empty means the paginator
    #: misjudged a block and that sheet will be scaled down to fit
    overflow: List[int] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_bytes(self) -> int:
        return sum(len(p.png) for p in self.pages)


def bundle_ready() -> bool:
    """True if a built print entry point is present."""
    return (DIST_DIR / PRINT_ENTRY).is_file() and (DIST_DIR / "assets").is_dir()


def bundle_diagnosis() -> str:
    """Explain *why* the bundle is unusable, in terms an operator can act on.

    Returns an empty string when the bundle is fine.  The text is surfaced
    verbatim in the API error, so it names the exact missing path.
    """
    entry = DIST_DIR / PRINT_ENTRY
    assets = DIST_DIR / "assets"
    if entry.is_file() and assets.is_dir():
        return ""

    missing = []
    if not entry.is_file():
        missing.append(f"«{entry}»")
    if not assets.is_dir():
        missing.append(f"«{assets}»")

    return (
        "باندل فرانت‌اند (که موتور تولید PDF آن را در مرورگر بارگذاری می‌کند) "
        f"یافت نشد: {', '.join(missing)}. "
        "این باندل با اجرای «npm run build» در پوشهٔ frontend تولید می‌شود و "
        "باید در مسیر frontend/dist قرار بگیرد. در استقرار کانتینری، مرحلهٔ "
        "frontend-build در Dockerfile این کار را انجام می‌دهد؛ اگر سرویس را "
        "مستقیم اجرا می‌کنید، یک‌بار دستی build کنید."
    )


def browser_available() -> bool:
    """True if the playwright package and a Chromium build are both usable."""
    return check_prerequisites()["ok"]


def check_prerequisites() -> dict:
    """Report every precondition of the PDF engine at once.

    A user fixing one missing piece at a time gets one obscure error after
    another.  This returns the whole picture so a single message can list
    everything that is wrong and the exact command that fixes each part.

    Keys: ``ok`` (bool) and ``problems`` (list of dicts with ``code``,
    ``message`` and ``fix``).
    """
    problems: list[dict] = []

    # 1. the built frontend bundle
    diagnosis = bundle_diagnosis()
    if diagnosis:
        problems.append(
            {
                "code": "bundle_missing",
                "message": diagnosis,
                "fix": "cd frontend && npm install && npm run build",
            }
        )

    # 2. the playwright package
    try:
        from importlib.metadata import version as _pkg_version

        _pkg_version("playwright")
        have_pkg = True
    except Exception:
        have_pkg = False

    if not have_pkg:
        problems.append(
            {
                "code": "playwright_missing",
                "message": (
                    "پکیج playwright نصب نیست؛ موتور تولید PDF با مرورگر کار می‌کند."
                ),
                "fix": "pip install -r requirements.txt",
            }
        )
    else:
        # 3. the browser binary (only meaningful if the package is present)
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                exe = p.chromium.executable_path
            have_browser = bool(exe) and Path(exe).exists()
        except Exception:
            have_browser = False

        if not have_browser:
            problems.append(
                {
                    "code": "chromium_missing",
                    "message": (
                        "باینری Chromium نصب نیست. پکیج playwright تنها کد "
                        "پایتون است؛ مرورگر جداگانه دانلود می‌شود."
                    ),
                    "fix": "python -m playwright install chromium",
                }
            )

    return {"ok": not problems, "problems": problems}


# ---------------------------------------------------------------------------
# a tiny static server for the built bundle
# ---------------------------------------------------------------------------

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler without the stderr chatter."""

    def log_message(self, fmt, *args):  # noqa: D102 - silence
        pass


def _start_server(directory: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    """Serve ``directory`` on a free loopback port; return (server, port)."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _free_port_check(port: int, timeout: float = 5.0) -> bool:
    """Wait until the port accepts connections."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

def capture_exam(
    exam: Dict[str, Any],
    *,
    scale: float = DEVICE_SCALE,
    timeout_ms: int = 45_000,
) -> CaptureResult:
    """Render the exam through the React print entry and return one PNG per A4 sheet.

    ``exam`` is JSON-serialisable and becomes ``window.__EXAM__`` in the page.
    """
    diagnosis = bundle_diagnosis()
    if diagnosis:
        raise CaptureError(diagnosis, reason="bundle_missing")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        raise CaptureError(
            "موتور رندر مرورگری در این نصب موجود نیست (پکیج playwright). "
            "«pip install -r requirements.txt» و سپس "
            "«python -m playwright install chromium» را اجرا کنید.",
            reason="chromium_missing",
        ) from exc

    server, port = _start_server(DIST_DIR)
    try:
        if not _free_port_check(port):
            raise CaptureError("static server did not come up")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--font-render-hinting=none",
                        "--force-color-profile=srgb",
                        "--disable-lcd-text",
                    ]
                )
            except Exception as exc:
                raise CaptureError(
                    _launch_error_message(exc), reason="chromium_missing"
                ) from exc
            try:
                ctx = browser.new_context(
                    viewport={"width": 794, "height": A4_H},
                    device_scale_factor=scale,
                    java_script_enabled=True,
                )
                # inject the data before any page script runs
                ctx.add_init_script(
                    "window.__EXAM__ = %s;" % _js_json(exam)
                )
                page = ctx.new_page()
                page.set_default_timeout(timeout_ms)

                errors: List[str] = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))

                page.goto(f"http://127.0.0.1:{port}/{PRINT_ENTRY}", wait_until="load")

                # The page exposes a promise-based readiness hook: fonts + images
                # + pagination.  Polling a boolean is not enough because the hook
                # is async; use the returned promise.
                page.evaluate(
                    "() => (window.__readyForCapture "
                    "? window.__readyForCapture() : Promise.resolve(0))"
                )
                page.wait_for_function(
                    "() => document.querySelectorAll('.page').length > 0",
                    timeout=timeout_ms,
                )

                if errors:
                    raise CaptureError("page raised: " + " | ".join(errors[:3]))

                # grow the viewport so every sheet is inside the render surface
                full_h = page.evaluate(
                    "() => Math.max(document.body.scrollHeight,"
                    " document.documentElement.scrollHeight, 1123)"
                )
                page.set_viewport_size({"width": 794, "height": int(full_h) + 8})
                page.wait_for_timeout(120)   # one layout pass at the new size

                pages = _shoot(page)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    if not pages:
        raise CaptureError("no sheets were produced")

    overflow = [
        i + 1 for i, pg in enumerate(pages) if pg.height_px > A4_H * scale * 1.01
    ]
    return CaptureResult(pages=pages, scale=scale, overflow=overflow)


def _launch_error_message(exc: Exception) -> str:
    """Turn a Chromium launch failure into an operator-readable sentence."""
    text = str(exc)
    if "shared libraries" in text or "cannot open shared object" in text:
        return (
            "مرورگر Chromium نصب است اما اجرا نشد، چون کتابخانه‌های سیستمیِ "
            "لازم موجود نیستند. این کتابخانه‌ها با pip نصب نمی‌شوند و باید در "
            "تصویر سیستم‌عامل باشند — Dockerfile این پروژه آن‌ها را نصب می‌کند "
            "(libnspr4، libnss3، libatk-1.0، libgbm1، libpango، libcairo و…). "
            f"پیام اصلی: {text.splitlines()[0][:200] if text else 'نامشخص'}"
        )
    if "Executable doesn't exist" in text:
        return (
            "باینری Chromium نصب نشده است. «python -m playwright install "
            "chromium» را اجرا کنید."
        )
    return f"راه‌اندازی Chromium شکست خورد: {text.splitlines()[0][:300] if text else exc}"


def _js_json(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)


def _shoot(page) -> List[CapturedPage]:
    """Photograph each paginated A4 sheet.

    No slicing happens here.  Slicing a long container mechanically is exactly
    what cut questions in half in the first prototype; the page's own paginator
    produces correct A4 boundaries, so we take whole sheets.
    """
    sheets = page.query_selector_all("div.page")
    out: List[CapturedPage] = []
    for sheet in sheets:
        box = sheet.bounding_box()
        if not box or box["height"] < 10:
            continue
        png = page.screenshot(
            clip={
                "x": box["x"],
                "y": box["y"],
                "width": box["width"],
                "height": box["height"],
            },
            type="png",
            scale="device",
        )
        out.append(
            CapturedPage(
                png=png,
                width_px=int(round(box["width"] * DEVICE_SCALE)),
                height_px=int(round(box["height"] * DEVICE_SCALE)),
            )
        )
    return out
