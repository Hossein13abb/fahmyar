"""
سرورِ پیش‌نمایشِ بیلدِ تولیدی — دقیقاً مثلِ تجربهٔ کاربر.

چرا لازم است: کلاینتِ فرانت درخواست‌های نسبی می‌فرستد (``/api/...``). در
حالتِ توسعه، Vite آن‌ها را به بک‌اند پروکسی می‌کند. ولی اگر کسی
``dist`` را با یک سرورِ استاتیکِ ساده (مثلِ ``python -m http.server``)
سرو کند، دو اتفاقِ بد می‌افتد:

  ۱. ``/api/...`` با ۴۰۴ برمی‌گردد — و اگر آن سرور SPA-fallback داشته باشد،
     بجای ۴۰۴ یک صفحهٔ **HTML** با status 200 برمی‌گرداند.
  ۲. axios آن HTML را «داده» می‌بیند، ``report.exam`` تهی می‌شود، و اپ
     بی‌صدا به مسیرِ کارنامهٔ قدیمی می‌افتد.

یعنی UIِ تازه دقیقاً در همان محیطی که «کار نمی‌کند»، کار نمی‌کند — و هیچ
خطایی هم نشان نمی‌دهد. این اسکریپت آن محیط را درست بازسازی می‌کند تا
هر باگِ این‌جنس قبل از کاربر دیده شود.

اجرا:
    python3 tools/serve_dist.py --dist frontend/dist --port 8100 --api http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import http.server
import os
import posixpath
import socketserver
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

API_BASE = "http://127.0.0.1:8000"
DIST_ROOT = "."


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_ROOT, **kwargs)

    # ── پروکسیِ /api به بک‌اند ──────────────────────────────────────
    def _proxy(self, method: str) -> None:
        parsed = urlparse(self.path)
        target = API_BASE.rstrip("/") + parsed.path
        if parsed.query:
            target += "?" + parsed.query

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "accept-encoding")
        }
        req = urllib.request.Request(target, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    # Content-Length خودمان می‌نویسیم؛ تکرارش مرورگر را
                    # با «Duplicate Content-Length» رد می‌کند.
                    if key.lower() in (
                        "transfer-encoding",
                        "connection",
                        "content-encoding",
                        "content-length",
                    ):
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001
            message = f'{{"detail":"backend unreachable: {exc}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy("GET")
        path = self.translate_path(self.path)
        # SPA fallback — فقط برای مسیرهای بدونِ پسوند (نه برای /api)
        if not os.path.exists(path) and "." not in posixpath.basename(self.path):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy("POST")
        self.send_error(405)

    def do_PUT(self):
        if self.path.startswith("/api/"):
            return self._proxy("PUT")
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self._proxy("DELETE")
        self.send_error(405)

    def log_message(self, fmt, *args):  # کم‌نویسه، تا لاگِ تست شلوغ نشود
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


class ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    global API_BASE, DIST_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="frontend/dist")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    API_BASE = args.api
    DIST_ROOT = os.path.abspath(args.dist)
    if not os.path.isdir(DIST_ROOT):
        sys.exit(f"✗ dist پیدا نشد: {DIST_ROOT} — اول npm run build بزن.")

    with ThreadedServer(("0.0.0.0", args.port), Handler) as srv:
        print(f"→ dist: {DIST_ROOT}")
        print(f"→ api : {API_BASE}")
        print(f"→ http://0.0.0.0:{args.port}", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
