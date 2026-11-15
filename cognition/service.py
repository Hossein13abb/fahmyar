"""سرویس موتور فهم‌سنجی شناختی — تولید، ارزیابیِ کل‌نگر و بازپرسی.

این ماژول *همهٔ* ارتباط با مدل را در سه تابعِ مستقل نگه می‌دارد. هیچ منطقِ
حکمی این‌جا نیست؛ قواعدِ قطعی در `cognition.rules` و اعتبارسنجی در
`cognition.contract` است. نتیجه: هر لایه جداگانه آزمون‌پذیر است.

جریان:

    generate_assessment()  → آزمونِ ۵ سؤالی + نقشهٔ مفهومی
    evaluate_assessment()  → کارنامهٔ اشعهٔ ایکس (+ درخواستِ بازپرسی اگر لازم)
    clarify_assessment()   → حکمِ نهایی پس از پاسخِ دانش‌آموز به بازپرسی
"""
from __future__ import annotations

import logging
from typing import Any

from ai.json_sanitize import extract_json_object, sanitize_json_string
from ai.model_abstraction import AIProviderError, BudgetExceededError, get_router
from cognition.contract import (
    ContractError,
    EvaluationReport,
    GeneratedAssessment,
    normalize_evaluation,
    normalize_generation,
    validate_generation,
)
from cognition.prompts import (
    build_clarify_prompt,
    build_evaluator_prompt,
    build_generator_prompt,
)
from cognition.rules import (
    apply_jargon_flag,
    apply_supremacy_override,
    dedupe_findings,
    rule_summary,
)

logger = logging.getLogger(__name__)


