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
    """Raised when the browser is missing, the bundle is stale, or capture fails."""


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


def browser_available() -> bool:
    """True if Playwright and a Chromium build are usable on this host."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return bool(exe) and Path(exe).exists()
    except Exception:
        return False


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
    if not bundle_ready():
        raise CaptureError(
            "frontend bundle missing — run `npm run build` in frontend/ "
            f"(expected {DIST_DIR / PRINT_ENTRY})"
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        raise CaptureError(f"playwright is not installed: {exc}") from exc

    server, port = _start_server(DIST_DIR)
    try:
        if not _free_port_check(port):
            raise CaptureError("static server did not come up")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--font-render-hinting=none",
                    "--force-color-profile=srgb",
                    "--disable-lcd-text",
                ]
            )
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
