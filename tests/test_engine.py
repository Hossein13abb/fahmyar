"""تست‌های پایه موتور فهم‌یار — با AI_PROVIDER=mock و دیتابیس موقت."""
import os
import sys
import tempfile

_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="fahmyar_test_"), "test.db")
os.environ["AI_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from models.database import SessionLocal, init_db  # noqa: E402
from graph.seed_data import seed_all  # noqa: E402
from graph.knowledge_graph import load_graph  # noqa: E402
from models.concept import Concept  # noqa: E402
from models.question import AssessmentSession, EvidenceStatus, Question  # noqa: E402
from models.user import User  # noqa: E402
from engine.inference import InferenceEngine  # noqa: E402
from ai.response_analyzer import EvidenceRecord  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def seeded():
    init_db()
    seed_all(verbose=False)
    yield


def _db():
    return SessionLocal()


# ---------- داده‌های اولیه ----------
def test_seed_minimums(seeded):
    db = _db()
    try:
        concepts = db.query(Concept).count()
        approved_questions = db.query(Question).filter(Question.approval_status == "approved").count()
        assert concepts >= 15, f"حداقل ۱۵ مفهوم لازم است؛ موجود: {concepts}"
        assert approved_questions >= 45, f"حداقل ۴۵ سؤال تأییدشده لازم است؛ موجود: {approved_questions}"
    finally:
        db.close()


def test_knowledge_graph_cross_subject(seeded):
    db = _db()
    try:
        graph = load_graph(db)
        coulomb = db.query(Concept).filter(Concept.topic == "coulomb_law").first()
        prereqs = graph.get_prerequisites(coulomb.id, depth=2)
        topics = {p["topic"] for p in prereqs}
        assert "exponents" in topics, "توان باید پیش‌نیاز ابزارِ کولن باشد"
        cross = [p for p in prereqs if p["cross_subject"]]
        assert cross, "حداقل یک پیش‌نیاز بین‌درسی باید پیدا شود"
    finally:
        db.close()


def test_root_cause_candidates_ordering(seeded):
    db = _db()
    try:
        graph = load_graph(db)
        coulomb = db.query(Concept).filter(Concept.topic == "coulomb_law").first()
        candidates = graph.get_root_cause_candidates(coulomb.id, error_type="computational")
        assert candidates, "کاندیدای ریشهٔ خطا باید برگردد"
        # برای خطای محاسباتی، ابزارِ محاسباتی ریاضی باید زودتر بیاید
        assert candidates[0]["dependency_type"] == "tool"
        target = graph.get_isolating_question_target(coulomb.id, passed_prerequisites=[])
        assert target is not None
    finally:
        db.close()


# ---------- منطق ۵ وضعیته ----------
def _make_session(db, student_id=1) -> AssessmentSession:
    topic = db.query(Concept).filter(Concept.topic == "coulomb_law").first()
    return AssessmentSession(
        student_id=student_id,
        trigger_type="topic_selection",
        trigger_detail="test",
        concept_id=topic.id if topic else None,
        started_at=__import__("datetime").datetime.utcnow(),
        time_limit_seconds=1800,
        status="active",
        current_hypotheses=[],
        evidence_log=[],
    )


def _ev(prop, status, etype="strong_confirming", conf=0.8, qid_hint=0):
    return EvidenceRecord(
        proposition_id=prop, status=status, evidence_type=etype,
        reasoning="تست", confidence=conf, needs_teacher_review=False,
    )


def test_inference_confirmed_with_two_independent(seeded):
    db = _db()
    try:
        engine = InferenceEngine(db)
        s = _make_session(db)
        s.evidence_log = [
            {"question_id": 11, "response": "r1", "answered_at": "2026-11-08T00:00:00",
             "evidence": [_ev("گزارهٔ تست", "CONFIRMED", "strong_confirming", 0.8).to_dict()]},
            {"question_id": 22, "response": "r2", "answered_at": "2026-11-08T00:01:00",
             "evidence": [_ev("گزارهٔ تست", "LIKELY_UNDERSTOOD", "weak_confirming", 0.55).to_dict()]},
        ]
        out = engine.update_evidence(s, [])
        assert out["proposition_statuses"]["گزارهٔ تست"] == EvidenceStatus.CONFIRMED.value
    finally:
        db.close()


def test_inference_conflict_is_unclear(seeded):
    db = _db()
    try:
        engine = InferenceEngine(db)
        s = _make_session(db)
        s.evidence_log = [
            {"question_id": 1, "response": "r1", "answered_at": "t",
             "evidence": [_ev("گ", "LIKELY_UNDERSTOOD", "strong_confirming", 0.7).to_dict()]},
            {"question_id": 2, "response": "r2", "answered_at": "t",
             "evidence": [_ev("گ", "NEEDS_REVIEW", "weak_contradicting", 0.4).to_dict()]},
        ]
        out = engine.update_evidence(s, [])
        assert out["proposition_statuses"]["گ"] == EvidenceStatus.UNCLEAR.value
        assert out["conflicts"] == ["گ"]
    finally:
        db.close()


def test_inference_strong_contradiction_needs_review(seeded):
    db = _db()
    try:
        engine = InferenceEngine(db)
        s = _make_session(db)
        s.evidence_log = [
            {"question_id": 1, "response": "r1", "answered_at": "t",
             "evidence": [_ev("گ", "NEEDS_REVIEW", "strong_contradicting", 0.9).to_dict()]},
        ]
        out = engine.update_evidence(s, [])
        assert out["proposition_statuses"]["گ"] == EvidenceStatus.NEEDS_REVIEW.value
    finally:
        db.close()


def test_computational_success_does_not_confirm_core(seeded):
    db = _db()
    try:
        engine = InferenceEngine(db)
        s = _make_session(db)
        s.evidence_log = [
            {"question_id": 1, "response": "r1", "answered_at": "t",
             "evidence": [_ev("گزارهٔ اصلی", "CONFIRMED", "computational_success", 0.9).to_dict()]},
            {"question_id": 2, "response": "r2", "answered_at": "t",
             "evidence": [_ev("گزارهٔ اصلی", "CONFIRMED", "computational_success", 0.9).to_dict()]},
        ]
        out = engine.update_evidence(s, [])
        # موفقیت محاسباتی ≠ فهمیدن
        assert out["proposition_statuses"]["گزارهٔ اصلی"] in (
            EvidenceStatus.UNCLEAR.value,
            EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
        )
    finally:
        db.close()


def test_should_continue_blocks_on_time_limit(seeded):
    db = _db()
    try:
        engine = InferenceEngine(db)
        s = _make_session(db)
        assert engine.should_continue(s, time_remaining_seconds=0) is False
        assert engine.should_continue(s, time_remaining_seconds=300) is True
        assert engine.should_continue(s, time_remaining_seconds=300, student_requested_stop=True) is False
    finally:
        db.close()


# ---------- جریان کامل با TestClient و mock ----------
def test_full_session_flow_with_mock_ai(seeded):
    from main import app

    client = TestClient(app)
    # ورود به‌عنوان دانش‌آموز دمو
    r = client.post("/api/auth/login", json={"username": "student1", "password": "student123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = _db()
    try:
        coulomb = db.query(Concept).filter(Concept.topic == "coulomb_law").first()
        concept_id = coulomb.id
    finally:
        db.close()

    r = client.post("/api/assess/start", json={"trigger_type": "topic_selection", "concept_id": concept_id}, headers=headers)
    assert r.status_code == 201, r.text
    data = r.json()
    session_id = data["session"]["id"]
    question = data["next_question"]
    assert question is not None

    reasoning_answer = (
        "چون نیروی بین دو بار با حاصل‌ضرب بارها نسبت مستقیم دارد و با مجذور فاصله نسبت عکس، "
        "بنابراین با نصف شدن فاصله نیرو چهار برابر می‌شود. زیرا فرمول کولن F = k q1 q2 / r^2 است "
        "و چون ر = فاصله در مخرج به توان دو قرار دارد، نصف شدن آن یعنی تقسیم بر یک‌چهارم. "
        "این را می‌توان با جایگذاری اعداد هم نشان داد و باعث می‌شود نیرو خیلی بزرگ‌تر شود."
    )

    report = None
    for _ in range(12):
        if question is None:
            break
        r = client.post(
            f"/api/assess/{session_id}/answer",
            json={"question_id": question["id"], "response_text": reasoning_answer},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        payload = r.json()
        if payload.get("done"):
            break
        question = payload.get("next_question")

    r = client.get(f"/api/assess/{session_id}/report", headers=headers)
    assert r.status_code == 200, r.text
    report = r.json()
    assert "موضوع بررسی" in report["report_text"]
    assert "شواهد" in report["report_text"]
    assert "⚠️ نمرهٔ آزمون" in report["report_text"]
    # هیچ نشانه‌ای از رتبه/نمره/درصد نباید باشد
    for forbidden in ["رتبه", "درصد", "percentile", "rank", "score:"]:
        assert forbidden not in report["report_text"].lower()


def test_auth_required():
    from main import app

    client = TestClient(app)
    r = client.post("/api/assess/start", json={"trigger_type": "topic_selection", "concept_id": 1})
    assert r.status_code == 401


def test_wrong_answer_path_builds_hypotheses(seeded):
    from main import app

    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": "student2", "password": "student123"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = _db()
    try:
        coulomb = db.query(Concept).filter(Concept.topic == "coulomb_law").first()
        cid = coulomb.id
    finally:
        db.close()

    r = client.post(
        "/api/assess/start",
        json={
            "trigger_type": "wrong_answer",
            "wrong_answer": {
                "problem_text": "نیروی بین دو بار را با فاصله نصف شده حساب کنید",
                "student_answer": "نیرو دو برابر می‌شود چون فاصله نصف شد",
                "concept_id": cid,
            },
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["hypotheses"], "مسیر پاسخ غلط باید فرضیه بسازد"
    cross = [h for h in data["hypotheses"] if h.get("cross_subject")]
    assert cross, "باید حداقل یک فرضیهٔ بین‌درسی ساخته شود (توان ریاضی → کولن)"



def test_safe_parse_json_latex_backslashes():
    from ai.json_sanitize import extract_json_array, safe_parse_json

    raw = r"""```json
[
  {
    "id": 1,
    "text": "دترمینان ماتریس $$\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}$$ و مقدار $\frac{۱}{۲} \cdot \sqrt{x} \times \alpha$ برابر چیست؟",
    "options": ["$\frac{۱}{۲}$", "$-۲$", "$\left(x\right)$", "$\tan(\theta) \neq ۰$"],
    "correct_answer": 2,
    "subject": "هندسه ۳",
    "difficulty": "کنکوری",
    "source_tag": "تألیفی AI",
    "explanation": "با استفاده از $\det(A) = ad - bc$ مقدار $-۲$ به‌دست می‌آید."
  }
]
```"""
    parsed = safe_parse_json(raw)
    assert isinstance(parsed, list) and len(parsed) == 1
    assert r"\begin{bmatrix}" in parsed[0]["text"]
    assert r"\frac{۱}{۲}" in parsed[0]["text"]
    assert r"\cdot" in parsed[0]["text"]
    assert r"\sqrt{x}" in parsed[0]["text"]
    assert extract_json_array(raw) == parsed


def test_exam_preview_multi_model_retry_fallback(seeded):
    from main import app
    from ai.model_abstraction import AIResponse, get_router

    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": "teacher1", "password": "teacher123"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    router = get_router()
    orig_gen = router.generate
    attempts = []

    async def flaky_generate(prompt, task_type, temperature=0.8, model_override=None):
        attempts.append(model_override)
        if len(attempts) == 1:
            return AIResponse(text="NOT VALID JSON", model_name="meta-llama/llama-3.3-70b-instruct:free", token_count=5)
        raw_latex = r'[{"id": 1, "text": "مقدار $\frac{۱}{۲} \cdot \begin{bmatrix} ۱ \end{bmatrix}$ چیست؟", "options": ["۱", "۲", "۳", "۴"], "correct_answer": 1, "subject": "هندسه", "difficulty": "کنکوری", "source_tag": "تألیفی AI", "explanation": "پاسخ ۱"}]'
        return AIResponse(text=raw_latex, model_name=model_override or "qwen/qwen-2.5-coder-32b-instruct:free", token_count=30)

    router.generate = flaky_generate
    try:
        res = client.post(
            "/api/teacher/generate-exam-preview",
            json={
                "field": "math",
                "grade": "12",
                "subjects": ["geometry"],
                "subject_configs": [{"subject": "geometry", "count": 1, "difficulty": "کنکوری", "subTopics": []}],
                "count": 1,
                "ai_ratio": 60,
                "difficulty": "کنکوری",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["questions"]) == 1
        assert len(attempts) == 2
        assert attempts[1] == "qwen/qwen-2.5-coder-32b-instruct:free"
    finally:
        router.generate = orig_gen
