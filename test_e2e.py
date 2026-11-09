#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سرتاسری (End-to-End) سامانهٔ فهم‌یار — Fahmyar
====================================================

این اسکریپت کل چرخهٔ زندگی API را از صفر تا گزارش نهایی به‌صورت خودکار اجرا می‌کند:

  ۱) بررسی اتصال به سرور (GET /openapi.json یا /docs) با پیام خطای راهنما
  ۲) ثبت‌نام کاربر تستی (demo_test) — اگر از قبل وجود داشته باشد، به ورود fallback می‌کند
  ۳) ورود و دریافت JWT (کلید «token» یا «access_token» — هر دو پذیرفته می‌شوند)
  ۴) دریافت مفاهیم (GET /api/concepts/physics/11) و انتخاب اولین concept_id معتبر
  ۵) شروع جلسهٔ ارزیابی (POST /api/assess/start) با اسکیمای اصلاح‌شده:
        {"trigger_type": "topic_selection", "concept_id": <int>, "wrong_answer": null}
  ۶) ثبت پاسخِ غلطِ مفهومیِ عمدی و چاپ شواهدِ تحلیل‌شده + سؤال دنباله‌دار
  ۷) دریافت «گزارش نهایی» و راستی‌آزمایی ساختار کیفی آن (بدون نمره/رتبه/درصد)
  ۸) چاپ خلاصهٔ فارسی PASS/FAIL و خروج با کد ۰ (موفق) یا ۱ (ناموفق)

نحوهٔ اجرا (سرور باید در پس‌زمینه اجرا باشد):
    uvicorn main:app --reload
    python test_e2e.py

