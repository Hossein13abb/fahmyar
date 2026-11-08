#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سرتاسری (End-to-End) سامانهٔ فهم‌یار — Fahmyar
====================================================

کل چرخهٔ زندگی API را از صفر تا گزارش نهایی خودکار می‌کند:

  ۱) بررسی سلامت سرور روی http://localhost:8000
  ۲) ثبت‌نام دانش‌آموزِ تستی (demo_student) + ورود و دریافت JWT
     (اگر قبلاً ثبت شده باشد، خودکار به حالت ورود fallback می‌کند)
  ۳) دریافت فهرست مفاهیم و انتخاب خودکار یک concept_id معتبر
     (ترجیحاً «قانون اهم» چون پاسخ غلطِ سناریو دربارهٔ همین است؛ وگرنه اولین مفهوم)
  ۴) شروع جلسهٔ ارزیابی — مسیر A (انتخاب موضوع) و چاپ سؤال اول
  ۵) ثبت یک پاسخ غلطِ مفهومی (بدفهمی هدفمند) + چاپ شواهد تحلیل‌شده
     سپس یک پاسخ اصلاحی/تکمیلی + چاپ شواهد و سؤال بعدی
  ۶) دریافت «گزارش نهایی» و راستی‌آزمایی ساختار آن:
     مشاهدات، وضعیت‌های کیفی (CONFIRMED/UNCLEAR/NEEDS_REVIEW…)، پیشنهاد اقدام،
     و **عدمِ وجود هرگونه نمره/رتبه/درصد**
  ۷) شروع جلسهٔ دوم — مسیر B (پاسخ غلط) و راستی‌آزمایی ساختِ فرضیه‌های ریشهٔ خطا (بین‌درسی)
  ۸) چاپ خلاصهٔ فارسیِ PASS/FAIL برای هر گام + خروج با کد ۰ یا ۱

نحوهٔ اجرا:
    python test_e2e.py

