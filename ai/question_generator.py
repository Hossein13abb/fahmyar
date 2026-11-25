"""تولید سؤال «درست‌به‌وقت» (JIT) با محدودیت‌های سختِ پرامپت.

قواعد تضمین‌شده در پرامپت:
  ۱) سؤال MUST یک پدیده/موقعیت واقعی را مطرح کند (نه سؤال انتزاعی کتابی)
  ۲) همهٔ داده‌های لازم (مواد، شرایط، مشاهدات) در متن سؤال داده شود
  ۳) نامِ مفهوم هدف در سؤال دیده نشود
  ۴) پاسخ یا مسیر استدلالیِ مورد انتظار افشا نشود
  ۵) مشاهدات از تفسیرها جدا باشند («محلول کمرنگ شد» نه «ماده کاهیده شد»)
  ۶) خروجی فقط JSON ساخت‌یافته باشد

خروجی JSON: question_text, phenomenon_description, required_data, rubric,
             mapped_propositions, mapped_misconceptions (+ question_type, difficulty, cognitive_type)
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from models.concept import Concept
from models.question import Question, QUESTION_TYPES
from ai.model_abstraction import get_router, AIProviderError
from ai.json_sanitize import extract_json_object
from ai.exam_generator import FALLBACK_FREE_MODELS, JSON_LATEX_ESCAPING_RULE


class QuestionGenerationError(Exception):
    pass


BEHAVIOR_FA = {
    "recall": "یادآوری و بازشناسی (دانش پایه)",
    "explain": "توضیح چراییِ یک پدیده (استدلال علّی)",
    "convert_representation": "تبدیل بین نمایش‌ها (شکل ↔ فرمول ↔ کلام)",
    "identify_conditions": "تشخیص شرایط و استثناها",
    "predict": "پیش‌بینی نتیجهٔ یک تغییر",
    "solve": "حل مسئله با داده‌های مشخص",
    "apply_novel": "به‌کارگیری در موقعیت کاملاً نو",
    "identify_error": "شناسایی و نقد خطای یک پاسخ/استدلال دیگر",
    "connect": "اتصال مفهوم به مفاهیم دیگر (بین‌درسی)",
}

_SYSTEM = r"""شما یک طراح سؤال تشخیصیِ خبره برای سیستم «فهم‌یار» هستید.
تنها یک سؤال تشخیصی به زبان فارسی طراحی می‌کنید که هدفش سنجیدنِ فهمیدن است، نه حفظ کردن.

