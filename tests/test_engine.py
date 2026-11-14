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
    """sanitize_json_string قرارداد است و باید دست‌نخورده بماند."""
    from ai.json_sanitize import sanitize_json_string

    raw = r'[{"id": 1, "text": "مقدار $\$\sqrt{7}\$$ و $\theta$ و $\vec{a}$ و $\frac{1}{2}$ و \cos^{-1}(4/9) چیست؟"}]'
    parsed = sanitize_json_string(raw)
    txt = parsed[0]["text"]
    assert r"\sqrt{7}" in txt
    assert r"\theta" in txt
    assert r"\vec{a}" in txt
    assert r"\frac{1}{2}" in txt
    assert "$\$" not in txt


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


def test_json_control_chars_in_latex_are_recovered():
    """json.loads رشتهٔ "\\begin" را به \x08egin و "\\frac" را به \x0crac تبدیل می‌کند.

    بازیابی از عهدهٔ MathText (سمت فرانت‌اند) و sanitize_json_string است؛ موتور
    PDFِ قدیم حذف شد و این تست دیگر به آن وابسته نیست.
    """
    from ai.json_sanitize import sanitize_json_string

    parsed = sanitize_json_string(r'[{"text": "حاصل $\frac{۱}{۲}+\sqrt{۷}$"}]')
    assert r"\frac" in parsed[0]["text"]
    assert r"\sqrt" in parsed[0]["text"]


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


