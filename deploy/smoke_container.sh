#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# آزمون دودِ تصویر نهایی — روی کانتینر تازه، بدون هیچ نصب دستی.
#
# این اسکریپت همان چیزی را می‌سنجد که در تحویل ادعا شده: Chromium داخل تصویر
# اجرا می‌شود، باندل فرانت‌اند بارگذاری می‌شود، و Endpoint واقعی یک PDF معتبر
# برمی‌گرداند. اگر خروجی صفر نبود، تصویر سالم است.
#
#   ./deploy/smoke_container.sh [image] [port]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

IMAGE="${1:-fahmyar:latest}"
PORT="${2:-8055}"
NAME="fahmyar-smoke-$$"
PASSWORD="smoke-pass-123"
USER_NAME="smoke_teacher"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "── ۱. اجرای تصویر ─────────────────────────────────────────────"
docker run -d --name "$NAME" --network host -e AI_PROVIDER=mock \
  "$IMAGE" uvicorn main:app --host 127.0.0.1 --port "$PORT" >/dev/null

for _ in $(seq 1 40); do
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS -m 5 "http://127.0.0.1:$PORT/api/health" >/dev/null
echo "  ✓ سرویس پاسخ می‌دهد"

echo "── ۲. تأیید سلامت موتور PDF داخل کانتینر ──────────────────────"
docker exec "$NAME" python /app/deploy/verify_runtime.py | sed 's/^/  /'

echo "── ۳. تولید PDF از Endpoint واقعی ─────────────────────────────"
python3 - "$PORT" "$USER_NAME" "$PASSWORD" <<'PY'
import json
import sys
import httpx

port, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"http://127.0.0.1:{port}"

with httpx.Client(timeout=180) as client:
    r = client.post(f"{base}/api/auth/register",
                    json={"username": user, "password": password, "role": "teacher"})
    if r.status_code not in (200, 201):
        r = client.post(f"{base}/api/auth/login",
                        json={"username": user, "password": password})
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise SystemExit(f"ورود ناموفق: {r.status_code} {r.text[:200]}")

    q = {
        "text": r"اگر $A=\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}$ باشد، "
                r"حاصل $\frac{\sqrt{۱۴}}{۷}$ کدام است؟",
        "options": ["$۱$", "$۲$", "$۳$", "$۴$"],
        "correct_answer": 1,
        "explanation": r"با $\sqrt{۱۴}$ ساده می‌شود.",
        "difficulty": "متوسط",
        "subject": "ریاضی",
        "diagram_svg": None,
    }
    body = {
        "school_name": "دبیرستان آزمون دود",
        "title": "آزمون دود استقرار",
        "questions": [q, {**q, "text": "Which option is correct?"}],
        "duration_minutes": 30,
        "difficulty": "متوسط",
        "grade": "12",
        "major": "ریاضی",
        "subject_label": "ریاضی",
        "topic": "دود",
    }
    r = client.post(f"{base}/api/teacher/generate-exam-pdf", json=body,
                    headers={"Authorization": f"Bearer {token}"})

if r.status_code != 200:
    raise SystemExit(f"خطا {r.status_code}: {r.text[:400]}")
if not r.headers.get("content-type", "").startswith("application/pdf"):
    raise SystemExit("content-type اشتباه است")
if "attachment" not in r.headers.get("content-disposition", ""):
    raise SystemExit("هدر دانلود نیست")

payload = r.content
if payload[:5] != b"%PDF-":
    raise SystemExit("خروجی PDF معتبر نیست")

with open("/tmp/smoke-exam.pdf", "wb") as fh:
    fh.write(payload)
print(f"  ✓ HTTP 200 · {len(payload):,} بایت · {r.headers.get('x-exam-total-questions')} سؤال")
PY

echo "── ۴. بازرسی PDF ──────────────────────────────────────────────"
# فایل روی میزبان نوشته شد، پس همان‌جا بررسی می‌شود
python3 - <<'PY' | sed 's/^/  /'
import pymupdf

doc = pymupdf.open("/tmp/smoke-exam.pdf")
assert doc.page_count >= 2, "کمتر از دو صفحه"
imgs = sum(len(p.get_images()) for p in doc)
for page in doc:
    w, h = page.rect.width, page.rect.height
    assert abs(w - 595.28) < 1 and abs(h - 841.89) < 1, f"اندازهٔ صفحه A4 نیست: {w}x{h}"
print(f"  ✓ {doc.page_count} صفحه A4، {imgs} تصویر")
doc.close()
PY

echo "── نتیجه: تصویر سالم است ──────────────────────────────────────"