متغیرهای محیطی اختیاری:
    FAHMYAR_BASE_URL   (پیش‌فرض: http://127.0.0.1:8000)
    FAHMYAR_TIMEOUT    (پیش‌فرض: 30.0 ثانیه)

نکتهٔ مهم دربارهٔ رمز عبور:
    کاربر "123" خواسته شده بود، ولی نسخهٔ فعلی API رمز کوتاه‌تر از ۶ نویسه را
    (422 Unprocessable Entity) رد می‌کند. اسکریپت ابتدا «123» را امتحان می‌کند؛
    اگر سرور آن را رد کرد با رمز سازگار «demo_test123» ثبت‌نام می‌کند.
    در اجراهای بعدی (کاربر از قبل موجود است) با هرکدام از رمزها وارد می‌شود —
    یعنی اسکریپت روی هر دو نسخهٔ کد شما و این نسخه، پایدار و سبز است.

نکتهٔ اسکیمای پاسخ:
    اندپوینت پاسخ، بدنهٔ {"answer": "..."} را نمی‌پذیرد؛ اسکیمای واقعی
    {"question_id": <int>, "response_text": "<متن>"} است. question_id از پاسخِ
    start/answer گرفته می‌شود.
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
# طبق خواستهٔ کاربر اول «123» امتحان می‌شود؛ سپس رمز سازگار با validation فعلی
CANDIDATE_PASSWORDS = ["123", "demo_test123"]

WRONG_ANSWER = "چون ولتاژ زیاد شد مقاومت هم زیاد میشه"  # بدفهمیِ هدفمند: خلط ولتاژ با مقاومت

STATUS_FA = {
    "CONFIRMED": "تأییدشده",
    "LIKELY_UNDERSTOOD": "احتمالاً آموخته‌شده",
    "UNCLEAR": "نامشخص",
    "NEEDS_REVIEW": "بدفهمی شناسایی‌شده",
    "INSUFFICIENT_EVIDENCE": "فاقد شواهد کافی",
}
ALLOWED_STATUSES = set(STATUS_FA)
REPORT_MUST_CONTAIN = ["موضوع بررسی", "شواهد", "موارد هنوز روشن‌نشده", "پیشنهاد اقدام", "⚠️ نمرهٔ آزمون"]
# کلیدهای عددیِ ممنوع در ساختار گزارش (ساختار از آنِ ماست پس این بررسی قطعی است)
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
    """JWT را از پاسخ برمی‌دارد — هم token و هم access_token را می‌پذیرد."""
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
            r = client.get("/docs")  # fallback
        ok = r.status_code in (200, 307, 308)
        ui.info(f"پاسخ سرور → HTTP {r.status_code}")
        try:
            health = client.get("/api/health").json()
            ui.info(f"/api/health → {health}")
        except Exception:
            pass  # سلامت اصلی همین است که سرور پاسخ می‌دهد
        return record("اتصال به سرور", ok, f"{BASE_URL}")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        ui.info(f"❌ اتصال به {BASE_URL} برقرار نشد — احتمالاً سرور Uvicorn در پس‌زمینه اجرا نیست.")
        ui.info("   راه‌حل: در یک ترمینال جدا اجرا کنید:")
        ui.info("       uvicorn main:app --reload")
        ui.info(f"   سپس دوباره همین اسکریپت را اجرا کنید:  python test_e2e.py")
        ui.info(f"   (آدرس را می‌توانید با FAHMYAR_BASE_URL عوض کنید؛ مقدار فعلی: {BASE_URL})")
        return record("اتصال به سرور", False, "سرور در دسترس نیست")
    except httpx.TimeoutException:
        ui.info(f"❌ سرور در مهلت {TIMEOUT} ثانیه پاسخ نداد (پاسخ AI می‌تواند کند باشد — FAHMYAR_TIMEOUT را بالا ببرید).")
        return record("اتصال به سرور", False, "تایم‌اوت")
    except Exception as exc:
        return record("اتصال به سرور", False, f"خطای غیرمنتظره: {exc}")


def step_register_and_login(client: httpx.Client) -> str | None:
    ui.section("گام ۲ و ۳: ثبت‌نام (در صورت نیاز) و ورود")

    # --- ثبت‌نام: اول «123» طبق خواسته، سپس رمز سازگار ---
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
        ui.info(f"ثبت‌نام با رمز «{pw}» پذیرفته نشد → HTTP {r.status_code} | {data}")

    if registered_token:
        record("ثبت‌نام / ورود (demo_test)", True, "ثبت‌نام جدید موفق")
        return registered_token

    # --- ورود: رمزها را به ترتیب امتحان کن ---
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
        ui.info(f"ورود با رمز «{pw}» ناموفق → HTTP {r.status_code}")

    record("ثبت‌نام / ورود (demo_test)", False, "نه ثبت‌نام و نه ورود با هیچ‌کدام از رمزها موفق نبود")
    return None


def step_fetch_concepts(client: httpx.Client, token: str) -> int | None:
    ui.section("گام ۴: دریافت مفاهیم و انتخاب concept_id")
    concepts: list[dict[str, Any]] = []
    # مسیر اصلی طبق طراحی API
    r = client.get("/api/concepts/physics/11", headers=auth_headers(token))
    data = json_or_none(r) or {}
    concepts = data.get("concepts", []) if isinstance(data, dict) else []
    if r.status_code == 200 and concepts:
        ui.info(f"GET /api/concepts/physics/11 → {len(concepts)} مفهوم")
    else:
        ui.info(f"مسیر اصلی پاسخ نداد (HTTP {r.status_code}) — تلاش با /api/concepts …")
        r2 = client.get("/api/concepts", headers=auth_headers(token))
        data2 = json_or_none(r2) or {}
        concepts = data2.get("concepts", []) if isinstance(data2, dict) else []
        if r2.status_code == 200 and concepts:
            ui.info(f"GET /api/concepts → {len(concepts)} مفهوم")

    if not concepts:
        record("دریافت مفاهیم", False, "هیچ مفهومی برگردانده نشد (آیا seed اجرا شده؟)")
        return None

    # ترجیح با قانون اهم چون پاسخ غلطِ سناریو دربارهٔ همین مفهوم است؛ وگرنه اولین مورد
    chosen = next((c for c in concepts if c.get("topic") == "ohm_law"), concepts[0])
    ui.info(f"مفهوم انتخاب‌شده: [{chosen.get('id')}] {chosen.get('name')} ({chosen.get('subject')} — پایهٔ {chosen.get('grade')})")
    record("دریافت مفاهیم و انتخاب concept_id", True, f"concept_id={chosen.get('id')}")
    return int(chosen["id"])


def step_start_session(client: httpx.Client, token: str, concept_id: int) -> dict[str, Any] | None:
    ui.section("گام ۵: شروع جلسهٔ ارزیابی (مسیر A)")
    # اسکیمای اصلاح‌شده طبق مشخصات: concept_id عددی + wrong_answer صریحاً null
    payload = {"trigger_type": "topic_selection", "concept_id": concept_id, "wrong_answer": None}
    r = client.post("/api/assess/start", json=payload, headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code not in (200, 201):
        record("شروع جلسهٔ ارزیابی", False, f"HTTP {r.status_code} | {data}")
        return None

    session = data.get("session", {})
    question = data.get("next_question")
    ui.info(f"شناسهٔ جلسه: {session.get('id')} | وضعیت: {session.get('status')} | سقف زمان: {session.get('time_limit_seconds')} ثانیه")
    if question:
        ui.info(f"سؤالِ تشخیصیِ اول (نوع: {question.get('question_type')} | سختی: {question.get('difficulty')} | id={question.get('id')}):")
        ui.info(f"    «{question.get('text')}»")
    else:
        ui.info("⚠️ سؤالی برگردانده نشد.")
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

    ui.info("پاسخِ دانش‌آموز (غلطِ مفهومیِ عمدی):")
    ui.info(f"    «{WRONG_ANSWER}»")

    # اسکیمای واقعی اندپوینت: question_id + response_text (نه کلید «answer»)
    payload = {"question_id": question["id"], "response_text": WRONG_ANSWER}
    r = client.post(f"/api/assess/{session_id}/answer", json=payload, headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("ثبت پاسخ + تحلیل", False, f"HTTP {r.status_code} | {data}")
        return False

    # --- چاپ تحلیل AI ---
    for ev in data.get("evidence", []):
        status = ev.get("status", "?")
        status_fa = STATUS_FA.get(status, status)
        conf = ev.get("confidence")
        conf_txt = f"اطمینان={conf:.2f}" if isinstance(conf, (int, float)) else ""
        review = " | ⚠️ نیازمند بررسی معلم" if ev.get("needs_teacher_review") else ""
        ui.info(f"    • گزارهٔ «{str(ev.get('proposition_id'))[:70]}»")
        ui.info(f"        وضعیت: {status_fa} ({status}) | {conf_txt}{review}")
        ui.info(f"        دلیل تحلیل‌گر: {ev.get('reasoning', '')[:150]}")

    statuses = data.get("proposition_statuses") or {}
    if statuses:
        ui.info("    وضعیت گزاره‌ها پس از این پاسخ:")
        for prop, st in statuses.items():
            ui.info(f"        - {STATUS_FA.get(st, st):22s} | {str(prop)[:60]}")

    next_q = data.get("next_question")
    if next_q:
        ui.info("سؤالِ دنباله‌دارِ انطباقی:")
        ui.info(f"    [id={next_q.get('id')} | {next_q.get('question_type')}] «{next_q.get('text')}»")
    else:
        ui.info(f"جلسه پس از این پاسخ تعیین‌تکلیف شد (done={data.get('done')} | {data.get('message', '')})")

    detail = f"concept_status={data.get('concept_status')} | باقی‌مانده={data.get('remaining_seconds')}ثانیه"
    return record("ثبت پاسخ + تحلیل شواهد", True, detail)


def step_final_report(client: httpx.Client, token: str, session_id: int) -> bool:
    ui.section("گام ۷: دریافت و راستی‌آزمایی گزارش نهایی")
    r = client.get(f"/api/assess/{session_id}/report", headers=auth_headers(token))
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("گزارش نهایی", False, f"HTTP {r.status_code} | {data}")
        return False

    text = str(data.get("report_text", ""))
    sections = data.get("sections") or {}
    prop_statuses = data.get("proposition_statuses") or {}

    checks: list[tuple[bool, str]] = [
        (bool(text), "report_text غیرخالی است"),
        *[(needle in text, f"گزارش شامل «{needle}» است") for needle in REPORT_MUST_CONTAIN],
        (bool(sections.get("مشاهدات")), "بخش «مشاهدات» با ارجاع به پاسخ واقعی پر شده است"),
        (bool(sections.get("شواهد")), "بخش «شواهد» گزاره‌به‌گزاره پر شده است"),
        (all(v in ALLOWED_STATUSES for v in prop_statuses.values()),
         "همهٔ وضعیت‌ها یکی از ۵ وضعیتِ کیفیِ مجاز هستند (نه عدد)"),
        (not any(k in data for k in FORBIDDEN_REPORT_KEYS),
         "هیچ کلید عددیِ نمره/رتبه‌ای در ساختار گزارش نیست"),
        (not any(bad in text.lower() for bad in ["percentile", "رتبه"]),
         "هیچ «رتبه/percentile» در متن گزارش نیست"),
    ]
    all_ok = True
    for ok, label in checks:
        ui.sub_check(ok, label)
        all_ok = all_ok and ok

    ui.info(f"تعداد پاسخ‌های ثبت‌شده: {data.get('questions_answered')} (این «تعداد» است، نه «نمره»)")
    ui.info("─" * 58)
    for line in text.splitlines():
        if line.strip():
            ui.info(line)
    ui.info("─" * 58)
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
        failed = [f"گام {i} ({s})" for i, (s, ok, _) in enumerate(RESULTS, start=1) if not ok]
        print(ui.c(f"  ⚠️  {total - passed} گام از {total} ناموفق بود: {', '.join(failed)}", ui.RED, ui.BOLD))
    print(ui.c("  یادآوری: خروجی سامانه هیچ نمره/رتبه‌ای ندارد — فقط شواهد کیفی.", ui.DIM))
    print(flush=True)
    return 0 if passed == total else 1


# --------------------------------------------------------------------- main ---

def main() -> int:
    ui.banner("فهم‌یار — تست سرتاسری (E2E)")
    ui.info(f"آدرس سرور: {BASE_URL} | تایم‌اوت: {TIMEOUT} ثانیه")
    ui.info(f"کاربر تست: {DEMO_USERNAME}")

    # تایم‌اوت سخاوتمندانه (۳۰ ثانیه پیش‌فرض) تا پاسخ‌های واقعیِ AI قطع نشوند
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # گام ۱ — بدون سرور سالم ادامه نمی‌دهیم
        if not step_health(client):
            return print_summary()

        token = step_register_and_login(client)
        if not token:
            ui.info("بدون توکن JWT ادامهٔ تست ممکن نیست.")
            return print_summary()

        concept_id = step_fetch_concepts(client, token)
        if concept_id is None:
            return print_summary()

        session_data = step_start_session(client, token, concept_id)
        session_id: int | None = None
        if session_data:
            session_id = int(session_data["session"]["id"])
            step_submit_answer(client, token, session_data)
            step_final_report(client, token, session_id)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
