"""قرارداد دادهٔ موتور فهم‌سنجی — اعتبارسنجی و نرمال‌سازیِ خروجیِ مدل.

مدل‌های زبانی تقریباً همیشه *کمی* از قالب منحرف می‌شوند: کلید را با فاصله
می‌نویسند، `correct_option_index` را یک‌پایه می‌دهند، یا `forbidden_words` را
null می‌گذارند. اگر این انحراف‌ها به لایهٔ UI برسند، کاربر خطای مبهم می‌بیند.
پس همه‌چیز این‌جا به یک شکلِ قطعی درمی‌آید و هر نقصی صریح گزارش می‌شود.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: پنج نوع سؤال، به ترتیبِ اجباری. ترتیب مهم است: سؤال ۲ باید *پیش از*
#: سؤال ۵ دیده شود تا تضادِ نقاب و شهود قابلِ شکار باشد.
QUESTION_TYPES: tuple[str, ...] = (
    "philosophy",
    "mask_mcq",
    "perturbation",
    "debugging",
    "feynman_synthesis",
)

QUESTION_TITLES: dict[str, str] = {
    "philosophy": "فلسفه و تصویر کلان",
    "mask_mcq": "تستِ استاندارد (لایهٔ نقاب)",
    "perturbation": "دستکاریِ سیستم",
    "debugging": "عیب‌یابیِ ساعتِ خراب",
    "feynman_synthesis": "چالشِ فاینمن (توضیح با دستِ بسته)",
}

#: برچسبِ کوتاهِ مرحله برای استپرِ فرانت‌اند.
STAGES: tuple[dict[str, Any], ...] = (
    {"index": 1, "type": "philosophy", "label": "فلسفه", "title": QUESTION_TITLES["philosophy"]},
    {"index": 2, "type": "mask_mcq", "label": "تست", "title": QUESTION_TITLES["mask_mcq"]},
    {"index": 3, "type": "perturbation", "label": "دستکاری", "title": QUESTION_TITLES["perturbation"]},
    {"index": 4, "type": "debugging", "label": "عیب‌یابی", "title": QUESTION_TITLES["debugging"]},
    {"index": 5, "type": "feynman_synthesis", "label": "فاینمن", "title": QUESTION_TITLES["feynman_synthesis"]},
)

MIN_FORBIDDEN_WORDS = 3
MAX_FORBIDDEN_WORDS = 8


class ContractError(ValueError):
    """خروجیِ مدل با قرارداد نمی‌خواند و قابلِ ترمیم نیست."""


# ---------------------------------------------------------------------------
# ساختارهای داده
# ---------------------------------------------------------------------------
@dataclass
class Blueprint:
    core_mechanism: str = ""
    target_misconceptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_mechanism": self.core_mechanism,
            "target_misconceptions": list(self.target_misconceptions),
        }


@dataclass
class GeneratedAssessment:
    blueprint: Blueprint
    questions: list[dict[str, Any]]
    model_name: str = ""
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_blueprint": self.blueprint.to_dict(),
            "questions": self.questions,
            "ai_model_used": self.model_name,
            "generation_cost_usd": self.cost_usd,
        }


@dataclass
class QuestionInsight:
    question_id: int
    cognitive_verdict: str = ""
    missing_gear: Optional[str] = None


@dataclass
class CrossCheckFinding:
    title: str
    type: str = "SYNERGY"
    description: str = ""


FINDING_TYPES = {
    "CONTRADICTION",
    "SYNERGY",
    "JARGON_VIOLATION",
    "BLUFF_DETECTED",
    "SLIP_RESOLVED",
}


@dataclass
class ClarificationData:
    contradicting_questions: list[int] = field(default_factory=list)
    mirror_prompt: str = ""


@dataclass
class EvaluationReport:
    mastery_status: str = "UNSTRUCTURED"
    persona_title: str = ""
    executive_summary: str = ""
    cross_check_findings: list[CrossCheckFinding] = field(default_factory=list)
    question_by_question_insight: list[QuestionInsight] = field(default_factory=list)
    actionable_advice: str = ""
    needs_clarification: bool = False
    clarification: Optional[ClarificationData] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_clarification": self.needs_clarification,
            "clarification_data": (
                {
                    "contradicting_questions": list(self.clarification.contradicting_questions),
                    "mirror_prompt": self.clarification.mirror_prompt,
                }
                if self.clarification
                else None
            ),
            "evaluation_report": {
                "mastery_status": self.mastery_status,
                "persona_title": self.persona_title,
                "executive_summary": self.executive_summary,
                "cross_check_findings": [
                    {"title": f.title, "type": f.type, "description": f.description}
                    for f in self.cross_check_findings
                ],
                "question_by_question_insight": [
                    {
                        "question_id": i.question_id,
                        "cognitive_verdict": i.cognitive_verdict,
                        "missing_gear": i.missing_gear,
                    }
                    for i in self.question_by_question_insight
                ],
                "actionable_advice": self.actionable_advice,
            },
        }


# ---------------------------------------------------------------------------
# کمکی‌ها
# ---------------------------------------------------------------------------
def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _as_int(value: Any, fallback: int) -> int:
    try:
        if isinstance(value, bool):
            return fallback
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_str(item)
        if text and text not in out:
            out.append(text)
    return out


# ---------------------------------------------------------------------------
# مرحلهٔ ۱ — تولیدِ آزمون
# ---------------------------------------------------------------------------
def normalize_generation(payload: Any) -> GeneratedAssessment:
    """خروجیِ خامِ مدل را به آزمونِ قطعیِ ۵ سؤالی تبدیل می‌کند.

    در برابرِ انحراف‌های رایج مقاوم است:
    * `topic_blueprint` غایب یا رشته‌ای باشد،
    * سؤال‌ها بی‌ترتیب یا با `type` اشتباه بیایند،
    * `correct_option_index` صفرپایه باشد یا رشته،
    * `forbidden_words` وجود نداشته باشد (برای Q5 از عنوان‌های عمومی پر می‌شود).
    """
    if not isinstance(payload, dict):
        raise ContractError("خروجیِ مدل یک شیءِ JSON نیست.")

    raw_blueprint = payload.get("topic_blueprint") or payload.get("blueprint") or {}
    if isinstance(raw_blueprint, str):
        blueprint = Blueprint(core_mechanism=raw_blueprint.strip())
    elif isinstance(raw_blueprint, dict):
        blueprint = Blueprint(
            core_mechanism=_clean_str(raw_blueprint.get("core_mechanism")),
            target_misconceptions=_clean_list(raw_blueprint.get("target_misconceptions")),
        )
    else:
        blueprint = Blueprint()

    raw_questions = payload.get("questions")
    if isinstance(raw_questions, dict):
        raw_questions = list(raw_questions.values())
    if not isinstance(raw_questions, list):
        raise ContractError("فیلدِ questions در خروجیِ مدل آرایه نیست.")

    # هر سؤال را بر اساسِ type (و در صورتِ نبود، بر اساسِ id یا ترتیب) در جای خودش بگذار.
    ordered: list[Optional[dict[str, Any]]] = [None] * len(QUESTION_TYPES)
    spare: list[dict[str, Any]] = []
    for position, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            continue
        qtype = _clean_str(item.get("type")).strip().lower()
        slot: Optional[int] = None
        if qtype in QUESTION_TYPES:
            slot = QUESTION_TYPES.index(qtype)
        else:
            qid = _as_int(item.get("id"), position + 1)
            if 1 <= qid <= len(QUESTION_TYPES):
                slot = qid - 1
        if slot is not None and ordered[slot] is None:
            ordered[slot] = item
        else:
            spare.append(item)

    # جاهای خالی را با سؤال‌های اضافی پر کن تا آزمونِ ناقص به UI نرسد.
    for slot, value in enumerate(ordered):
        if value is None:
            if not spare:
                break
            ordered[slot] = spare.pop(0)

    questions: list[dict[str, Any]] = []
    for index, qtype in enumerate(QUESTION_TYPES):
        raw = ordered[index]
        if raw is None:
            raise ContractError(
                f"سؤال شمارهٔ {index + 1} ({qtype}) در خروجیِ مدل نیامده است."
            )

        item: dict[str, Any] = {
            "id": index + 1,
            "type": qtype,
            "title": _clean_str(raw.get("title")) or QUESTION_TITLES[qtype],
            "question_text": _clean_str(raw.get("question_text") or raw.get("text")),
            "options": None,
            "forbidden_words": _clean_list(raw.get("forbidden_words")),
            "expected_logic": _clean_str(raw.get("expected_logic")),
        }
        if not item["question_text"]:
            raise ContractError(f"متنِ سؤال شمارهٔ {index + 1} خالی است.")

        if qtype == "mask_mcq":
            options = _clean_list(raw.get("options"))
            if len(options) < 2:
                raise ContractError("سؤالِ تستی گزینه کافی ندارد.")
            item["options"] = options
            idx = _as_int(raw.get("correct_option_index"), -1)
            if not (0 <= idx < len(options)):
                # مدل ممکن است یک‌پایه بدهد: ۱ برای گزینهٔ اول (اندیس ۰)
                if 1 <= idx <= len(options) and idx == len(options):
                    idx -= 1
                else:
                    idx = 0
            item["correct_option_index"] = idx
        else:
            item["correct_option_index"] = None

        # Q5 باید دستِ کاربر را ببندد؛ اگر مدل کلمهٔ ممنوعه نداده، آن را
        # از عنوانِ تخصصیِ خودِ سؤال بساز تا شرطِ اصلیِ آزمون اجرا شود.
        if qtype == "feynman_synthesis" and len(item["forbidden_words"]) < MIN_FORBIDDEN_WORDS:
            item["forbidden_words"] = _fallback_forbidden(raw, blueprint)

        questions.append(item)

    return GeneratedAssessment(blueprint=blueprint, questions=questions)


def _fallback_forbidden(raw: dict[str, Any], blueprint: Blueprint) -> list[str]:
    """کلماتِ ممنوعهٔ جانشین از خودِ متنِ سؤال استخراج می‌شود.

    اگر مدل هیچ کلمه‌ای نداده باشد، آزمون بی‌معنا نمی‌شود: از عبارت‌های
    تخصصیِ درونِ متن استفاده می‌کنیم. این بهتر از حذفِ کلِ چالش است.
    """
    import re

    text = _clean_str(raw.get("question_text"))
    candidates = re.findall(r"[آ-یA-Za-z]{4,}", text)
    skip = {"برای", "یک", "این", "آن", "که", "را", "به", "از", "با", "اگر", "چه", "چرا", "چگونه", "بچه", "سال"}
    out: list[str] = []
    for word in candidates:
        if word in skip or word in out:
            continue
        out.append(word)
        if len(out) >= MIN_FORBIDDEN_WORDS:
            break
    return out or ["فرمول", "تعریف", "قانون"]


def validate_generation(assessment: GeneratedAssessment) -> list[str]:
    """فهرستِ هشدارهای غیرکشنده — برای لاگ و برای نمایش در UI."""
    warnings: list[str] = []
    if not assessment.blueprint.core_mechanism:
        warnings.append("نقشهٔ مفهومی مکانیزمِ اصلی را مشخص نکرده است.")
    if not assessment.blueprint.target_misconceptions:
        warnings.append("کج‌فهمی‌های هدف مشخص نشده‌اند؛ سؤالِ عیب‌یابی ممکن است کم‌اثر باشد.")
    q5 = assessment.questions[-1]
    if len(q5["forbidden_words"]) < MIN_FORBIDDEN_WORDS:
        warnings.append("کلماتِ ممنوعهٔ سؤالِ فاینمن کمتر از حدِ لازم است.")
    q2 = assessment.questions[1]
    if not q2.get("options"):
        warnings.append("سؤالِ تستی گزینه ندارد.")
    return warnings


def assess_payload_from_generation(assessment: GeneratedAssessment) -> dict[str, Any]:
    """قالبِ سبکِ آزمون برای ذخیره در جلسه (بدونِ پاسخِ درستٔ لو رفته برای دانش‌آموز)."""
    return {
        "topic_blueprint": assessment.blueprint.to_dict(),
        "questions": assessment.questions,
        "ai_model_used": assessment.model_name,
        "generation_cost_usd": assessment.cost_usd,
    }


# ---------------------------------------------------------------------------
# مرحلهٔ ۲ و ۳ — ارزیابی و بازپرسی
# ---------------------------------------------------------------------------
def normalize_evaluation(payload: Any) -> EvaluationReport:
    """خروجیِ کارآگاه را به گزارشِ قطعی تبدیل می‌کند.

    نکتهٔ مهم: اگر مدل `needs_clarification` را true بگذارد اما متنِ
    `mirror_prompt` را خالی بگذارد، بازپرسی بی‌معنا می‌شود (کاربر چیزی
    نمی‌بیند که به آن پاسخ دهد). در این حالت بازپرسی لغو می‌شود تا کاربر
    در بن‌بست نماند.
    """
    if not isinstance(payload, dict):
        raise ContractError("خروجیِ ارزیاب یک شیءِ JSON نیست.")

    report_raw = payload.get("evaluation_report") or payload.get("report") or {}
    if not isinstance(report_raw, dict):
        report_raw = {}

    status = _clean_str(report_raw.get("mastery_status")).upper()
    if status not in ("MASTERED", "ILLUSION_OF_COMPETENCE", "JARGON_DEPENDENT", "PARTIAL_FRAGMENTED", "UNSTRUCTURED"):
        status = "PARTIAL_FRAGMENTED"

    findings: list[CrossCheckFinding] = []
    for item in report_raw.get("cross_check_findings") or []:
        if not isinstance(item, dict):
            continue
        ftype = _clean_str(item.get("type")).upper() or "SYNERGY"
        if ftype not in FINDING_TYPES:
            ftype = "SYNERGY"
        findings.append(
            CrossCheckFinding(
                title=_clean_str(item.get("title")) or "یافته",
                type=ftype,
                description=_clean_str(item.get("description")),
            )
        )

    insights: list[QuestionInsight] = []
    for item in report_raw.get("question_by_question_insight") or []:
        if not isinstance(item, dict):
            continue
        qid = _as_int(item.get("question_id"), 0)
        if qid == 0:
            continue
        missing = item.get("missing_gear")
        insights.append(
            QuestionInsight(
                question_id=qid,
                cognitive_verdict=_clean_str(item.get("cognitive_verdict")),
                missing_gear=_clean_str(missing) or None,
            )
        )
    insights.sort(key=lambda i: i.question_id)

    needs = bool(payload.get("needs_clarification"))
    clar_raw = payload.get("clarification_data") or {}
    clarification: Optional[ClarificationData] = None
    if isinstance(clar_raw, dict):
        mirror = _clean_str(clar_raw.get("mirror_prompt"))
        contradicting = [
            q for q in (_as_int(x, 0) for x in (clar_raw.get("contradicting_questions") or [])) if q
        ]
        if mirror:
            clarification = ClarificationData(
                contradicting_questions=contradicting[:4],
                mirror_prompt=mirror,
            )
    # بازپرسی بدونِ متنِ آینه‌ای، کاربر را در بن‌بست می‌گذارد.
    if needs and clarification is None:
        needs = False

    return EvaluationReport(
        mastery_status=status,
        persona_title=_clean_str(report_raw.get("persona_title")),
        executive_summary=_clean_str(report_raw.get("executive_summary")),
        cross_check_findings=findings,
        question_by_question_insight=insights,
        actionable_advice=_clean_str(report_raw.get("actionable_advice")),
        needs_clarification=needs,
        clarification=clarification,
    )
