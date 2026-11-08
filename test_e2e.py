#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سرتاسری (End-to-End) سامانهٔ فهم‌یار — Fahmyar
====================================================
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

# ------------------------------------------------------------ پیکربندی کلی ---
BASE_URL = os.getenv("FAHMYAR_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = float(os.getenv("FAHMYAR_TIMEOUT", "30.0"))

DEMO_USERNAME = "demo_test"
DEMO_GRADE = 11
DEMO_MAJOR = "experimental"
CANDIDATE_PASSWORDS = ["123", "demo_test123"]

WRONG_ANSWER = "چون ولتاژ زیاد شد مقاومت هم زیاد میشه"  # بدفهمیِ هدفمند

STATUS_FA = {
    "CONFIRMED": "تأییدشده",
    "LIKELY_UNDERSTOOD": "احتمالاً آموخته‌شده",
    "UNCLEAR": "نامشخص",
    "NEEDS_REVIEW": "نیاز به بررسی",
    "INSUFFICIENT_EVIDENCE": "فاقد شواهد کافی",
}
ALLOWED_STATUSES = set(STATUS_FA)
REPORT_MUST_CONTAIN = ["موضوع بررسی", "شواهد", "موارد هنوز روشن‌نشده", "پیشنهاد اقدام", "⚠️ نمرهٔ آزمون"]
FORBIDDEN_REPORT_KEYS = ["score", "rank", "percentage", "percentile", "total_score", "grading"]

# --------------------------------------------------------------- کنسول -------

class Console:
    RESET, BOLD = "\033[0m", "\033[1m"
    GREEN, RED, CYAN, DIM = "\033[92m", "\033[91m", "\033[96m", "\033[2m"

    def __init__(self) -> None:
        self.color = sys.stdout.isatty()

    def c(self, text: str, *codes: str) -> str:
        return ("".join(codes) + text + self.RESET) if self.color else text

    def banner(self, title: str) -> None:
        line = "═" * 60
        print(self.c(line, self.CYAN, self.BOLD))
        print(self.c(f"  🧠  {title}", self.CYAN, self.BOLD))
        print(self.c(line, self.CYAN, self.BOLD), flush=True)

    def section(self, title: str) -> None:
        print()
        print(self.c(f"── {title} " + "─" * max(0, 56 - len(title)), self.BOLD), flush=True)

    def info(self, text: str) -> None:
        print(f"    {text}", flush=True)

    def sub_check(self, ok: bool, text: str) -> None:
        mark = self.c("✅", self.GREEN) if ok else self.c("❌", self.RED)
        print(f"      {mark} {text}", flush=True)


ui = Console()
RESULTS: list[tuple[str, bool, str]] = []


def record(step: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((step, ok, detail))
    mark = ui.c("✅ موفق", ui.GREEN, ui.BOLD) if ok else ui.c("❌ ناموفق", ui.RED, ui.BOLD)
    suffix = f"  — {detail}" if detail else ""
    print(f"  {mark}  {step}{suffix}", flush=True)
    return ok


def json_or_none(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def token_from(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    return (
        data.get("access_token")
        or data.get("token")
        or (data.get("data") or {}).get("access_token")
        or (data.get("data") or {}).get("token")
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ گام‌ها ---

def step_health(client: httpx.Client) -> bool:
    ui.section("گام ۱: بررسی اتصال به سرور")
    try:
        r = client.get("/openapi.json")
        if r.status_code != 200:
            r = client.get("/docs")
        ok = r.status_code in (200, 307, 308)
        ui.info(f"پاسخ سرور → HTTP {r.status_code}")
        try:
            health = client.get("/api/health").json()
            ui.info(f"/api/health → {health}")
        except Exception:
            pass
        return record("اتصال به سرور", ok, f"{BASE_URL}")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        ui.info(f"❌ اتصال به {BASE_URL} برقرار نشد — احتمالاً سرور Uvicorn در پس‌زمینه اجرا نیست.")
        return record("اتصال به سرور", False, "سرور در دسترس نیست")
    except httpx.TimeoutException:
        ui.info(f"❌ سرور در مهلت {TIMEOUT} ثانیه پاسخ نداد.")
        return record("اتصال به سرور", False, "تایم‌اوت")
    except Exception as exc:
        return record("اتصال به سرور", False, f"خطای غیرمنتظره: {exc}")


def step_register_and_login(client: httpx.Client) -> str | None:
    ui.section("گام ۲ و ۳: ثبت‌نام (در صورت نیاز) و ورود")

    registered_token = None
    for pw in CANDIDATE_PASSWORDS:
        payload = {
            "username": DEMO_USERNAME,
            "password": pw,
            "role": "student",
            "grade": DEMO_GRADE,
            "major": DEMO_MAJOR,
        }
        try:
            r = client.post("/api/auth/register", json=payload)
        except Exception as exc:
            ui.info(f"خطای شبکه در ثبت‌نام: {exc}")
            continue
        data = json_or_none(r) or {}
        if r.status_code in (200, 201):
            registered_token = token_from(data)
            ui.info(f"کاربر جدید «{DEMO_USERNAME}» ثبت شد (HTTP {r.status_code}).")
            break
        if r.status_code == 409:
            ui.info("این کاربر قبلاً ثبت شده است — ورود انجام می‌شود.")
            break

    if registered_token:
        record("ثبت‌نام / ورود (demo_test)", True, "ثبت‌نام جدید موفق")
        return registered_token

    for pw in CANDIDATE_PASSWORDS:
        try:
            r = client.post("/api/auth/login", json={"username": DEMO_USERNAME, "password": pw})
        except Exception as exc:
            ui.info(f"خطای شبکه در ورود: {exc}")
            continue
        data = json_or_none(r) or {}
        token = token_from(data)
        if r.status_code == 200 and token:
            role = (data.get("user") or {}).get("role", "student")
            record("ثبت‌نام / ورود (demo_test)", True, f"ورود موفق (نقش: {role})")
            return token

    record("ثبت‌نام / ورود (demo_test)", False, "ورود ناموفق بود")
    return None


def step_fetch_concepts(client: httpx.Client, token: str) -> int | None:
    ui.section("گام ۴: دریافت مفاهیم و انتخاب concept_id")
    concepts: list[dict[str, Any]] = []
    r = client.get("/api/concepts/physics/11", headers=auth_headers(token))
    data = json_or_none(r) or {}
    concepts = data.get("concepts", []) if isinstance(data, dict) else []
    if not concepts:
        r2 = client.get("/api/concepts", headers=auth_headers(token))
        data2 = json_or_none(r2) or {}
        concepts = data2.get("concepts", []) if isinstance(data2, dict) else []

    if not concepts:
        record("دریافت مفاهیم", False, "هیچ مفهومی برگردانده نشد")
        return None

    chosen = next((c for c in concepts if c.get("topic") == "ohm_law"), concepts[0])
    ui.info(f"مفهوم انتخاب‌شده: [{chosen.get('id')}] {chosen.get('name')}")
    record("دریافت مفاهیم و انتخاب concept_id", True, f"concept_id={chosen.get('id')}")
    return int(chosen["id"])


def step_start_session(client: httpx.Client, token: str, concept_id: int) -> dict[str, Any] | None:
    ui.section("گام ۵: شروع جلسهٔ ارزیابی (مسیر A)")
    payload = {"trigger_type": "topic_selection", "concept_id": concept_id, "wrong_answer": None}
    r = client.post("/api/assess/start", json=payload, headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code not in (200, 201):
        record("شروع جلسهٔ ارزیابی", False, f"HTTP {r.status_code} | {data}")
        return None

    session = data.get("session", {})
    question = data.get("next_question")
    ok = bool(session.get("id")) and bool(question)
    record("شروع جلسه + دریافت سؤال اول", ok, f"session_id={session.get('id')}")
    data["_question"] = question
    return data


def step_submit_answer(client: httpx.Client, token: str, session_data: dict[str, Any]) -> bool:
    ui.section("گام ۶: ثبت پاسخ غلطِ مفهومی و چاپ تحلیل AI")
    session_id = session_data["session"]["id"]
    question = session_data.get("_question")
    if not question:
        return record("ثبت پاسخ", False, "سؤالی برای پاسخ دادن وجود نداشت")

    payload = {"question_id": question["id"], "response_text": WRONG_ANSWER}
    r = client.post(f"/api/assess/{session_id}/answer", json=payload, headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("ثبت پاسخ + تحلیل", False, f"HTTP {r.status_code} | {data}")
        return False

    next_q = data.get("next_question")
    if next_q:
        ui.info(f"سؤالِ دنباله‌دار بعدی: «{next_q.get('text')}»")

    return record("ثبت پاسخ + تحلیل شواهد", True, f"session_id={session_id}")


def step_final_report(client: httpx.Client, token: str, session_id: int) -> bool:
    ui.section("گام ۷: دریافت و راستی‌آزمایی گزارش نهایی")
    r = client.get(f"/api/assess/{session_id}/report", headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("گزارش نهایی", False, f"HTTP {r.status_code} | {data}")
        return False

    text = str(data.get("report_text", ""))
    sections = data.get("sections") or {}

    checks: list[tuple[bool, str]] = [
        (bool(text), "report_text غیرخالی است"),
        *[(needle in text, f"گزارش شامل «{needle}» است") for needle in REPORT_MUST_CONTAIN],
        (not any(k in data for k in FORBIDDEN_REPORT_KEYS), "هیچ کلید عددیِ نمره/رتبه‌ای در ساختار گزارش نیست"),
    ]
    all_ok = True
    for ok, label in checks:
        ui.sub_check(ok, label)
        all_ok = all_ok and ok

    return record("گزارش نهایی (کیفی، بدون نمره/رتبه)", all_ok)


def print_summary() -> int:
    ui.section("گام ۸: خلاصهٔ نهایی")
    line = "═" * 60
    print(ui.c(line, ui.CYAN, ui.BOLD))
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for i, (step, ok, detail) in enumerate(RESULTS, start=1):
        mark = ui.c("✅ PASS", ui.GREEN, ui.BOLD) if ok else ui.c("❌ FAIL", ui.RED, ui.BOLD)
        detail_txt = f"  ({detail})" if detail else ""
        print(f"  {mark}  گام {i}: {step}{detail_txt}")
    print(ui.c(line, ui.CYAN, ui.BOLD))
    if passed == total:
        print(ui.c(f"  🎉 همهٔ {total} گام با موفقیت پاس شدند — سامانهٔ فهم‌یار سالم کار می‌کند.", ui.GREEN, ui.BOLD))
    else:
        print(ui.c(f"  ⚠️  {total - passed} گام از {total} ناموفق بود.", ui.RED, ui.BOLD))
    print(flush=True)
    return 0 if passed == total else 1


def main() -> int:
    ui.banner("فهم‌یار — تست سرتاسری (E2E)")
    ui.info(f"آدرس سرور: {BASE_URL} | تایم‌اوت: {TIMEOUT} ثانیه")

    # ⚠️ نکتهٔ مهم: trust_env=False برای دور زدن پروکسی/VPN روی 127.0.0.1
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, trust_env=False) as client:
        if not step_health(client):
            return print_summary()

        token = step_register_and_login(client)
        if not token:
            return print_summary()

        concept_id = step_fetch_concepts(client, token)
        if concept_id is None:
            return print_summary()

        session_data = step_start_session(client, token, concept_id)
        if session_data:
            session_id = int(session_data["session"]["id"])
            step_submit_answer(client, token, session_data)
            step_final_report(client, token, session_id)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())