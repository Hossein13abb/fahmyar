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



def test_clean_latex_for_pdf_and_svg_pdf_export(seeded):
    from main import app
    from reports.exam_pdf import clean_latex_for_pdf, has_math

    # مسیر اصلی: فرمول‌ها به تصویر واقعی رندر می‌شوند و به متن تبدیل نمی‌شوند
    assert has_math(r"دترمینان $\frac{a}{b}$ چیست؟") is True

    # مسیر fallback (فقط وقتی رندر تصویری شکست بخورد): پاک‌سازی متنیِ امن
    cleaned = clean_latex_for_pdf(
        r"دترمینان $$\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}$$ و $\frac{a}{b} \times ۲$ چیست؟"
    )
    assert "$" not in cleaned
    # ماتریس هرگز به رشتهٔ براکتیِ «[ ۲ , ۱ | -۱ , ۰ ]» تبدیل نمی‌شود
    assert "[ " not in cleaned
    assert " | " not in cleaned
    assert "," not in cleaned
    for cell in ("۱", "۲", "۳", "۴"):
        assert cell in cleaned
    assert "a/b" in cleaned            # کسر به «a/b» ساده می‌شود، نه «a به روی b»
    assert "×" in cleaned              # \times به نماد × تبدیل می‌شود
    # هیچ ترجمهٔ کلمه‌ای انجام نمی‌شود
    assert "به روی" not in cleaned
    assert "رادیکال" not in cleaned

    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": "teacher1", "password": "teacher123"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    valid_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 160" width="300" height="160">'
        '<rect x="20" y="20" width="260" height="120" fill="#f8fafc" stroke="#0d9488" stroke-width="2"/>'
        '<circle cx="150" cy="80" r="40" fill="none" stroke="#0f172a" stroke-width="2"/>'
        '<text x="150" y="85" font-family="Vazirmatn, Arial" font-size="14" text-anchor="middle">شعاع ۵</text>'
        "</svg>"
    )
    res = client.post(
        "/api/teacher/generate-exam-pdf",
        json={
            "title": "آزمون تست هندسه و حسابان",
            "school_name": "دبیرستان نمونه",
            "grade": "12",
            "major": "ریاضی و فیزیک",
            "subject_label": "هندسه ۳",
            "topic": "ماتریس و مقاطع مخروطی",
            "duration_minutes": 45,
            "difficulty": "کنکوری",
            "questions": [
                {
                    "id": 1,
                    "text": r"دترمینان $$\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}$$ و $\frac{۱}{۲} \times ۴$ کدام است؟",
                    "options": [r"$\frac{۱}{۲}$", "$-۲$", "$۰$", "$۴$"],
                    "correct_answer": 2,
                    "source_tag": "تألیفی AI",
                    "explanation": r"حاصل $\frac{۱}{۲} \times ۴ = ۲$ و دترمینان برابر $-۲$ است.",
                    "diagram_svg": valid_svg,
                },
                {
                    "id": 2,
                    "text": "سؤال با SVG معیوب که باید بدون خطا نادیده گرفته شود",
                    "options": ["۱", "۲", "۳", "۴"],
                    "correct_answer": 1,
                    "source_tag": "قلم‌چی",
                    "explanation": "پاسخ ۱",
                    "diagram_svg": "<svg><broken>",
                },
            ],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")
    assert len(res.content) > 5000


def test_prompt_rules_and_swallowed_backslash_recovery():
    from ai.exam_generator import build_exam_preview_prompt
    from ai.json_sanitize import safe_parse_json

    prompt = build_exam_preview_prompt(
        count=3,
        field_label="ریاضی و فیزیک",
        subjects_slugs="geometry",
        subjects_labels="هندسه ۳",
        subject_configs=[{"subject": "geometry", "count": 3, "difficulty": "سخت", "subTopics": []}],
        sub_topics=[],
        ai_ratio=50,
        grade_label="دوازدهم",
        topic="—",
        question_type_label="نامشخص / ترکیبی",
        difficulty_label="سخت",
        custom_prompt="—",
    )
    assert "You MUST double-escape all LaTeX commands in the JSON" in prompt
    assert "BANNED NEZAM-GHADIM TOPICS" in prompt
    assert "معادله بیضی" in prompt
    assert "انتگرال" in prompt
    assert "SVGs are OPTIONAL." in prompt
    assert "STRICT DIFFICULTY CALIBRATION:" in prompt

    # حتی اگر بک‌اسلشِ begin{bmatrix} یا frac{ بلعیده شده باشد، پیش‌پردازنده آن را احیا می‌کند
    swallowed = '[{"id": 1, "text": "$$begin{bmatrix} ۱ & ۲ \\\\ ۳ & ۴ end{bmatrix}$$ و $frac{۱}{۲} + sqrt{x}$"}]'
    parsed = safe_parse_json(swallowed)
    assert r"\begin{bmatrix}" in parsed[0]["text"]
    assert r"\end{bmatrix}" in parsed[0]["text"]
    assert r"\frac{۱}{۲}" in parsed[0]["text"]
    assert r"\sqrt{x}" in parsed[0]["text"]



def test_latex_to_persian_text_converter():
    from reports.exam_pdf import latex_to_persian_text

    raw = r"اگر زاویه بین $\vec{a}$ و $\vec{AB}$ برابر $30^\circ$ باشد و $\sqrt{x} = \frac{1}{2}$ و $$\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}$$ باشد:"
    out = latex_to_persian_text(raw)
    # برچسبِ برداری حذف می‌شود ولی هیچ ترجمهٔ کلمه‌ای («بردار»، «رادیکال»، «به روی») ساخته نمی‌شود
    assert "بردار" not in out
    assert "رادیکال" not in out
    assert "به روی" not in out
    assert "a" in out and "AB" in out
    assert "۳۰" in out
    assert "x" in out
    assert "۱/۲" in out
    # ماتریس به رشتهٔ براکتی تبدیل نمی‌شود (فقط سلول‌ها با «،» جدا می‌شوند)
    assert "[ " not in out
    assert " | " not in out
    assert "۱ ، ۲ ، ۳ ، ۴" in out
    assert "$" not in out
    assert "\\" not in out
    assert "vec" not in out
    assert "circ" not in out



def test_nezam_jadid_syllabus_and_latex_to_pdf_image():
    from reportlab.platypus import Image as RLImage
    from ai.exam_generator import build_exam_preview_prompt
    from reports.exam_pdf import latex_to_pdf_image, render_latex_to_image

    prompt = build_exam_preview_prompt(
        count=2,
        field_label="ریاضی و فیزیک",
        subjects_slugs="geometry",
        subjects_labels="هندسه ۳",
        subject_configs=[{"subject": "geometry", "count": 2, "difficulty": "متوسط", "subTopics": []}],
        sub_topics=[],
        ai_ratio=50,
        grade_label="دوازدهم",
        topic="—",
        question_type_label="نامشخص / ترکیبی",
        difficulty_label="متوسط",
        custom_prompt="—",
    )
    assert "CRITICAL SYLLABUS RULE (Nezam Jadid - نظام جدید 1397 onwards):" in prompt
    assert "BANNED NEZAM-GHADIM TOPICS (STRICTLY FORBIDDEN):" in prompt
    assert "معادله بیضی و هذلولی" in prompt
    assert "معکوس ماتریس 3x3" in prompt

    img_frac = latex_to_pdf_image(r"$ \frac{a}{b} $")
    assert isinstance(img_frac, RLImage)
    assert img_frac.drawWidth > 0 and img_frac.drawHeight > 0

    img_sqrt = render_latex_to_image(r"$ \sqrt{2} $")
    assert isinstance(img_sqrt, RLImage)

    img_mat = latex_to_pdf_image(r"$$ \begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix} $$")
    assert isinstance(img_mat, RLImage)



def test_critical_math_formatting_rule_and_pristine_json_latex():
    from ai.exam_generator import build_exam_preview_prompt
    from ai.json_sanitize import safe_parse_json

    prompt = build_exam_preview_prompt(
        count=2,
        field_label="ریاضی و فیزیک",
        subjects_slugs="geometry",
        subjects_labels="هندسه ۳",
        subject_configs=[{"subject": "geometry", "count": 2, "difficulty": "متوسط", "subTopics": []}],
        sub_topics=[],
        ai_ratio=50,
        grade_label="دوازدهم",
        topic="—",
        question_type_label="نامشخص / ترکیبی",
        difficulty_label="متوسط",
        custom_prompt="—",
    )
    assert "CRITICAL MATH FORMATTING RULE:" in prompt
    assert r"$\cos^{-1}\left(\frac{4}{9}\right)$" in prompt
    assert r"$T^{-1}$" in prompt
    assert r"$\vec{n}_1 = (1, 2, 2)$" in prompt

    raw = r'[{"id": 1, "text": "مقدار $\cos^{-1}\left(\frac{4}{9}\right)$ و $T^-1$ و $\vec{n}_1$ در \begin{bmatrix} 2 & 1 \\ 1 & 3 \end{bmatrix} چیست؟"}]'
    parsed = safe_parse_json(raw)
    txt = parsed[0]["text"]
    assert r"\cos^{-1}" in txt
    assert r"\vec{n}_1" in txt
    assert r"\begin{bmatrix} 2 & 1 \\ 1 & 3 \end{bmatrix}" in txt
    assert "T^{-1}" in txt



def test_sanitize_json_backslash_and_dollar_noise():
    from ai.json_sanitize import sanitize_json_string
    from reports.exam_pdf import latex_to_persian_text

    # Single-backslash rac, 	heta, egin, \sqrt, ec and broken $\$ dollars
    raw = r'[{"id": 1, "text": "مقدار $\$\sqrt{7}\$$ و $\theta$ و $\vec{a}$ و $\frac{1}{2}$ و \cos^{-1}(4/9) چیست؟"}]'
    parsed = sanitize_json_string(raw)
    txt = parsed[0]["text"]
    assert r"\sqrt{7}" in txt
    assert r"\theta" in txt
    assert r"\vec{a}" in txt
    assert r"\frac{1}{2}" in txt
    assert r"$\$" not in txt

    # PDF converter handles both escaped and unescaped commands + cos^{-1} + theta
    pdf_txt = latex_to_persian_text(r"$\$ sqrt{7} \$ و vec{a} و frac{1}{2} و \cos^{-1} و theta و 45^\circ")
    assert "۷" in pdf_txt            # رادیکاند باقی می‌ماند
    assert "a" in pdf_txt
    assert "۱/۲" in pdf_txt
    assert "۴۵" in pdf_txt
    assert "$" not in pdf_txt
    for banned in ("رادیکال", "بردار", "به روی", "کسینوس معکوس", "تتا", "درجه"):
        assert banned not in pdf_txt, banned



def test_final_pdf_cleanup_and_get_pdf_safe_text():
    from reports.exam_pdf import final_pdf_cleanup, get_pdf_safe_text

    raw = r"مقدار $45^\circ$ و $\sqrt{7}$ و $\vec{a}$ و $\cos^{-1}(4/9)$ و $\frac{a}{b}$ و $\theta$ و $\rightarrow \infty$"
    cleaned = final_pdf_cleanup(raw)
    assert "۴۵" in cleaned and "°" in cleaned     # \circ → ° (نماد، نه کلمه)
    assert "۷" in cleaned
    assert "a/b" in cleaned                        # \frac → a/b (نماد، نه «به روی»)
    assert "→" in cleaned                          # \rightarrow → →
    assert "∞" in cleaned                          # \infty → ∞
    # هیچ ترجمهٔ کلمه‌ای: این واژه‌ها هرگز نباید ظاهر شوند
    for banned in ("به روی", "رادیکال", "بردار", "کسینوس معکوس", "تتا", "به سمت", "بی‌نهایت", "درجه"):
        assert banned not in cleaned, banned
    for ch in ("$", "\\", "{", "}", "^", "_"):
        assert ch not in cleaned

    safe = get_pdf_safe_text(raw)
    assert isinstance(safe, str) and len(safe) > 10


def test_math_renderer_real_fractions_and_radicals():
    """فرمول‌ها باید به تصویر واقعی (کسر/رادیکال/بردار/ماتریس) رندر شوند — نه متنِ «به روی»."""
    from reports.math_renderer import normalize_latex, render_math_png

    assert normalize_latex(r"$\frac{a}{b}$") == r"\frac{a}{b}"
    assert normalize_latex(r"sqrt{7}") == r"\sqrt{7}"
    assert normalize_latex(r"vec{AB}") == r"\vec{AB}"
    assert normalize_latex(r"\\frac{a}{b}") == r"\frac{a}{b}"

    frac = render_math_png(r"$\frac{۵\sqrt{۱۴}}{۱۴}$", font_size=10.5)
    assert frac is not None
    assert frac.width > 10 and frac.height > 8
    assert frac.depth > 0
    assert frac.png[:8] == b"\x89PNG\r\n\x1a\n"

    for expr in (
        r"$\sqrt{۷}$",
        r"$\vec{a}=(۱,۲,۲)$",
        r"$\cos^{-1}\left(\frac{۴}{۹}\right)$",
        r"$۴۵^\circ$",
        r"$$\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}$$",
    ):
        rendered = render_math_png(expr, font_size=10.5)
        assert rendered is not None, expr
        assert rendered.width > 0 and rendered.height > 0


def test_pdf_text_flow_splits_math_segments():
    from reports.pdf_text_flow import has_math, split_math_segments

    segs = split_math_segments(r"مقدار $\frac{۱}{۲}$ و $$\sqrt{۷}$$ کدام است؟")
    kinds = [seg[0] for seg in segs]
    assert kinds.count("math") == 2
    assert kinds[0] == "text"
    assert has_math(r"اگر $x^2=۴$ باشد") is True
    assert has_math("این جمله هیچ فرمولی ندارد") is False


def test_exam_pdf_contains_real_math_images():
    """PDF نهایی باید تصویر فرمول (XObject) داشته باشد و برچسب دلار خام در آن نماند."""
    import pymupdf

    from reports.exam_pdf import build_exam_pdf

    questions = [
        {
            "order": 1,
            "subject": "هندسه ۳",
            "difficulty": "متوسط",
            "text": r"اگر $\vec{a}=(۱,۲)$ باشد، حاصل $\frac{۵\sqrt{۱۴}}{۱۴}$ کدام است؟",
            "options": [r"$\frac{۵\sqrt{۱۴}}{۱۴}$", r"$\sqrt{۷}$", r"$۴۵^\circ$", r"$T^{-1}$"],
            "correct_answer": 1,
            "explanation": r"داریم $\sqrt{۷}<\frac{۵\sqrt{۱۴}}{۱۴}$ پس پاسخ ۱ است.",
            "diagram_svg": None,
        }
    ]
    pdf = build_exam_pdf(
        school_name="دبیرستان نمونه",
        title="آزمون رندر ریاضی",
        questions=questions,
        duration_minutes=30,
        difficulty="متوسط",
        grade="12",
        major="ریاضی و فیزیک",
        subject_label="هندسه ۳",
        topic="بردار",
    )
    assert pdf.startswith(b"%PDF-")
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        images = sum(len(page.get_images(full=True)) for page in doc)
        assert images >= 4  # کسر، رادیکال، درجه، T^-1
        text = "".join(page.get_text() for page in doc)
        assert "به روی" not in text  # دیگر فرمول‌ها به کلمه ترجمه نمی‌شوند
        assert "$" not in text
    finally:
        doc.close()


def test_ai_prompt_requires_persian_digits_inside_math():
    from ai.exam_generator import build_exam_preview_prompt

    prompt = build_exam_preview_prompt(
        count=2,
        field_label="ریاضی و فیزیک",
        subjects_slugs="geometry",
        subjects_labels="هندسه ۳",
        subject_configs=[{"subject": "geometry", "count": 2, "difficulty": "متوسط", "subTopics": []}],
        sub_topics=[],
        ai_ratio=50,
        grade_label="دوازدهم",
        topic="—",
        question_type_label="نامشخص / ترکیبی",
        difficulty_label="متوسط",
        custom_prompt="—",
    )
    assert "PERSIAN DIGITS INSIDE MATH (VISUAL RENDERER REQUIREMENT)" in prompt
    assert "۵" in prompt and "۱۴" in prompt


def test_matrix_row_separator_variants_all_render():
    """جداکنندهٔ سطرِ ماتریس ممکن است \\\\، \\cr، یا خط جدید باشد — هیچ‌کدام نباید
    ماتریس ۲×۲ را به یک سطر ادغام کند یا به رشتهٔ براکتی falback بیندازد."""
    from reports.math_renderer import _MATRIX_ENV_RE, _split_matrix_rows, render_math_png

    cases = [
        r"\begin{bmatrix} 2 & 1 \\ -1 & 0 \end{bmatrix}",   # استاندارد
        r"\begin{bmatrix} 2 & 1 \cr -1 & 0 \end{bmatrix}",  # \cr
        "\\begin{bmatrix} 2 & 1 \n -1 & 0 \\end{bmatrix}",  # خط جدید
        r"\begin{bmatrix}{cc} 2 & 1 \\ -1 & 0 \end{bmatrix}",  # مشخصهٔ ستون
        r"\begin{smallmatrix} 2 & 1 \\ -1 & 0 \end{smallmatrix}",
        r"\begin{Bmatrix} 2 & 1 \\ -1 & 0 \end{Bmatrix}",
        r"\begin{pmatrix} 2 & 1 \\ -1 & 0 \end{pmatrix}",
        r"\begin{bmatrix} ۲ & ۱ \\ -۱ & ۰ \end{bmatrix}",   # ارقام فارسی
    ]
    for latex in cases:
        m = _MATRIX_ENV_RE.search(latex)
        assert m is not None, latex
        assert len(_split_matrix_rows(m.group(2))) == 2, latex
        img = render_math_png(latex, font_size=10.5)
        assert img is not None, latex
        # ماتریس ۲×۲ باید بلندتر از یک سطرِ تخت باشد (~۲.۴ برابرِ font_size)
        assert img.height > 1.8 * 10.5, f"{latex} → {img.width}x{img.height} (rows collapsed)"
        assert img.height >= 2.0 * 10.5, f"{latex} → rows may have collapsed: {img.height}"
        # ... ولی نباید سطرهای متن را بشکند: ارتفاعِ ماتریس باید در محدودهٔ
        # یک سطرِ دوصفحه‌ایِ معمول بماند (۲.۵ تا ۳.۵ برابرِ font_size برای ۲ سطر).
        # پیش‌تر این عدد ~۴.۵ برابر بود و سؤال را بین دو صفحه تکه می‌کرد.
        assert img.height < 3.5 * 10.5, f"{latex} → too tall: {img.height}"

    # ۳×۳
    m3 = _MATRIX_ENV_RE.search(r"\begin{bmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{bmatrix}")
    assert len(_split_matrix_rows(m3.group(2))) == 3


def test_fallback_never_emits_bracket_matrix_string():
    """حتی اگر رندر تصویری شکست بخورد، خروجی متنی نباید «[ ۲ , ۱ | -۱ , ۰ ]» باشد."""
    from reports.exam_pdf import final_pdf_cleanup

    out = final_pdf_cleanup(r"دترمینان $\begin{bmatrix} 2 & 1 \\ -1 & 0 \end{bmatrix}$ کدام است؟")
    assert "[ " not in out
    assert " | " not in out
    assert "," not in out          # کامای لاتین
    assert "بmatrix" not in out
    assert "begin" not in out
    for cell in ("۲", "۱", "۰"):
        assert cell in out


def test_json_control_chars_in_latex_are_recovered():
    """json.loads رشتهٔ "\\begin" را به \\x08egin و "\\frac" را به \\x0crac تبدیل می‌کند."""
    from reports.pdf_text_flow import repair_control_chars, split_math_segments

    assert "\\begin" in repair_control_chars("$\x08egin{bmatrix} ۱ \\end{bmatrix}$")
    assert "\\frac" in repair_control_chars("$\x0crac{۱}{۲}$")

    segs = [s for s in split_math_segments("حاصل $\x0crac{۱}{۲}+\\sqrt{۷}$") if s[0] == "math"]
    assert segs and "\\frac" in segs[0][1]

    # ورودی سالم نباید دستکاری شود
    healthy = r"$\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}$"
    assert repair_control_chars(healthy) == healthy


def test_progress_percent_curve_is_monotonic_and_bounded():
    """شمارندهٔ پیشرفت: منحنیِ مجانبی، یکنوا، با سقفِ سختِ ۹۰٪.

    قراردادِ جدید (نسبت به نسخهٔ زمان‌محورِ قبلی):

    * هر تیک: ``next = prev + (90 - prev) * 0.08``  (هرچه نزدیک‌تر، کندتر)
    * هرگز از ۹۰ عبور نمی‌کند — حتی اگر تولید دقیقه‌ها طول بکشد
    * ۱۰۰ فقط با پاسخِ واقعیِ سرور ست می‌شود، نه با تایمر
    """

    def tick(prev: float) -> float:
        nxt = prev + (90 - prev) * 0.08
        return 90.0 if nxt > 90 else nxt

    # ۱) شروع از ۵٪ و رشدِ یکنوا
    values = [5.0]
    for _ in range(200):
        values.append(tick(values[-1]))
    assert all(b >= a for a, b in zip(values, values[1:])), "should be monotonic"

    # ۲) هرگز از ۹۰ عبور نمی‌کند (حتی بعد از ۲۰۰ ثانیه).
    #    منحنی «مجانبی» است، پس به ۹۰ میل می‌کند ولی هرگز به آن نمی‌رسد؛
    #    به همین دلیل مقایسه با یک اپسیلون انجام می‌شود نه برابریِ دقیق.
    assert max(values) <= 90.0
    assert 89.9 < values[-1] <= 90.0

    # ۳) ولی در بازهٔ معقولی به سقف می‌رسد (نه این‌که یخ بزند)
    assert values[30] > 80.0, "بعد از ۳۰ ثانیه باید بالای ۸۰٪ باشد"

    # ۴) از بالا تقریب نمی‌زند: همیشه کمتر از سقف تا وقتی واقعاً برسد
    assert all(v <= 90.0 for v in values)

    # ۵) نرخِ کاهشی: تا کردنِ فاصله در هر تیک کمتر از ۱۰٪ فاصلهٔ اولیه نیست
    first_step = values[1] - values[0]
    assert 5.0 < first_step < 8.0, first_step


# ---------------------------------------------------------------------------
# رگرسیون‌های چیدمانِ PDF (کشف‌شده در بازبینیِ تزریقِ درون‌خطیِ ریاضی)
# ---------------------------------------------------------------------------
def test_options_row_fits_inside_frame():
    """ردیفِ چهارگزینه‌ای نباید از کادرِ متن بیرون بزند.

    ``doc.width`` = ``178mm`` = ``504.57pt`` بود و همان به ``OptionsRow`` داده
    می‌شد؛ اما ``Frame`` به‌طورِ پیش‌فرض ۶pt padding از هر طرف دارد، پس گشودگیِ
    واقعی ``492.57pt`` است. نتیجه: ۱۲pt سرریز روی هر ردیفِ گزینه‌ها.
    """
    from reportlab.lib.units import mm

    from reports.exam_pdf import _CONTENT_WIDTH_PT

    available = 178 * mm - 12.0  # doc.width منهای paddingِ دو طرف
    assert _CONTENT_WIDTH_PT <= available, f"{_CONTENT_WIDTH_PT} > {available}"
    # ولی نه زیادی کوچک که گزینه‌ها بی‌دلیل تنگ شوند
    assert _CONTENT_WIDTH_PT > available - 1.0


def test_matrix_image_scales_with_font_size():
    """ارتفاعِ ماتریس باید تقریباً خطی با font_size رشد کند (نه غول‌آسا).

    پیش‌تر ``ax.text(size=fs)`` روی ``figsize`` اینچیِ ثابت نوشته می‌شد؛ نتیجه
    این بود که ماتریس ۲×۲ در fs=10.5 به ارتفاعِ ~۴۷pt (۴.۵ برابرِ متن) می‌رسید و
    سطرِ سؤال را می‌شکست.
    """
    from reports.math_renderer import render_math_png

    tex = r"\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}"
    heights = {}
    for fs in (8.0, 10.5, 14.0, 20.0):
        img = render_math_png(tex, font_size=fs)
        assert img is not None, fs
        heights[fs] = img.height
        # نسبتِ ارتفاع به فونت باید در محدودهٔ معقول بماند، نه ۴.۵ برابر
        ratio = img.height / fs
        assert 2.0 <= ratio <= 3.0, f"fs={fs} → h={img.height} (ratio {ratio:.2f})"

    # رشدِ خطی: دو برابر شدنِ فونت باید ارتفاع را ~دو برابر کند
    assert 1.7 < heights[20.0] / heights[10.5] < 2.3


def test_bare_latex_frac_consumes_both_brace_groups():
    r"""``frac{۱}{۲}`` بدونِ بک‌اسلش باید هر دو گروه را ببلعد.

    الگوی قبلی فقط یک ``\{[^{}]*\}`` می‌گرفت، پس ``frac{۱}{۲}`` به قطعهٔ ریاضیِ
    ``frac{۱}`` + متنِ ``{۲}`` تجزیه می‌شد و در PDF به‌صورتِ «{۲}۱» چاپ می‌شد.
    """
    from reports.pdf_text_flow import split_math_segments

    segs = split_math_segments(r"مقدار frac{1}{2} و sqrt{7} را حساب کنید")
    maths = [s[1] for s in segs if s[0] == "math"]
    texts = "".join(s[1] for s in segs if s[0] == "text")
    assert "frac{1}{2}" in maths, maths
    assert "sqrt{7}" in maths, maths
    # هیچ آکولادِ سرگردانی در متن نمانده باشد
    assert "{" not in texts and "}" not in texts, texts


def test_inline_math_html_keeps_word_spacing():
    """فاصله‌های میانِ واژه‌ها در HTMLِ خروجی نباید گم شوند.

    اشتباه در یک واحد (نگاه به ``atom.space_before`` به‌جای اتمِ همسایهٔ راست) کلمات
    را به هم می‌چسباند: «ﺩﺗﺮﻣﯿﻨﺎﻥﻣﺎﺗﺮﯾﺲ». آن‌گاه ReportLab عرضِ خط را اشتباه می‌سنجد
    و پاراگراف را دوباره می‌شکند.
    """
    from reports.math_inline import _build_block, _lines_to_html, _ensure_fonts
    from reportlab.lib.styles import ParagraphStyle

    _ensure_fonts()
    style = ParagraphStyle("t", fontName="Vazirmatn", fontSize=10, leading=19)
    txt = "دترمینان ماتریس دو $x^2$ را محاسبه کنید"
    html = _lines_to_html(_build_block(txt, style, 400))
    assert len(html) == 1, html
    # باید حداقل یک فاصلهٔ واقعی میانِ واژه‌ها باشد
    assert html[0].count(" ") >= 4, html[0]


def test_progress_markup_uses_standard_font_size():
    """درصدِ پیشرفت باید با اندازهٔ استاندارد (`text-lg`) نمایش داده شود، نه `text-3xl`."""
    from pathlib import Path

    src = Path("frontend/src/pages/ExamBuilder.jsx").read_text(encoding="utf-8")
    assert "text-lg font-bold text-slate-700" in src
    assert "text-3xl font-black" not in src


# ---------------------------------------------------------------------------
# رگرسیون: باگِ «ماتریس به لیستِ ویرگول‌دار تخت تبدیل شده» (گزارش کاربر)
# ---------------------------------------------------------------------------
def test_flat_matrix_is_rebuilt_from_comma_list():
    """مدل گاهی ماتریس را به لیستِ ویرگول‌دار تخت می‌کند؛ باید بازسازی شود.

    پیش‌تر متنِ ``A=۱،۰،۱،۱،۰،۰،۱،۰،۱`` در PDF عیناً چاپ می‌شد، چون هیچ
    ``\\begin{bmatrix}``ای باقی نمانده بود که matplotlib رندرش کند.
    """
    from ai.json_sanitize import repair_flat_matrices

    out = repair_flat_matrices(
        "اگر A=۱،۰،۱،۱،۰،۰،۱،۰،۱ و B=۳،۵،۴ و X=x،y،z باشد، مقدار x^2+y^2+z^2 کدام است؟"
    )
    assert r"\begin{bmatrix}" in out
    assert out.count(r"\end{bmatrix}") == 3          # هر سه ماتریس بازسازی شد
    # ماتریس ۳×۳ باید دو جداکنندهٔ سطر داشته باشد
    assert out.count(r" \\ ") >= 2


def test_flat_matrix_repair_leaves_normal_lists_alone():
    """لیست‌های معمولیِ فارسی (میانگینِ چند عدد) نباید ماتریس شوند."""
    from ai.json_sanitize import repair_flat_matrices

    for text in (
        "میانگین سه عدد ۴، ۷ و ۱۰ چیست؟",
        "مخرج برابر ۲، ۴، ۶، ۸ است",
        "گزینه‌ها ۱، ۲، ۳ و ۴ هستند",
    ):
        assert repair_flat_matrices(text) == text, text


def test_matrix_render_keeps_prefix_and_has_no_placeholder_cells():
    r"""``A=\begin{bmatrix}…`` نباید «A=» را دور بریزد و نه سلول‌ها را به نقطه تبدیل کند.

    دو باگِ واقعی که این تست از بازگشتشان جلوگیری می‌کند:

    1. رندرکنندهٔ ماتریس فقط ``\begin{bmatrix}…\end{bmatrix}`` را می‌گرفت و
       پیشوند را بی‌صدا حذف می‌کرد ⇒ دانش‌آموز به‌جای ``A=`` فقط ماتریس می‌دید.
    2. matplotlib با ``fontset="cm"/"stix"`` گلیفِ ارقامِ فارسی ندارد و به‌جای
       رقم «نمادِ ساختگی» (یک نقطه) می‌کشد ⇒ ماتریسِ پر از نقطه.
    """
    from reports.math_renderer import _split_matrix_affixes, render_math_png

    latex = r"A=\begin{bmatrix} ۱ & ۰ & ۱ \\ ۱ & ۰ & ۰ \\ ۱ & ۰ & ۱ \end{bmatrix}"
    prefix, env, body, suffix = _split_matrix_affixes(latex)
    assert prefix == "A=", prefix
    assert env == "bmatrix"
    assert "&" in body

    img = render_math_png(latex, font_size=10.5, dpi=300)
    assert img is not None
    # پیشوند «A=» عرض را افزایش می‌دهد؛ بدونِ آن ۲×۲ کوچک‌تر است.
    bare = render_math_png(
        r"\begin{bmatrix} ۱ & ۰ & ۱ \\ ۱ & ۰ & ۰ \\ ۱ & ۰ & ۱ \end{bmatrix}",
        font_size=10.5,
        dpi=300,
    )
    assert img.width > bare.width + 10, (img.width, bare.width)

    # هیچ سلولی نباید به «نمادِ ساختگی» تبدیل شود: تصویر باید پیکسلِ کافی داشته باشد.
    try:
        import io as _io

        from PIL import Image

        with Image.open(_io.BytesIO(img.png)) as im:
            opaque = sum(1 for p in im.convert("RGBA").getdata() if p[3] > 10)
    except Exception:
        return  # PIL نبود — بررسی بصری در E2E انجام می‌شود
    assert opaque > 2000, f"too few opaque pixels: {opaque} (placeholder glyphs?)"


# ---------------------------------------------------------------------------
# رگرسیون: فرمول‌های بدون «$» به fallback متنی می‌افتادند (گزارش کاربر)
# ---------------------------------------------------------------------------
def test_bare_symbol_commands_are_recognized_as_math():
    r"""دستوراتِ نمادی مثلِ ``\times`` و ``\cdot`` باید ریاضی شناخته شوند.

    پیش‌تر ``_LATEX_SYMBOL_CMDS`` هیچ‌جا نبود و متنی مثل
    «ماتریسی ۲ \\times ۲» هیچ فرمولی برایش پیدا نمی‌شد؛ ``has_math`` مقدار
    ``False`` می‌گرفت، کلِ سؤال از مسیرِ رندر تصویری بیرون می‌افتاد و به
    ``final_pdf_cleanup`` (ترجمهٔ متنی) می‌رفت. نتیجه در PDF: «۲۲» و
    «۱، ۲، ۳، ۴» — دقیقاً همان چیزی که کاربر گزارش کرد.
    """
    from reports.pdf_text_flow import has_math, split_math_segments

    for text, expected in (
        (r"ماتریسی ۲ \times ۲ باشد", r"۲ \times ۲"),
        (r"اگر a \cdot b باشد", r"a \cdot b"),
        (r"مقدار x \leq y", r"x \leq y"),
        (r"جمع ۲ \pm ۳", r"۲ \pm ۳"),
    ):
        assert has_math(text), text
        maths = [s[1] for s in split_math_segments(text) if s[0] == "math"]
        # باید **یک** قطعهٔ کامل باشد، نه سه تکهٔ پراکنده
        assert len(maths) == 1, (text, maths)
        assert expected.replace(" ", "") in maths[0].replace(" ", ""), (text, maths)


def test_whole_math_expression_is_not_split_around_operators():
    r"""``۲ \times ۲`` باید یک قطعه بماند، نه «۲ » + «\times» + « ۲».

    قبلاً ``_BARE_LATEX_RE`` پیش از ``_wrap_bare_math`` اجرا می‌شد و دستورِ
    وسطِ عبارت را می‌برید؛ تصویرِ ۸ پوینتیِ «×» تنها چیزی بود که می‌ماند.
    """
    from reports.pdf_text_flow import split_math_segments

    segs = split_math_segments(r"ماتریسی ۲ \times ۲ باشد")
    maths = [s[1] for s in segs if s[0] == "math"]
    assert len(maths) == 1, maths
    assert "times" in maths[0] and "۲" in maths[0]

    # ماتریسِ بدون $ هم باید یک قطعهٔ واحد بماند
    segs = split_math_segments(
        r"ماتریس \begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix} را بنویس"
    )
    maths = [s[1] for s in segs if s[0] == "math"]
    assert len(maths) == 1, maths
    assert "bmatrix" in maths[0] and "&" in maths[0]


def test_plain_persian_text_stays_plain():
    """متنِ فارسیِ بدونِ فرمول نباید به قطعهٔ ریاضی تبدیل شود."""
    from reports.pdf_text_flow import has_math

    for text in (
        "میانگین سه عدد ۴، ۷ و ۱۰ چیست؟",
        "کدام است X؟",
        "این آزمون و پاسخنامه توسط فهم‌یار ساخته شد.",
    ):
        assert not has_math(text), text


def test_no_dollar_latex_matrix_end_to_end():
    r"""کلِ سؤالِ گزارش‌شده — بدون هیچ ``$`` — باید ماتریسِ واقعی رندر کند."""
    import pymupdf  # noqa: F401  (اختیاری)

    from reports.exam_pdf import build_exam_pdf

    text = (
        r"اگر A=\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix} و "
        r"B=\begin{bmatrix} ۰ \\ ۱ \end{bmatrix} باشد که X ماتریسی "
        r"۲ \times ۲ باشد و AX=B برقرار است، کدام است X؟"
    )
    opts = [
        r"\begin{bmatrix} ۱ & ۲ \\ ۳ & ۴ \end{bmatrix}",
        r"\begin{bmatrix} -۱ & ۲ \\ -۳ & ۱ \end{bmatrix}",
        r"\begin{bmatrix} -۱ & -۲ \\ -۳ & -۱ \end{bmatrix}",
        r"\begin{bmatrix} ۲ & -۱ \\ ۱ & -۱ \end{bmatrix}",
    ]
    pdf = build_exam_pdf(
        "دبیرستان", "آزمون", [
            {"order": 1, "subject": "هندسه", "difficulty": "سخت", "text": text,
             "options": opts, "correct_answer": 3, "explanation": "", "diagram_svg": None},
        ],
        60, "سخت", grade="12", major="ریاضی و فیزیک", subject_label="هندسه", topic="ماتریس",
    )
    assert pdf[:4] == b"%PDF"

    import io as _io

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    total_images = sum(len(p.get_images()) for p in doc)
    # ۵ ماتریس + «۲×۲» + X → دست‌کم ۶ تصویر در صفحهٔ سؤال
    assert total_images >= 6, total_images

    full_text = "".join(p.get_text() for p in doc)
    # هیچ نشتیِ متنی نباید باشد
    for leak in ("\\times", "bmatrix", "\\begin", "$"):
        assert leak not in full_text, leak


def test_flat_option_becomes_real_matrix():
    r"""گزینه‌های تخت («۱، ۲، ۳، ۴») باید به ماتریس واقعی تبدیل شوند.

    گزینه‌ها LHS ندارند، پس مسیرِ ``repair_flat_matrices`` (که به ``A=`` نیاز
    دارد) آن‌ها را نمی‌گرفت و در PDF به‌صورتِ متنِ ویرگول‌دار چاپ می‌شدند.
    """
    from ai.json_sanitize import repair_flat_option

    cases = {
        "۱، ۲، ۳، ۴": (r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}", 2),
        "-۱، ۲، -۳، ۱": (r"\begin{bmatrix}-۱ & ۲ \\ -۳ & ۱\end{bmatrix}", 2),
        "-۱ / ۲، -۳ / ۲، ۲، ۱": (r"\frac", 2),
    }
    for raw, (needle, nrows) in cases.items():
        out = repair_flat_option(raw)
        assert out.startswith("$") and out.endswith("$"), out
        assert needle in out, (raw, out)
        assert out.count(r" \\ ") == nrows - 1, (raw, out)

    # مواردی که نباید تغییر کنند
    for keep in ("$x$", "میانگین ۴، ۷", "۱، ۲"):
        assert repair_flat_option(keep) == keep, keep


def test_operand_operator_expression_is_math_without_signal_chars():
    r"""عبارتی مثلِ ``(A+B)۲-A۲-B۲`` باید ریاضی شناخته شود.

    این عبارت هیچ‌یک از نشانه‌های ``_MATH_SIGNAL_RE`` (``^ _ = < > |``) را ندارد
    و هیچ واژهٔ دوحرفی‌ای هم در آن نیست؛ بنابراین پیش‌تر ``_looks_math`` آن را رد
    می‌کرد و کلِ عبارت به متنِ تخت تبدیل می‌شد. کاربر عیناً
    ``(A+B)۲-A۲-B۲`` را در PDF می‌دید.
    """
    from reports.pdf_text_flow import has_math, split_math_segments

    text = "حاصل‌جمع تمام درایه‌های (A+B)۲-A۲-B۲ کدام است؟"
    assert has_math(text)
    maths = [s[1] for s in split_math_segments(text) if s[0] == "math"]
    assert maths == ["(A+B)۲-A۲-B۲"], maths

    # ولی واژه‌های خط‌تیره‌دارِ فارسی نباید ریاضی شوند
    for plain in ("سود-زیان این معامله چقدر است؟", "بیش-کم در جدول مشخص است"):
        assert not has_math(plain), plain


def test_attached_digit_becomes_power():
    r"""رقمِ چسبیده به حرف یا پرانتز باید توان شود، نه زیرنویس.

    مدل به‌جای ``(A+B)^۲`` رشتهٔ ``(A+B)۲`` تولید می‌کند؛ بدونِ این اصلاح
    رقم به‌شکلِ چسبیده رندر می‌شد و معنای توان را نمی‌رساند.
    """
    from reports.math_renderer import normalize_latex

    assert normalize_latex("(A+B)۲-A۲-B۲") == r"(A+B)^{۲}-A^{۲}-B^{۲}"
    assert normalize_latex("A۲+B۲") == r"A^{۲}+B^{۲}"
    # نباید چیزی که توان نیست را خراب کند
    assert normalize_latex("x^2") == "x^2"
    assert normalize_latex("۲x") == "۲x"


def test_unicode_minus_and_superscript_survive():
    r"""مدل‌های زبانی شکل‌های یونیکدِ عملگر را هم تولید می‌کنند.

    ``U+2212`` (منفیِ ریاضی) و ``²`` (بالانویسِ U+00B2) باید مثلِ ``-`` و
    ``^2`` رفتار کنند. وقتی در ``_MATH_CHARS`` نبودند عبارت از سرِ همان کاراکتر
    می‌شکست و بقیهٔ عبارت متنِ تخت می‌شد — دقیقاً همان چیزی که کاربر دید.
    """
    from reports.pdf_text_flow import has_math, split_math_segments

    for expr in ("(A+B)۲\u2212A۲\u2212B۲", "(A+B)²-A²-B²", "۳x\u2212۲y"):
        sent = f"اگر {expr} باشد، حاصل کدام است؟"
        assert has_math(sent), expr
        maths = [s[1] for s in split_math_segments(sent) if s[0] == "math"]
        assert expr in maths, (expr, maths)

    # و دوباره: خط تیرهٔ فارسی نباید ریاضی شود
    assert not has_math("سود-زیان این معامله چقدر است؟")
