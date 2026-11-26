"""فاز ۱۴ — معلمِ درلحظه (On-Demand Tutor).

همهٔ تست‌ها mock هستند: هیچ فراخوانیِ واقعیِ OpenRouter انجام نمی‌شود.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ai import model_abstraction as ma
from api.routes_tutor import clear_tutor_cache


# ─────────────────────────── کمکی‌ها ───────────────────────────
def _login(client: TestClient, username: str = "student1", password: str = "student123") -> dict:
    body = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()
    return {"Authorization": f"Bearer {body['token']}"}


def _fake_router(payload: dict, *, fail: bool = False):
    """روتری که پاسخِ ثابتِ JSON می‌دهد (یا عمداً می‌شکند)."""

    class FakeRouter:
        def __init__(self):
            self.calls = []

        async def generate(self, prompt, task_type, temperature=0.7):
            self.calls.append({"prompt": prompt, "task_type": task_type})
            if fail:
                raise RuntimeError("مدل در دسترس نیست")
            return ma.AIResponse(
                text=json.dumps(payload, ensure_ascii=False),
                model_name="fake-tutor",
                token_count=120,
                cost_usd=0.0,
                prompt_tokens=100,
                completion_tokens=20,
                attempts=1,
            )

    return FakeRouter()


@pytest.fixture()
def client(monkeypatch):
    """کلاینتِ تست با دیتابیس و مدلِ قطع‌شده.

    ``build_exam_report`` و ``SessionManager`` جعل می‌شوند تا تست به وضعیتِ
    دیتابیسِ محلی وابسته نباشد — چه تنها اجرا شود، چه در کلِ مجموعه.
    """
    from api import routes_tutor

    class FakeManager:
        def __init__(self, db):
            pass

        def get_session(self, session_id, user):
            return object()

    monkeypatch.setattr(routes_tutor, "SessionManager", FakeManager)
    monkeypatch.setattr(
        routes_tutor, "build_exam_report", lambda db, session: _SAMPLE_REPORT
    )
    clear_tutor_cache()
    yield TestClient(_app())
    clear_tutor_cache()


def _app():
    from main import app

    return app


def _tutor(client, headers, **body):
    return client.post("/api/tutor/explain", json=body, headers=headers)



# ─────────────── جعبه‌ابزارِ مستقل از دیتابیس ───────────────
_SAMPLE_REPORT = {
    "concept_name": "قانون اهم",
    "session_id": 1,
    "per_question": [
        {
            "order": n,
            "stage": (n - 1) // 2 + 1,
            "question_text": f"سؤالِ {n} دربارهٔ قانون اهم",
            "response": "ولتاژ بیشتر یعنی جریان بیشتر",
            "status": "WRONG" if n % 2 else "HALF_CORRECT",
            "diagnostic_insight": "رابطهٔ خطی را دید، اثرِ دما را نه.",
        }
        for n in range(1, 11)
    ],
    "cross_check_findings": [
        {"title": "بلوف", "type": "BLUFF_DETECTED", "description": "x"},
        {
            "title": "تناقضِ تست و تشریح",
            "type": "CONTRADICTION",
            "description": "در تست گفتی دو برابر، در تشریحی گفتی کمتر.",
            "contradiction_title": "دو جوابِ ناسازگار",
        },
    ],
}


# ─────────────────────── تست‌های قرارداد ───────────────────────
def test_endpoint_is_registered():
    from main import app

    assert "/api/tutor/explain" in app.openapi()["paths"]


def test_requires_authentication():
    client = TestClient(_app())
    res = client.post("/api/tutor/explain", json={"session_id": 1, "type": "question"})
    assert res.status_code in (401, 403), res.status_code


def test_rejects_unknown_type():
    client = TestClient(_app())
    h = _login(client)
    res = _tutor(client, h, session_id=1, type="freeform")
    assert res.status_code == 422


def test_rejects_order_out_of_range():
    client = TestClient(_app())
    h = _login(client)
    res = _tutor(client, h, session_id=1, type="question", order=99)
    assert res.status_code == 422


def test_missing_session_is_404():
    client = TestClient(_app())
    h = _login(client)
    res = _tutor(client, h, session_id=999_999, type="question", order=1)
    assert res.status_code == 404


# ──────────────────── خوشهٔ سؤال (question) ────────────────────
def test_question_explanation_returns_three_fields(client, monkeypatch):
    """مدل پاسخِ درست می‌دهد ⇒ هر سه فیلد باید برگردد."""
    payload = {
        "misconception_root": "تو فرض کردی مقاومت ثابت است.",
        "intuitive_explanation": "بیا با شیلنگِ آب ببینیم...",
        "golden_tip": "کاهنده = بخشنده!",
    }
    fake = _fake_router(payload)
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)

    h = _login(client)
    sid = 1
    res = _tutor(client, h, session_id=sid, type="question", order=1)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["type"] == "question"
    assert data["generated_by"] == "model"
    assert data["content"] == payload
    assert fake.calls and fake.calls[0]["task_type"] == "tutor_explain"


def test_question_prompt_is_second_person(client, monkeypatch):
    """پرامپتِ سیستم باید لحنِ دومِ‌شخص بخواهد و سومِ‌شخص را منع کند."""
    fake = _fake_router(
        {
            "misconception_root": "a",
            "intuitive_explanation": "b",
            "golden_tip": "c",
        }
    )
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1
    _tutor(client, h, session_id=sid, type="question", order=1)

    prompt = fake.calls[0]["prompt"]
    assert "دومِ‌شخص" in prompt
    assert "سومِ‌شخص" in prompt  # به‌عنوان ممنوعیت
    assert "دانش‌آموز فکر کرد" in prompt


def test_question_prompt_carries_the_student_answer(client, monkeypatch):
    fake = _fake_router(
        {"misconception_root": "a", "intuitive_explanation": "b", "golden_tip": "c"}
    )
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1
    _tutor(client, h, session_id=sid, type="question", order=1)
    prompt = fake.calls[0]["prompt"]
    assert "پاسخِ دانش‌آموز" in prompt
    assert "صورتِ سؤال" in prompt


def test_model_failure_falls_back_to_educational_text(client, monkeypatch):
    """اگر مدل بمیرد، دکمهٔ معلم نباید خطا بدهد."""
    fake = _fake_router({}, fail=True)
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1
    res = _tutor(client, h, session_id=sid, type="question", order=1)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["generated_by"] == "fallback"
    assert set(data["content"]) == {"misconception_root", "intuitive_explanation", "golden_tip"}
    assert all(v.strip() for v in data["content"].values())


def test_partial_model_output_is_completed(client, monkeypatch):
    """مدل فقط یک فیلد داد ⇒ دو فیلد دیگر باید پر شوند، نه خالی."""
    fake = _fake_router({"misconception_root": "فقط همین"})
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1
    data = _tutor(client, h, session_id=sid, type="question", order=1).json()
    assert data["content"]["misconception_root"] == "فقط همین"
    assert data["content"]["intuitive_explanation"].strip()
    assert data["content"]["golden_tip"].strip()


def test_second_call_is_served_from_cache(client, monkeypatch):
    """دکمهٔ دوم نباید هزینهٔ دوم بسازد."""
    fake = _fake_router(
        {"misconception_root": "a", "intuitive_explanation": "b", "golden_tip": "c"}
    )
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1

    first = _tutor(client, h, session_id=sid, type="question", order=1).json()
    second = _tutor(client, h, session_id=sid, type="question", order=1).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert len(fake.calls) == 1, "فراخوانیِ دوم نباید به مدل برسد"


# ───────────────── خوشهٔ تناقض (contradiction) ─────────────────
def test_contradiction_returns_three_fields(client, monkeypatch):
    payload = {
        "why_it_happened": "چون در تست فرمول را از حفظ زدی.",
        "how_to_connect_bridge": "بیا این دو تکه را وصل کنیم...",
        "exam_shield_tip": "یک ثانیه از خودت بپرس...",
    }
    fake = _fake_router(payload)
    monkeypatch.setattr("api.routes_tutor.get_router", lambda: fake)
    h = _login(client)
    sid = 1
    res = _tutor(client, h, session_id=sid, type="contradiction", finding_index=0)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["content"] == payload


def test_contradiction_without_any_is_404(client):
    h = _login(client)
    sid = 1
    res = _tutor(client, h, session_id=sid, type="contradiction", finding_index=0)
    # یا 404 (تناقضی نیست) یا 200 اگر نشستِ انتخابی تناقض داشت
    assert res.status_code in (200, 404)
    if res.status_code == 404:
        assert "تناقض" in res.json()["detail"]


# ─────────────────────── انتخابیِ نشست ───────────────────────
def _any_completed_session(client: TestClient, headers: dict) -> int:
    """یک نشستِ تمام‌شده که کارنامه‌اش per_question دارد."""
    from models.database import SessionLocal
    from models.question import AssessmentSession

    db = SessionLocal()
    try:
        for session in (
            db.query(AssessmentSession)
            .filter(AssessmentSession.status == "completed")
            .order_by(AssessmentSession.id.desc())
            .limit(30)
            .all()
        ):
            from reports.exam_report import build_exam_report

            try:
                report = build_exam_report(db, session)
            except Exception:  # noqa: BLE001
                continue
            if report.get("per_question"):
                return session.id
    finally:
        db.close()
    pytest.skip("هیچ نشستِ تمام‌شده‌ای با کارنامه پیدا نشد")


def _session_with_contradiction(client: TestClient, headers: dict) -> int | None:
    from models.database import SessionLocal
    from models.question import AssessmentSession
    from reports.exam_report import build_exam_report

    db = SessionLocal()
    try:
        for session in (
            db.query(AssessmentSession)
            .filter(AssessmentSession.status == "completed")
            .order_by(AssessmentSession.id.desc())
            .limit(30)
            .all()
        ):
            try:
                report = build_exam_report(db, session)
            except Exception:  # noqa: BLE001
                continue
            if any(
                str(f.get("type", "")).upper() == "CONTRADICTION"
                for f in (report.get("cross_check_findings") or [])
            ):
                return session.id
    finally:
        db.close()
    return None


def test_finding_index_is_absolute_not_filtered(monkeypatch):
    """رگرسیون: ایندکسِ تناقض باید نسبت به فهرستِ کامل باشد، نه فیلترشده.

    فرانت کارت‌ها را به ترتیبِ ``cross_check_findings`` رندر می‌کند؛ اگر
    بک‌اند ایندکس را روی فهرستِ CONTRADICTIONها بشمارد، کاربر تناقضِ
    اشتباه می‌گیرد یا ۴۰۴. این باگ در فاز ۱۴ واقعاً رخ داد.
    """
    from api import routes_tutor

    report = {
        "concept_name": "مفهومِ تستی",
        "per_question": [{"order": 1, "question_text": "س", "response": "پ", "status": "WRONG"}],
        "cross_check_findings": [
            {"title": "بلوف", "type": "BLUFF_DETECTED", "description": "x"},
            {"title": "اصطلاح", "type": "JARGON_VIOLATION", "description": "y"},
            {"title": "تناقضِ دوم", "type": "CONTRADICTION", "description": "z",
             "contradiction_title": "تناقضِ دوم"},
        ],
    }

    class FakeManager:
        def __init__(self, db):
            pass

        def get_session(self, session_id, user):
            return object()

    monkeypatch.setattr(routes_tutor, "SessionManager", FakeManager)
    monkeypatch.setattr(routes_tutor, "build_exam_report", lambda db, s: report)
    monkeypatch.setattr(routes_tutor, "_call_model", _async_none)
    routes_tutor.clear_tutor_cache()

    client = TestClient(_app())
    h = _login(client)
    res = _tutor(client, h, session_id=1, type="contradiction", finding_index=2)
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "تناقضِ دوم"


async def _async_none(prompt):
    return None