متغیرهای محیطی اختیاری:
    FAHMYAR_BASE_URL   (پیش‌فرض: http://localhost:8000)

نیازمندی: httpx (در requirements.txt موجود است) و سرور در حال اجرا:
    uvicorn main:app --reload
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

BASE_URL = os.getenv("FAHMYAR_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_SECONDS = 60.0  # فراخوانی واقعیِ Gemini ممکن است چند ثانیه طول بکشد

DEMO_USERNAME = "demo_student"
DEMO_PASSWORD = "demo_student123"  # حداقل ۶ نویسه
DEMO_FULL_NAME = "دانش‌آموز دموی تست"
WRONG_RESPONSE = "چون ولتاژ دو برابر شده مقاومت هم دو برابر میشه"  # بدفهمیِ هدفمند: خلط ولتاژ و مقاومت
CLARIFYING_RESPONSE = (
    "چون قانون اهم میگه I برابر V تقسیم بر R هست؛ جریان با ولتاژ نسبت مستقیم داره و با مقاومت "
    "نسبت عکس. مقاومت ویژگی خودِ رسانا (طول، سطح مقطع، جنس) هست و به ولتاژِ اعمالی بستگی نداره. "
    "بنابراین وقتی ولتاژ دو برابر بشه و مقاومت ثابت بمونه، جریان دو برابر میشه نه اینکه مقاومت تغییر کنه."
)

# برچسب‌های فارسیِ وضعیت‌های کیفی
STATUS_FA = {
    "CONFIRMED": "تأییدشده",
    "LIKELY_UNDERSTOOD": "احتمالاً آموخته‌شده",
    "UNCLEAR": "نامشخص",
    "NEEDS_REVIEW": "نیاز به بررسی",
    "INSUFFICIENT_EVIDENCE": "فاقد شواهد کافی",
}
ALLOWED_STATUSES = set(STATUS_FA)
# واژه‌هایی که هرگز نباید در متن گزارش باشند (نه نمره، نه رتبه، نه درس مقایسه)
FORBIDDEN_IN_REPORT = ["رتبه", "درصد", "percentile", "rank", "score", "%"]

# ---------------------------------------------------------------- ابزارها ---

class Console:
    """چاپ رنگی/قالب‌بندی‌شدهٔ فارسی (اگر ترمینال پشتیبانی کند)."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    DIM = "\033[2m"

    def __init__(self) -> None:
        self.color = sys.stdout.isatty()

    def c(self, text: str, *codes: str) -> str:
        if not self.color:
            return text
        return "".join(codes) + text + self.RESET

    def banner(self, title: str) -> None:
        line = "═" * 60
        print(self.c(line, self.CYAN, self.BOLD))
        print(self.c(f"  🧠  {title}", self.CYAN, self.BOLD))
        print(self.c(line, self.CYAN, self.BOLD), flush=True)

    def section(self, title: str) -> None:
        print()
        print(self.c(f"── {title} " + "─" * max(0, 54 - len(title)), self.BOLD), flush=True)

    def info(self, text: str) -> None:
        print(f"    {text}", flush=True)

    def sub_check(self, ok: bool, text: str) -> None:
        mark = self.c("✅", self.GREEN) if ok else self.c("❌", self.RED)
        print(f"      {mark} {text}", flush=True)


ui = Console()

# نتیجهٔ هر گام: (نام گام، موفق؟، جزئیات)
RESULTS: list[tuple[str, bool, str]] = []


def record(step: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((step, ok, detail))
    mark = ui.c("✅ موفق", ui.GREEN, ui.BOLD) if ok else ui.c("❌ ناموفق", ui.RED, ui.BOLD)
    suffix = f"  — {detail}" if detail else ""
    print(f"  {mark}  {step}{suffix}", flush=True)
    return ok


def api(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    """فراخوانی یکپارچه با مدیریت خطای شبکه."""
    return client.request(method, path, **kwargs)


def json_or_none(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def token_from(data: dict[str, Any]) -> str | None:
    """JWT را از پاسخ برمی‌دارد — هم کلید token و هم access_token را می‌پذیرد."""
    if not isinstance(data, dict):
        return None
    return data.get("token") or data.get("access_token") or (data.get("data") or {}).get("token")


# ------------------------------------------------------------------ گام‌ها ---

def step_health(client: httpx.Client) -> bool:
    ui.section("گام ۱: بررسی سلامت و اتصال به سرور")
    try:
        r = api(client, "GET", "/api/health")
    except httpx.ConnectError:
        ui.info(f"اتصال به {BASE_URL} برقرار نشد.")
        ui.info("ابتدا سرور را اجرا کنید:  uvicorn main:app --reload")
        return record("سلامت سرور", False, f"سرور در {BASE_URL} در دسترس نیست")
    except Exception as exc:
        return record("سلامت سرور", False, f"خطای غیرمنتظره: {exc}")

    data = json_or_none(r) or {}
    ok = r.status_code == 200
    ui.info(f"پاسخ /api/health → HTTP {r.status_code} | {data}")
    return record("سلامت سرور", ok, f"وضعیت={data.get('status')} | پروایدر AI={data.get('ai_provider')}")


def step_auth(client: httpx.Client) -> str | None:
    ui.section("گام ۲: ثبت‌نام / ورود دانش‌آموز")

    payload = {
        "username": DEMO_USERNAME,
        "password": DEMO_PASSWORD,
        "role": "student",
        "grade": 11,
        "major": "experimental",
        "full_name": DEMO_FULL_NAME,
    }
    r = api(client, "POST", "/api/auth/register", json=payload)
    data = json_or_none(r) or {}

    if r.status_code in (200, 201):
        token = token_from(data)
        ui.info(f"کاربر جدید «{DEMO_USERNAME}» ثبت شد.")
        record("ثبت‌نام / ورود دانش‌آموز", bool(token), f"HTTP {r.status_code} (ثبت‌نام جدید)")
        return token

    if r.status_code != 409:
        record("ثبت‌نام / ورود دانش‌آموز", False, f"HTTP {r.status_code} | {data}")
        return None

    ui.info("این کاربر قبلاً ثبت شده — ورود انجام می‌شود.")
    r = api(client, "POST", "/api/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
    data = json_or_none(r) or {}
    token = token_from(data)
    if r.status_code == 200 and token:
        record("ثبت‌نام / ورود دانش‌آموز", True, f"کاربر از قبل موجود بود → ورود موفق ({data.get('user', {}).get('role')})")
        return token
    record("ثبت‌نام / ورود دانش‌آموز", False, f"HTTP {r.status_code} | {data}")
    return None


def step_concepts(client: httpx.Client, token: str) -> int | None:
    ui.section("گام ۳: دریافت فهرست مفاهیم و انتخاب concept_id")
    r = api(client, "GET", "/api/concepts", headers={"Authorization": f"Bearer {token}"})
    data = json_or_none(r) or {}
    concepts = data.get("concepts") or data.get("items") or (data if isinstance(data, list) else [])

    if r.status_code != 200 or not concepts:
        record("دریافت مفاهیم", False, f"HTTP {r.status_code} | تعداد مفاهیم: 0")
        return None

    chosen = next((c for c in concepts if c.get("topic") == "ohm_law"), concepts[0])
    ui.info(f"تعداد مفاهیم موجود: {len(concepts)}")
    ui.info(f"مفهوم انتخاب‌شده برای سناریو: [{chosen.get('id')}] {chosen.get('name')} ({chosen.get('subject')} — پایه {chosen.get('grade')})")
    ui.info("(ترجیح با «قانون اهم» است چون بدفهمیِ سناریو دربارهٔ همین مفهوم است)")
    record("دریافت مفاهیم و انتخاب concept_id", True, f"concept_id={chosen.get('id')}")
    return int(chosen["id"])


def step_start_path_a(client: httpx.Client, token: str, concept_id: int) -> dict[str, Any] | None:
    ui.section("گام ۴: شروع جلسهٔ ارزیابی — مسیر A (انتخاب موضوع)")
    r = api(
        client, "POST", "/api/assess/start",
        json={"trigger_type": "topic_selection", "concept_id": concept_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = json_or_none(r) or {}
    if r.status_code not in (200, 201):
        record("شروع جلسه (مسیر A)", False, f"HTTP {r.status_code} | {data}")
        return None

    session = data.get("session", {})
    question = data.get("next_question")
    ui.info(f"شناسهٔ جلسه: {session.get('id')} | وضعیت: {session.get('status')} | سقف زمان: {session.get('time_limit_seconds')} ثانیه")
    ui.info(f"تعداد فرضیه‌ها: {len(data.get('hypotheses') or [])}")
    if question:
        ui.info(f"سؤالِ تشخیصیِ اول (نوع: {question.get('question_type')} | سختی: {question.get('difficulty')}):")
        ui.info(f"    «{question.get('text')}»")
    else:
        ui.info("⚠️ سؤال اولی برگردانده نشد (بانک خالی؟).")
    ok = bool(session.get("id")) and bool(question)
    record("شروع جلسه (مسیر A) + دریافت سؤال اول", ok, f"session_id={session.get('id')}")
    data["_question"] = question
    return data


def step_submit_answers(client: httpx.Client, token: str, session: dict[str, Any]) -> bool:
    ui.section("گام ۵: ثبت پاسخ‌ها و دریافت تحلیل انطباقی")
    session_id = session["session"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    question = session.get("_question")

    # --- پاسخ اول: بدفهمیِ هدفمند ---
    ui.info(f"پاسخِ اولِ دانش‌آموز (غلطِ مفهومیِ عمدی):")
    ui.info(f"    «{WRONG_RESPONSE}»")
    r = api(client, "POST", f"/api/assess/{session_id}/answer",
            json={"question_id": question["id"], "response_text": WRONG_RESPONSE}, headers=headers)
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("ثبت پاسخ غلط + تحلیل", False, f"HTTP {r.status_code} | {data}")
        return False

    print_evidence(data)
    record("ثبت پاسخ غلط + تحلیل شواهد", True, f"concept_status={data.get('concept_status')} | پاسخ‌ها={data.get('questions_answered')}")

    next_q = data.get("next_question")
    if not next_q:
        ui.info("جلسه پس از پاسخ اول بسته شد ( done=True ).")
        return True

    # --- پاسخ دوم: توضیحِ اصلاحی ---
    ui.info("سؤالِ دنباله‌دارِ انطباقی:")
    ui.info(f"    «{next_q.get('text')}»")
    ui.info("پاسخِ دومِ دانش‌آموز (اصلاحی):")
    ui.info(f"    «{CLARIFYING_RESPONSE[:110]}…»")
    r = api(client, "POST", f"/api/assess/{session_id}/answer",
            json={"question_id": next_q["id"], "response_text": CLARIFYING_RESPONSE}, headers=headers)
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("پاسخ اصلاحی + تحلیل", False, f"HTTP {r.status_code} | {data}")
        return False

    print_evidence(data)
    if data.get("next_question"):
        ui.info(f"سؤال بعدی (در صورت ادامه): «{data['next_question'].get('text')[:120]}…»")
    record("پاسخ اصلاحی + تحلیل شواهد", True, f"concept_status={data.get('concept_status')} | باقی‌مانده={data.get('remaining_seconds')}ثانیه")
    return True


def print_evidence(answer_payload: dict[str, Any]) -> None:
    """شواهد استخراج‌شده و وضعیت گزاره‌ها را زیبا چاپ می‌کند."""
    for ev in answer_payload.get("evidence", []):
        status = ev.get("status", "?")
        status_fa = STATUS_FA.get(status, status)
        conf = ev.get("confidence")
        conf_txt = f"اطمینان={conf:.2f}" if isinstance(conf, (int, float)) else ""
        review = " | نیازمند بررسی معلم" if ev.get("needs_teacher_review") else ""
        ui.info(f"    • گزارهٔ «{str(ev.get('proposition_id'))[:70]}»")
        ui.info(f"        وضعیت: {status_fa} ({status}) | {conf_txt}{review}")
        ui.info(f"        دلیل تحلیل‌گر: {ev.get('reasoning', '')[:140]}")
    statuses = answer_payload.get("proposition_statuses") or {}
    if statuses:
        ui.info("    وضعیت فعلی گزاره‌ها:")
        for prop, st in statuses.items():
            ui.info(f"        - {STATUS_FA.get(st, st):22s} | {str(prop)[:60]}")
    if answer_payload.get("conflicts"):
        ui.info(f"    ⚠️ تعارضِ شواهد در گزاره‌ها: {answer_payload['conflicts']}")
    if answer_payload.get("needs_teacher_review"):
        ui.info("    ⚠️ این پاسخ‌ها نیازمند نگاه معلم هستند.")


def step_report(client: httpx.Client, token: str, session_id: int) -> bool:
    ui.section("گام ۷: دریافت و راستی‌آزمایی گزارش نهایی")
    r = api(client, "GET", f"/api/assess/{session_id}/report", headers={"Authorization": f"Bearer {token}"})
    data = json_or_none(r) or {}
    if r.status_code != 200:
        record("گزارش نهایی", False, f"HTTP {r.status_code} | {data}")
        return False

    text = str(data.get("report_text", ""))
    sections = data.get("sections") or {}
    prop_statuses = data.get("proposition_statuses") or {}

    checks: list[tuple[bool, str]] = [
        ("موضوع بررسی" in text, "متن گزارش شامل «موضوع بررسی» است"),
        ("شواهد" in text, "متن گزارش شامل بخش «شواهد» است"),
        ("موارد هنوز روشن‌نشده" in text, "متن گزارش شامل «موارد هنوز روشن‌نشده» است"),
        ("پیشنهاد اقدام" in text, "متن گزارش شامل «پیشنهاد اقدام» است"),
        (bool(sections.get("مشاهدات")), "بخش «مشاهدات» با ارجاع به پاسخ‌های واقعی پر شده است"),
        (bool(sections.get("شواهد")), "بخش «شواهد» گزاره‌به‌گزاره پر شده است"),
        ("⚠️ نمرهٔ آزمون" in text, "برچسب «⚠️ نمرهٔ آزمون — نه سنجش فهم» وجود دارد"),
        (any(lbl in text for lbl in STATUS_FA.values()), "وضعیت‌های کیفی (تأییدشده/نامشخص/نیاز به بررسی…) در گزارش هستند"),
        (all(v in ALLOWED_STATUSES for v in prop_statuses.values()),
         "همهٔ وضعیت‌های گزاره‌ها یکی از ۵ وضعیتِ مجاز هستند (نه عدد)"),
        (not any(bad in text.lower() for bad in FORBIDDEN_IN_REPORT),
         "هیچ نمره/رتبه/درصد/percentile در گزارش نیست"),
        (not any(k in data for k in ["score", "rank", "percentage", "percentile", "total_score", "percentile_rank"]),
         "کلیدِ عددیِ نمره/رتبه در ساختار گزارش وجود ندارد"),
    ]
    all_ok = True
    for ok, label in checks:
        ui.sub_check(ok, label)
        all_ok = all_ok and ok

    ui.info(f"تعداد پاسخ‌های ثبت‌شده: {data.get('questions_answered')} (این «تعداد» است نه «نمره»)")
    ui.info("─" * 56)
    for line in text.splitlines():
        if line.strip():
            ui.info(line)
    ui.info("─" * 56)
    return record("راستی‌آزمایی گزارش نهایی (کیفی، بدون نمره/رتبه)", all_ok)


def step_path_b(client: httpx.Client, token: str, concept_id: int) -> bool:
    ui.section("گام ۷: جلسهٔ دوم — مسیر B (شروع از پاسخ غلط) و فرضیه‌های ریشهٔ خطا")
    wrong_answer = {
        "problem_text": "یک لامپ با مقاومت ۴ اهم به باتری ۱۲ ولتی وصل شده است؛ جریان عبوری چند آمپر است؟",
        "student_answer": "مقاومت لامپ ۴ اهمه پس جریان هم ۴ آمپره؛ هرچی ولتاژ بیشتر باشه مقاومت هم بیشتر میشه",
        "concept_id": concept_id,
    }
    r = api(client, "POST", "/api/assess/start",
            json={"trigger_type": "wrong_answer", "wrong_answer": wrong_answer},
            headers={"Authorization": f"Bearer {token}"})
    data = json_or_none(r) or {}
    if r.status_code not in (200, 201):
        record("شروع جلسه (مسیر B)", False, f"HTTP {r.status_code} | {data}")
        return False

    hypotheses = data.get("hypotheses") or []
    session = data.get("session", {})
    question = data.get("next_question")

    ui.info(f"شناسهٔ جلسه: {session.get('id')} | وضعیت: {session.get('status')}")
    ui.info(f"تعداد فرضیه‌های ریشهٔ خطا: {len(hypotheses)}")
    for h in hypotheses:
        cross = "بین‌درسی" if h.get("cross_subject") else "هم‌درس"
        ui.info(f"    • [{h.get('depth', 0)}] {h.get('subject', '')}/{h.get('concept_topic', h.get('type'))}"
                f" — نوع: {h.get('type')} | {cross} | وضعیت: {h.get('status')}")
    if question:
        ui.info(f"سؤال آغازین روی مفهومِ ریشه‌ای (concept_id={question.get('concept_id')}):")
        ui.info(f"    «{question.get('text')[:130]}…»")

    has_root_cause = any(h.get("type") == "root_cause" for h in hypotheses)
    has_cross = any(h.get("cross_subject") for h in hypotheses)
    starts_from_root = bool(question) and question.get("concept_id") != concept_id

    ui.sub_check(bool(hypotheses), "موتور حداقل یک فرضیه ساخت")
    ui.sub_check(has_root_cause, "فرضیهٔ «ریشهٔ خطا» (pre-requisite) ساخته شد")
    ui.sub_check(has_cross, "حداقل یک فرضیهٔ بین‌درسی ساخته شد (ریاضی ← فیزیک)")
    ui.sub_check(starts_from_root, "پرسش از محتمل‌ترین ریشهٔ خطا شروع شد، نه از خودِ سؤال اصلی")

    ok = bool(hypotheses) and has_root_cause and has_cross and starts_from_root
    return record("فرضیه‌سازی ریشهٔ خطا (مسیر B)", ok, f"session_id={session.get('id')}")


def print_summary() -> int:
    ui.section("خلاصهٔ نهایی")
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


def main() -> int:
    ui.banner("فهم‌یار — تست سرتاسری (E2E)")
    ui.info(f"آدرس سرور: {BASE_URL}")
    ui.info(f"کاربر تست: {DEMO_USERNAME}")

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS) as client:
        # گام ۱ — بدون سلامت سرور ادامه نمی‌دهیم
        if not step_health(client):
            return print_summary()

        token = step_auth(client)
        if not token:
            ui.info("بدون توکن JWT ادامهٔ تست ممکن نیست.")
            return print_summary()

        concept_id = step_concepts(client, token)
        if concept_id is None:
            return print_summary()

        session_a = step_start_path_a(client, token, concept_id)
        session_id: int | None = None
        if session_a:
            session_id = int(session_a["session"]["id"])
            step_submit_answers(client, token, session_a)
            step_report(client, token, session_id)

        step_path_b(client, token, concept_id)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