قواعد قطعی و غیرقابل‌نقض:
1. سؤال حتماً باید یک پدیده یا موقعیت واقعی مطرح کند (آزمایشگاه، کارگاه، زندگی روزمره، طبیعت).
2. همهٔ داده‌های لازم (مواد، شرایط، مقادیر، مشاهدات) در متن سؤال بیاید؛ دانش‌آموز نباید به منبع دیگری نیاز داشته باشد.
3. نامِ مفهوم هدف و اصطلاح فنیِ همان مفهوم در متن سؤال نیاید — دانش‌آموز نباید بفهمد کدام بخش درس سنجیده می‌شود.
4. پاسخ، نیمه‌پاسخ یا مسیر استدلالیِ مورد انتظار در سؤال لو نرود.
5. مشاهدات را از تفسیرها جدا کنید: بنویسید «محلول کمرنگ شد» نه «ماده کاهیده شد». هرگز تفسیر علمی را به‌جای مشاهده جا نزنید.
6. خروجی باید فقط یک شیء JSON معتبر باشد — بدون هیچ متن اضافه، بدون توضیح، بدون Markdown و بدون ```.
7. سؤال نباید بله/خیر باشد؛ پاسخ باید نیازمند استدلال باشد.
8. سؤال تکراریِ پاسخ‌های قبلی نباشد.

ساختار دقیق خروجی (همهٔ کلیدها الزامی):
{
  "question_text": "متن کامل سؤال به زبان فارسی",
  "phenomenon_description": "توصیف کوتاه موقعیتِ واقعی (فقط مشاهده)",
  "required_data": ["داده ۱", "داده ۲"],
  "question_type": "phenomenon_explain | compare_explanations | predict | categorize | error_identify | novel_application",
  "difficulty": "easy | medium | hard",
  "cognitive_type": "recall | conceptual | computational | combined",
  "rubric": {
    "correct_reasoning": "استدلال درست چیست (برای مصحح/تحلیل‌گر، نه برای دانش‌آموز)",
    "misconception_indicators": {"نشانهٔ بدفهمی به‌صورت نقل‌قول یا رفتار": "چرا این نشانهٔ آن بدفهمی است"},
    "partial_credit_signs": ["نشانهٔ فهمیدنِ ناقص"],
    "non_conceptual_errors": ["خطای صرفاً محاسباتی/بی‌دقتی که نباید به‌عنوان نفهمی تفسیر شود"]
  },
  "mapped_propositions": ["گزارهٔ ۱ که این سؤال می‌سنجد"],
  "mapped_misconceptions": ["بدفهمیِ هدف که این سؤال می‌تواند آشکارش کند"]
}

CRITICAL MATH FORMATTING RULE:
Every single mathematical symbol, formula, vector, power, matrix, variable, or inverse function MUST be enclosed in inline math `$ ... $` or block math `$$ ... $$`.
Examples of CORRECT formatting:
- Inverse trig / functions: `$\cos^{-1}\left(\frac{4}{9}\right)$` (NOT `cos^-1(4/9)`)
- Matrix inverses & powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)
- Vectors & subscripts: `$\vec{n}_1 = (1, 2, 2)$` (NOT `n_1=(1,2,2)`)
- Matrices: `$$\begin{bmatrix} 2 & 1 \\ 1 & 3 \end{bmatrix}$$`
Never output raw LaTeX commands outside of `$` or `$$` delimiters!
Even inside LaTeX blocks, you MUST use Persian numbers (۰۱۲۳۴۵۶۷۸۹). For example: $۲x + ۵ = ۱۲$.
CRITICAL JSON ESCAPING RULE: You MUST double-escape all LaTeX commands in the JSON. Write \\begin{bmatrix}, \\frac, \\sqrt, \\theta, \\vec. Never use a single backslash for LaTeX commands, and NEVER escape the $ delimiter itself (write $ ... $, not \$).
CRITICAL SYLLABUS RULE (Nezam Jadid - نظام جدید 1397 onwards):
You MUST generate questions exclusively compliant with the updated Iranian 6-3-3 high school textbooks published AFTER 1397 (2018).

BANNED NEZAM-GHADIM TOPICS (STRICTLY FORBIDDEN):
- Integrals (انتگرال) in Hesaban 2.
- General & Standard Equations of Ellipse/Hyperbola (معادله بیضی و هذلولی) in Geometry 3 - Only focus on the definition/focal properties.
- Matrix Inverses of 3x3 matrices (معکوس ماتریس 3x3).
- Obsolete physics topics removed post-1397.

Only include topics explicitly present in current 10th, 11th, and 12th grade Iranian textbooks.
Do NOT use these concepts under any circumstances.
SVGs are OPTIONAL. Set `diagram_svg` to `null` if the question can be solved without a picture (e.g., standard algebra, matrices). NEVER attempt to draw precise intersecting coordinates (like a line tangent to a circle) because your coordinate math will be wrong. Only draw simple block diagrams, circuits, or abstract isolated shapes. If you are unsure about the visual alignment, return `null`.
STRICT DIFFICULTY CALIBRATION:
- آسان (Easy): Any question requiring direct substitution into a known formula (e.g., dot product for angle between vectors, single-step vector math). NEVER label a plug-and-chug question as Hard.
- متوسط (Medium): Questions requiring 2 steps or basic concept connection.
- سخت (Hard): Questions requiring deep multi-step synthesis or hidden traps.
"""


def _build_prompt(
    concept: Concept,
    target_proposition: str,
    target_misconception: Optional[str],
    behavior: str,
    previous_responses: list[str],
    cross_subject: bool,
) -> str:
    behavior_desc = BEHAVIOR_FA.get(behavior, behavior)
    previous = "\n".join(f"- {r[:300]}" for r in (previous_responses or [])[-5:]) or "(هیچ‌کدام)"
    cross_note = (
        "این سؤال باید موقعیت بین‌درسی باشد (مثال: کاربرد ابزار ریاضی در فیزیک/شیمی)."
        if cross_subject
        else "سؤال می‌تواند درون‌درسی باشد."
    )
    misconception_block = target_misconception or "(بدون بدفهمیِ هدف — فقط گزارهٔ مورد نظر)"
    return f"""{_SYSTEM}

=== مفهوم ===
<<<CONCEPT>>>{concept.name} ({concept.subject} — پایهٔ {concept.grade})<<<END>>>

=== گزارهٔ هدف (دانش‌آموز نباید این را ببیند) ===
<<<PROPOSITION>>>{target_proposition}<<<END>>>

=== بدفهمیِ هدف (دانش‌آموز نباید این را ببیند) ===
<<<MISCONCEPTION>>>{misconception_block}<<<END>>>

=== رفتار شناختیِ هدف ===
{behavior} → {behavior_desc}
{cross_note}

=== رفتارها و بدفهمی‌های رایج این مفهوم (فقط برای راهنمایی شما) ===
رفتارهای هدف مفهوم: {", ".join(concept.target_behaviors or [])}
بدفهمی‌های رایج: {json.dumps(concept.common_misconceptions or [], ensure_ascii=False)[:1500]}

=== پاسخ‌های قبلی این دانش‌آموز (از آن‌ها دوری کن) ===
{previous}

اکنون فقط JSON خروجی را بده."""


# استخراج مقاوم JSON — پیاده‌سازی مشترک در ai/json_sanitize.py
_extract_json = extract_json_object



def _stringify_item(item) -> str:
    """گزاره/بدفهمی ممکن است متن ساده یا دیکشنریِ غنی باشد — همیشه رشتهٔ خوانا برمی‌گرداند."""
    if isinstance(item, dict):
        for key in ("misconception", "text", "label", "proposition", "root_cause", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item or "").strip()


_LATIN_RUN_RE = re.compile(r"[A-Za-z]+")


_FA_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_EN_WORD_RE = re.compile(r"[A-Za-z]{4,}")   # کلمهٔ انگلیسیِ واقعی (فرمول‌ها و نمادهای تک‌حرفی مستثنا)


_LATEX_BLOCK_RE = re.compile(r"\$\$[\s\S]*?\$\$|\$[^$]*\$|\\[A-Za-z]+(?:\{[^}]*\})?")


def is_persian_text(text) -> bool:
    """آیا متن، فارسی است؟ (فرمول‌های LaTeX مانند $...$ و $$...$$ و نمادهای علمی کوتاه استثنا هستند)"""
    s = str(text or "").strip()
    if not s:
        return False
    # حذف بلوک‌های فرمول LaTeX پیش از بررسی کلمات انگلیسی
    s_no_math = _LATEX_BLOCK_RE.sub(" ", s)
    fa = len(_FA_SCRIPT_RE.findall(s))
    if fa == 0:
        return False
    if _EN_WORD_RE.search(s_no_math):
        return False
    latin = sum(len(m.group(0)) for m in _LATIN_RUN_RE.finditer(s_no_math))
    return latin <= fa


# ══════════════ اعتبارسنجی هندسی SVG ══════════════
_SVG_ATTR_RE = lambda name: re.compile(rf'{name}\s*=\s*"([^"]*)"')


def _svg_attr(tag: str, name: str, default=None):
    m = _SVG_ATTR_RE(name).search(tag)
    return m.group(1) if m else default


def _svg_float(tag: str, name: str, default: float = 0.0) -> float:
    try:
        return float(_svg_attr(tag, name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _dist_point_seg(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = x1 + t * dx, y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _dist_bbox_seg(x0: float, y0: float, x1: float, y1: float, ax: float, ay: float, bx: float, by: float) -> float:
    """فاصلهٔ یک مستطیل (لیبل) تا پاره‌خط — با نمونه‌برداری از نقاطِ داخل/لبهٔ مستطیل."""
    pts = [(ax, ay), (bx, by)]
    for _ in range(40):
        t = _ / 39
        pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    best = float("inf")
    for px, py in pts:
        # نقطهٔ بیرون از مستطیل → فاصلهٔ مستقیم؛ داخل → ۰
        dx = max(x0 - px, 0.0, px - x1)
        dy = max(y0 - py, 0.0, py - y1)
        best = min(best, (dx * dx + dy * dy) ** 0.5)
    return best


def svg_geometry_ok(svg: str) -> bool:
    """قانون عدم هم‌انباشتگی: لیبل‌های <text> باید حداقل ۲۰ پیکسل از هر خط/کادر فاصله داشته باشند.

    - فاصلهٔ bbox هر <text> تا هر <line>/<rect>/<circle>/هر پاره‌خطِ <polyline> باید ≥ ۲۰ باشد.
    - text-anchor / x / y / font-size خوانده می‌شود؛ عرض متن تقریبی محاسبه می‌شود.
    """
    s = svg or ""
    shapes = []  # (kind, geometry)
    for m in re.finditer(r"<line\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        shapes.append(("seg", (_svg_float(t, "x1"), _svg_float(t, "y1"), _svg_float(t, "x2"), _svg_float(t, "y2"))))
    for m in re.finditer(r"<rect\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        x, y = _svg_float(t, "x"), _svg_float(t, "y")
        w, h = _svg_float(t, "width"), _svg_float(t, "height")
        shapes.append(("rect", (x, y, x + w, y + h)))
    for m in re.finditer(r"<circle\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        cx, cy, r = _svg_float(t, "cx"), _svg_float(t, "cy"), _svg_float(t, "r")
        shapes.append(("circle", (cx, cy, r)))
    for m in re.finditer(r"<polyline\b[^>]*>", s, re.IGNORECASE):
        t = m.group(0)
        pts_raw = _svg_attr(t, "points", "") or ""
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", pts_raw)]
        coords = list(zip(nums[::2], nums[1::2]))
        for i in range(len(coords) - 1):
            shapes.append(("seg", (coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])))

    texts = []
    for m in re.finditer(r"<text\b([^>]*)>([^<]*)</text>", s, re.IGNORECASE):
        attrs, content = m.group(1), m.group(2)
        x = _svg_float(attrs, "x")
        y = _svg_float(attrs, "y")
        fs = _svg_float(attrs, "font-size", 14.0)
        anchor = (_svg_attr(attrs, "text-anchor", "start") or "start").lower()
        width = max(1, len(content.strip())) * fs * 0.62
        if anchor == "middle":
            x0 = x - width / 2
        elif anchor == "end":
            x0 = x - width
        else:
            x0 = x
        texts.append((x0, y - fs, x0 + width, y + fs * 0.25))  # bbox تقریبی لیبل

    for (tx0, ty0, tx1, ty1) in texts:
        for kind, geom in shapes:
            if kind == "seg":
                ax, ay, bx, by = geom
                if _dist_bbox_seg(tx0, ty0, tx1, ty1, ax, ay, bx, by) < 20.0:
                    return False
            elif kind == "rect":
                rx0, ry0, rx1, ry1 = geom
                dx = max(rx0 - tx1, tx0 - rx1, 0.0)
                dy = max(ry0 - ty1, ty0 - ry1, 0.0)
                if (dx * dx + dy * dy) ** 0.5 < 20.0:
                    return False
            elif kind == "circle":
                cx, cy, r = geom
                dx = max(tx0 - (cx - r), (cx + r) - tx1, 0.0)
                dy = max(ty0 - (cy - r), (cy + r) - ty1, 0.0)
                inner_hit = tx0 >= (cx - r) and tx1 <= (cx + r) and ty0 >= (cy - r) and ty1 <= (cy + r)
                if inner_hit:
                    return False
                if (dx * dx + dy * dy) ** 0.5 < 20.0:
                    return False
    return True


_CANONICAL_SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
_ALLOWED_SVG_TAGS = {"svg", "rect", "circle", "line", "polyline", "text"}
_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)")
_FENCE_RE = re.compile(r"^```(?:[a-zA-Z]*)\s*|\s*```\s*$", re.MULTILINE)


def _sanitize_diagram_svg(raw) -> str | None:
    """سلامتِ SVGِ مدل را تضمین می‌کند؛ اگر الزامات بخش گرافیک را نداشته باشد، آن را دور می‌ریزد (None).

    قواعد اجباری:
      - فقط تگ‌های svg/rect/circle/line/polyline/text مجازند (path مطلقاً ممنوع).
      - تگ بازشونده با ساختار کانونیکالِ استاندارد جایگزین می‌شود.
      - تگ </svg> باید وجود داشته باشد؛ اسکریپت/هندلرهای on* رد می‌شوند.
    """
    s = raw if isinstance(raw, str) else ""
    s = s.strip()
    if not s:
        return None
    s = _FENCE_RE.sub("", s)  # فنس‌های مارک‌داون را از دور SVG بردار
    start = s.find("<svg")
    end = s.rfind("</svg>")
    if start == -1 or end == -1 or end < start:
        return None  # SVG ناتمام یا خراب
    s = s[start:end + len("</svg>")]
    # حذف عناصر خطرناک/غیرمجازِ جفتی
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<foreignObject[\s\S]*?</foreignObject>", "", s, flags=re.IGNORECASE)
    if re.search(r"\son[a-zA-Z]+\s*=", s):   # هندلرهای رویداد
        return None
    if re.search(r"javascript:", s, flags=re.IGNORECASE):
        return None
    # فقط تگ‌های مجاز — هر تگ دیگر (path, g, ellipse, image, ...) کل SVG را نامعتبر می‌کند
    for m in _TAG_RE.finditer(s):
        if m.group(1).lower() not in _ALLOWED_SVG_TAGS:
            return None
    # نرمال‌سازی تگ بازشونده به ساختار کانونیکال
    s = re.sub(r"<svg[^>]*>", _CANONICAL_SVG_OPEN, s, count=1, flags=re.IGNORECASE)
    # قانون عدم هم‌انباشتگی: لیبل‌ها باید ≥۲۰px از خطوط/کادرها فاصله داشته باشند
    if not svg_geometry_ok(s):
        return None
    return s


_FALLBACK_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                 '<line x1="44" y1="228" x2="372" y2="228" stroke="black" stroke-width="2"/>'
                 '<line x1="44" y1="228" x2="44" y2="40" stroke="black" stroke-width="2"/>'
                 '<rect x="96" y="176" width="36" height="52" fill="none" stroke="black" stroke-width="2"/>'
                 '<rect x="182" y="116" width="36" height="112" fill="none" stroke="black" stroke-width="2"/>'
                 '<rect x="268" y="56" width="36" height="172" fill="none" stroke="black" stroke-width="2"/>'
                 '<text x="114" y="268" font-size="12" text-anchor="middle">A</text>'
                 '<text x="200" y="268" font-size="12" text-anchor="middle">B</text>'
                 '<text x="286" y="268" font-size="12" text-anchor="middle">C</text></svg>')


_FIG_REF_PATTERNS = [
    ("در نمودار زیر", "در این نمودار"),
    ("به نمودار زیر", "به این نمودار"),
    ("در شکل زیر", "در یک شکل مفروض"),
    ("به شکل زیر", "به یک شکل مفروض"),
    ("در مدار زیر", "در یک مدار"),
    ("به مدار زیر", "به یک مدار"),
    ("با توجه به نمودار زیر", "با توجه به این نمودار"),
    ("با توجه به شکل زیر", "با توجه به یک شکل مفروض"),
    ("با توجه به مدار زیر", "با توجه به یک مدار"),
    # عبارت‌های برهنه — بعد از الگوهای بلندتر
    ("نمودار زیر", "این نمودار"),
    ("شکل زیر", "یک شکل مفروض"),
    ("مدار زیر", "یک مدار"),
]


def _replace_missing_figure_refs(text: str) -> str:
    """اگر سؤالی diagram_svg ندارد، هیچ ارجاعی به «شکل/نمودار/مدار زیر» نباید بماند."""
    s = text or ""
    for a, b in _FIG_REF_PATTERNS:
        s = s.replace(a, b)
    return s


async def generate_test_booklet(concept, wrong_answer: dict | None = None) -> tuple[list["Question"], str, float]:
    """زنجیرهٔ ۵ مرحله‌ایِ فهم‌سنجی را تولید می‌کند.

    منطقِ قدیمیِ «دفترچهٔ ۹ سؤالی» حذف شده است. آن آزمون پنج لایهٔ ذهن را
    از هم تشخیص نمی‌داد و ارزیابیِ مقایسه‌ای (Cross-Check) بر آن ممکن نبود.

    خروجی: (فهرست Questionهای ذخیره‌نشده, model_name, cost_usd)
    همیشه دقیقاً ۵ ردیف برمی‌گردد — در بدترین حالت از قالبِ اضطراریِ قطعی.
    """
    from ai.stage_chain import generate_stage_chain

    return await generate_stage_chain(concept, wrong_answer=wrong_answer)


def _validate_payload(data: dict[str, Any], target_proposition: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise QuestionGenerationError("خروجی مدل دیکشنری نیست")
    question_text = str(data.get("question_text") or "").strip()
    if len(question_text) < 20:
        raise QuestionGenerationError("متن سؤال تولیدی بیش از حد کوتاه است")
    if not is_persian_text(question_text):
        raise QuestionGenerationError("صورت سؤال تولیدی فارسی نیست — خروجی رد شد")

    qtype = str(data.get("question_type") or "phenomenon_explain")
    if qtype not in QUESTION_TYPES:
        qtype = "phenomenon_explain"

    difficulty = str(data.get("difficulty") or "medium")
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    cognitive = str(data.get("cognitive_type") or "conceptual")
    if cognitive not in {"recall", "conceptual", "computational", "combined"}:
        cognitive = "conceptual"

    rubric = data.get("rubric") if isinstance(data.get("rubric"), dict) else {}
    rubric = {
        "correct_reasoning": str(rubric.get("correct_reasoning", "")),
        "misconception_indicators": rubric.get("misconception_indicators") if isinstance(rubric.get("misconception_indicators"), dict) else {},
        "partial_credit_signs": list(rubric.get("partial_credit_signs") or []),
        "non_conceptual_errors": list(rubric.get("non_conceptual_errors") or []),
    }
    # داده‌های موقعیت را هم در rubric نگه می‌داریم تا تحلیل‌گر ببیند
    if data.get("phenomenon_description"):
        rubric["phenomenon_description"] = str(data["phenomenon_description"])
    if data.get("required_data"):
        rubric["required_data"] = list(data["required_data"]) if isinstance(data["required_data"], list) else [str(data["required_data"])]

    mapped_props = data.get("mapped_propositions")
    if not isinstance(mapped_props, list) or not mapped_props:
        mapped_props = [target_proposition]

    mapped_misc = data.get("mapped_misconceptions")
    if not isinstance(mapped_misc, list):
        mapped_misc = []

    return {
        "text": question_text,
        "question_type": qtype,
        "difficulty": difficulty,
        "cognitive_type": cognitive,
        "rubric": rubric,
        "mapped_propositions": [str(p) for p in mapped_props],
        "mapped_misconceptions": [str(m) for m in mapped_misc],
    }


async def generate_diagnostic_question(
    concept: Concept,
    target_proposition: str,
    target_misconception: str | None,
    behavior: str,
    previous_responses: list[str],
    cross_subject: bool = False,
) -> Question:
    """یک سؤال تشخیصیِ JIT می‌سازد و شیء Question (تأیید نشده، pending) برمی‌گرداند.

    توجه: سؤال تولیدی به‌طور پیش‌فرض approval_status='pending' دارد و تا تأیید معلم
    فقط در همان جلسهٔ جاری استفاده می‌شود (در گزارش پروژه قید شده است).
    """
    router = get_router()
    prompt = _build_prompt(concept, target_proposition, target_misconception,
                           behavior, previous_responses, cross_subject)

    data: Optional[dict[str, Any]] = None
    model_name, cost = "", 0.0
    last_error: str | None = None

    for attempt in range(3):
        temp = 0.8 if attempt == 0 else 0.3
        extra = "" if attempt == 0 else "\n\nخروجی قبلی نامعتبر بود. فقط و فقط JSON خالص با بک‌اسلش‌های دوتایی (\\\\) برای LaTeX بده."
        candidate_model = FALLBACK_FREE_MODELS[attempt % len(FALLBACK_FREE_MODELS)] if attempt > 0 else None
        try:
            try:
                resp = await router.generate(
                    prompt + extra, "generate_question", temperature=temp, model_override=candidate_model
                )
            except TypeError:
                resp = await router.generate(prompt + extra, "generate_question", temperature=temp)
            model_name, cost = resp.model_name, resp.cost_usd
            data = _extract_json(resp.text)
            if data is not None:
                break
            last_error = "JSON استخراج نشد"
            print(f"[DiagnosticQuestion] Attempt {attempt + 1}/3 invalid JSON; retrying with next model...")
        except AIProviderError as exc:
            last_error = str(exc)
            print(f"[DiagnosticQuestion] Attempt {attempt + 1}/3 provider error: {exc}; retrying...")
        except Exception as exc:  # بودجه و غیره
            last_error = str(exc)
            break

    if data is None:
        raise QuestionGenerationError(f"تولید سؤال شکست خورد: {last_error}")

    try:
        payload = _validate_payload(data, target_proposition)
    except QuestionGenerationError:
        raise
    except Exception as exc:
        raise QuestionGenerationError(f"اعتبارسنجی خروجی ناموفق بود: {exc}") from exc

    return Question(
        concept_id=concept.id,
        text=payload["text"],
        question_type=payload["question_type"],
        difficulty=payload["difficulty"],
        cognitive_type=payload["cognitive_type"],
        rubric=payload["rubric"],
        mapped_propositions=payload["mapped_propositions"],
        mapped_misconceptions=payload["mapped_misconceptions"],
        source="ai_generated",
        approval_status="pending",  # طبق الزام: سؤالات AI هرگز بدون تأیید معلم منتشر نمی‌شوند
        ai_model_used=model_name,
        generation_cost_usd=cost,
    )