class CognitionError(RuntimeError):
    """خطای قابلِ نمایش به کاربر در موتور فهم‌سنجی."""

    def __init__(self, message: str, *, reason: str = "engine_error", status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.status_code = status_code


def _parse_model_json(raw: str, what: str) -> dict[str, Any]:
    """JSON مدل را با ترمیمِ LaTeX و بدونِ بلعیدنِ خطا پارس می‌کند."""
    for parser in (sanitize_json_string, extract_json_object):
        try:
            parsed = parser(raw)  # type: ignore[misc]
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    snippet = (raw or "").strip()[:240].replace("\n", " ")
    raise CognitionError(
        f"خروجیِ مدل برای {what} ساختارِ JSON معتبری نداشت. نمونهٔ پاسخ: {snippet!r}",
        reason="invalid_model_json",
    )


async def _call_model(prompt: str, task_type: str, temperature: float) -> tuple[str, str, float]:
    """فراخوانیِ مدل با ترجمهٔ خطاها به پیامِ فارسیِ قابلِ اقدام."""
    router = get_router()
    try:
        response = await router.generate(prompt, task_type, temperature=temperature)
    except BudgetExceededError as exc:
        raise CognitionError(str(exc), reason="budget_exceeded", status_code=402) from exc
    except AIProviderError as exc:
        raise CognitionError(
            f"ارتباط با مدلِ هوش مصنوعی برقرار نشد: {exc}",
            reason="provider_error",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — هر خطای دیگر هم باید پیام بدهد
        logger.exception("cognitive: unexpected provider failure")
        raise CognitionError(
            f"خطای غیرمنتظره در فراخوانیِ مدل: {exc}",
            reason="provider_error",
        ) from exc
    return response.text, response.model_name, float(response.cost_usd or 0.0)


# ---------------------------------------------------------------------------
# مرحلهٔ ۱ — تولیدِ آزمون
# ---------------------------------------------------------------------------
async def generate_assessment(
    *,
    topic: str,
    subject: str = "",
    grade: str = "",
    misconceptions: list[str] | None = None,
) -> tuple[GeneratedAssessment, list[str]]:
    """آزمونِ ۵ سؤالیِ زنجیره‌ای + نقشهٔ مفهومی را می‌سازد.

    خروجی: (آزمونِ نرمال‌شده، فهرستِ هشدارهای غیرکشنده)
    """
    if not (topic or "").strip():
        raise CognitionError("موضوعِ آزمون مشخص نیست.", reason="missing_topic", status_code=422)

    prompt = build_generator_prompt(topic.strip(), subject=subject, grade=grade, misconceptions=misconceptions)
    raw, model_name, cost = await _call_model(prompt, "cognitive_generate", 0.7)
    payload = _parse_model_json(raw, "تولیدِ آزمون")

    try:
        assessment = normalize_generation(payload)
    except ContractError as exc:
        raise CognitionError(
            f"آزمونِ تولیدشده با قرارداد نمی‌خواند: {exc}",
            reason="contract_violation",
        ) from exc

    assessment.model_name = model_name
    assessment.cost_usd = cost
    warnings = validate_generation(assessment)
    if warnings:
        logger.warning("cognitive generation warnings: %s", warnings)
    return assessment, warnings


# ---------------------------------------------------------------------------
# مرحلهٔ ۲ — ارزیابیِ کل‌نگر
# ---------------------------------------------------------------------------
async def evaluate_assessment(
    *,
    topic: str,
    blueprint: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> dict[str, Any]:
    """پاسخ‌ها را *با هم* مقایسه می‌کند و کارنامهٔ اشعهٔ ایکس می‌سازد.

    خروجیِ نهایی: دیکشنریِ کاملِ گزارش + سیگنال‌های قطعی (برای ذخیره و
    نمایشِ شفاف در UI).
    """
    signals = rule_summary(answers, questions)
    prompt = build_evaluator_prompt(topic, blueprint, questions, answers, signals)
    raw, _model_name, _cost = await _call_model(prompt, "cognitive_evaluate", 0.4)

    payload = _parse_model_json(raw, "ارزیابی")
    try:
        report: EvaluationReport = normalize_evaluation(payload)
    except ContractError as exc:
        raise CognitionError(
            f"گزارشِ ارزیابی با قرارداد نمی‌خواند: {exc}",
            reason="contract_violation",
        ) from exc

    result = report.to_dict()
    _fact_check_mcq(result, questions, answers)
    # قواعدِ قطعی به‌عنوانِ تورِ ایمنی روی حکمِ مدل اعمال می‌شوند.
    result = apply_supremacy_override(result, signals)
    result = apply_jargon_flag(result, signals)
    result = dedupe_findings(result)
    result["signals"] = signals
    return result


# ---------------------------------------------------------------------------
# مرحلهٔ ۳ — بازپرسی
# ---------------------------------------------------------------------------
async def clarify_assessment(
    *,
    topic: str,
    blueprint: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[int, str],
    clarification_answer: str,
    previous_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """حکمِ نهایی را پس از پاسخِ دانش‌آموز به بازپرسی صادر می‌کند."""
    if not (clarification_answer or "").strip():
        raise CognitionError(
            "پاسخِ بازپرسی خالی است؛ برای صدورِ حکمِ نهایی به توضیحِ کوتاه نیاز است.",
            reason="empty_clarification",
            status_code=422,
        )

    signals = rule_summary(answers, questions)
    prompt = build_clarify_prompt(
        topic,
        blueprint,
        questions,
        answers,
        clarification_answer.strip(),
        previous_report=previous_report,
        signals=signals,
    )
    raw, _model_name, _cost = await _call_model(prompt, "cognitive_clarify", 0.4)
    payload = _parse_model_json(raw, "بازپرسی")
    try:
        report = normalize_evaluation(payload)
    except ContractError as exc:
        raise CognitionError(
            f"گزارشِ نهایی با قرارداد نمی‌خواند: {exc}",
            reason="contract_violation",
        ) from exc

    result = report.to_dict()
    # بازپرسی انجام شده؛ دیگر نباید دوباره درخواست شود (حلقهٔ بی‌پایان).
    result["needs_clarification"] = False
    result = apply_supremacy_override(result, signals)
    result = apply_jargon_flag(result, signals)
    result = dedupe_findings(result)
    result["signals"] = signals
    result["clarification_answer"] = clarification_answer.strip()
    return result


# ---------------------------------------------------------------------------
# راستی‌آزماییِ قطعیِ سؤالِ تستی
# ---------------------------------------------------------------------------
def _fact_check_mcq(
    report: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> None:
    """درستیِ سؤالِ ۲ را در کد تعیین می‌کند، نه با اعتماد به مدل.

    **چرا لازم است؟** مدل در توضیحِ هر سؤال، «سالم/خراب» می‌نویسد و می‌تواند
    گزینهٔ نادرست را «سالم» بشمارد، چون قضاوتش معنایی است و پاسخِ کوتاه و
    مطمئن را با پاسخِ درست اشتباه می‌گیرد. اما درستیِ یک تستِ چهارگزینه‌ای
    مسئلهٔ *محاسبه* است، نه قضاوت — پس در کد محاسبه می‌شود و نظرِ مدل
    بازنویسی می‌شود.
    """
    from cognition.rules import _chosen_option

    q2 = next((q for q in questions or [] if int(q.get("id") or 0) == 2), None)
    if not q2 or q2.get("correct_option_index") is None:
        return

    chosen = _chosen_option(answers, q2)
    if chosen is None:
        return

    correct = int(q2["correct_option_index"])
    is_right = chosen == correct

    evaluation = report.setdefault("evaluation_report", {})
    insights = evaluation.get("question_by_question_insight") or []
    for insight in insights:
        if int(insight.get("question_id") or 0) != 2:
            continue
        insights = [i for i in insights if int(i.get("question_id") or 0) != 2]
        insights.append(
            {
                "question_id": 2,
                "cognitive_verdict": (
                    "لایهٔ نقاب را رد کردی: گزینهٔ درست را انتخاب کردی و گمراه‌کننده‌ها را نادیده گرفتی."
                    if is_right
                    else "در تست به گزینهٔ نادرست رسیدی — این نقطه دقیقاً همان جایی است که فرمول و شهود از هم جدا می‌شوند."
                ),
                "missing_gear": None if is_right else "تشخیصِ اطلاعاتِ انحرافی از متغیرِ مؤثر",
                "is_correct": is_right,
            }
        )
        insights.sort(key=lambda i: int(i.get("question_id") or 0))
        evaluation["question_by_question_insight"] = insights
        return
