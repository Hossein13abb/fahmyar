"""لایهٔ انتزاع مدل هوش مصنوعی — تعویض مدل بدون تغییر کد بقیهٔ سیستم.

پروایدرها:
  - GeminiFreeProvider : گوگل جمینی ۲ فلش (پلن رایگان) — نیازمند GEMINI_API_KEY
  - OpenRouterProvider : مدل‌های OpenRouter با فراخوانی HTTP محض (requests) — نیازمند OPENROUTER_API_KEY
  - MockProvider       : بدون شبکه و کلید؛ پاسخ‌های قالب‌بندی‌شدهٔ قطعی (برای تست)

ModelRouter:
  - مسیریابی بر اساس task_type
  - ثبتِ همهٔ فراخوانی‌ها در جدول ai_usage_logs (مدل، توکن، هزینه، نوع وظیفه، زمان)
  - کنترل سقف بودجه (پیش‌فرض ۱۰ دلار — پلن رایگان همیشه صفر است)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from config import settings


class BudgetExceededError(Exception):
    """سقف بودجهٔ هوش مصنوعی رد شده است."""


class AIProviderError(Exception):
    """خطای پروایدر مدل."""


@dataclass
class AIResponse:
    text: str
    model_name: str
    token_count: int
    cost_usd: float = 0.0
    task_type: str = ""
    raw: Optional[dict[str, Any]] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# رابط انتزاعی
# ---------------------------------------------------------------------------
class AIProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        ...


# ---------------------------------------------------------------------------
# Gemini 2.0 Flash (پلن رایگان)
# ---------------------------------------------------------------------------
class GeminiFreeProvider(AIProvider):
    name = "gemini_free"

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        if not self.api_key:
            raise AIProviderError(
                "GEMINI_API_KEY تنظیم نشده است. کلید رایگان را از https://ai.google.dev بگیرید "
                "یا AI_PROVIDER=mock را در .env قرار دهید."
            )
        try:
            import google.generativeai as genai  # import تنبل — لازم نیست برای mock نصب باشد
        except ImportError as exc:  # pragma: no cover
            raise AIProviderError(
                "کتابخانهٔ google-generativeai نصب نیست. `pip install google-generativeai` را اجرا کنید."
            ) from exc
        genai.configure(api_key=self.api_key)
        self._genai = genai
        self._model = genai.GenerativeModel(self.model_name)
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._min_interval = max(0.0, settings.GEMINI_MIN_INTERVAL_SECONDS)

    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        # محدودیت نرخ پلن رایگان — فاصلهٔ حداقلی بین فراخوانی‌ها
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

        try:
            response = await self._model.generate_content_async(
                prompt,
                generation_config={"temperature": temperature},
            )
        except Exception as exc:
            raise AIProviderError(f"خطای فراخوانی Gemini: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            # بعضی پاسخ‌ها به‌دلیل فیلتر ایمنی خالی می‌شوند
            raise AIProviderError("پاسخ خالی از Gemini (ممکن است فیلتر ایمنی فعال شده باشد).")

        token_count = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            token_count = int(getattr(usage, "total_token_count", 0) or 0)
        if not token_count:
            token_count = max(1, (len(prompt) + len(text)) // 4)  # تخمین

        return AIResponse(
            text=text,
            model_name=self.model_name,
            token_count=token_count,
            cost_usd=0.0,  # پلن رایگان Gemini
            task_type=task_type,
        )


# ---------------------------------------------------------------------------
# OpenRouter (فراخوانی HTTP محض با requests — بدون SDK)
# ---------------------------------------------------------------------------
class OpenRouterProvider(AIProvider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        # پاکسازی کلید: فاصلهٔ انتهایی/خط جدید (.strip()) علت رایج خطای 401 است
        raw_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.api_key = (raw_key or "").strip()
        self.model_name = (model_name or settings.OPENROUTER_MODEL).strip()
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.timeout = settings.OPENROUTER_TIMEOUT_SECONDS
        if not self.api_key:
            raise AIProviderError(
                "OPENROUTER_API_KEY تنظیم نشده است. کلید را در .env قرار دهید "
                "یا AI_PROVIDER=mock را انتخاب کنید."
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fahmyar.ir",
            "X-Title": "Fahmyar App",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    def _post_chat_completion(self, prompt: str, temperature: float) -> dict[str, Any]:
        import requests  # import تنبل — اگر requests نصب نباشد فقط این پروایدر می‌شکند

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AIProviderError(f"خطای شبکه در اتصال به OpenRouter: {exc}") from exc

        if resp.status_code == 401:
            body_excerpt = (resp.text or "")[:300]
            raise AIProviderError(
                f"خطای 401 از OpenRouter — کلید API یافت نشد یا نامعتبر است "
                f"(پس از .strip() بررسی شد). پاسخ سرور: {body_excerpt}"
            )
        if resp.status_code >= 400:
            raise AIProviderError(
                f"خطای {resp.status_code} از OpenRouter: {(resp.text or '')[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise AIProviderError("پاسخ غیرJSON از OpenRouter دریافت شد.") from exc

    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        # requests همزمانی نیست؛ در thread اجرا می‌شود تا event loop قفل نشود
        data = await asyncio.to_thread(self._post_chat_completion, prompt, temperature)

        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"ساختار پاسخ OpenRouter نامعتبر بود: {exc}") from exc
        if not text:
            raise AIProviderError("پاسخ خالی از OpenRouter.")

        usage = data.get("usage") or {}
        token_count = int(usage.get("total_tokens") or 0) or max(1, (len(prompt) + len(text)) // 4)
        # بعضی مدل‌های رایگان هزینه را هم برمی‌گردانند؛ در غیاب، صفر در نظر می‌گیریم
        try:
            cost_usd = float(usage.get("cost") or 0.0)
        except (TypeError, ValueError):
            cost_usd = 0.0

        return AIResponse(
            text=text,
            model_name=self.model_name,
            token_count=token_count,
            cost_usd=cost_usd,
            task_type=task_type,
            raw=data,
        )


# ---------------------------------------------------------------------------
# Mock — کاملاً آفلاین و قطعی
# ---------------------------------------------------------------------------
_REASONING_MARKERS = [
    "چون", "زیرا", "به این دلیل", "به دلیل", "به علت", "چرا که", "بنابراین",
    "لذا", "باعث", "موجب", "پس نتیجه", "در نتیجه", "because", "since", "therefore",
]
_UNCERTAINTY_MARKERS = ["نمی‌دانم", "نمیدانم", "مطمئن نیستم", "شک دارم", "no idea", "idk"]


def _extract_marker(prompt: str, tag: str) -> str:
    m = re.search(rf"<<<{tag}>>>(.*?)<<<END>>>", prompt, re.DOTALL)
    return m.group(1).strip() if m else ""


class MockProvider(AIProvider):
    name = "mock"

    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        # شبیه‌سازی تأخیر واقعی شبکه نیست؛ تست‌ها سریع می‌مانند
        if task_type == "generate_question":
            text = self._mock_question(prompt)
        elif task_type == "analyze_response":
            text = self._mock_analysis(prompt)
        elif task_type == "build_graph":
            text = json.dumps(
                {"suggestions": [
                    {"from": "math.ratio_proportion", "to": "physics.ohm_law", "type": "tool", "cross_subject": True},
                    {"from": "chemistry.oxidation_number", "to": "chemistry.redox_reactions", "type": "prerequisite", "cross_subject": False},
                ]},
                ensure_ascii=False,
            )
        else:
            text = json.dumps({"echo": task_type, "note": "mock provider"}, ensure_ascii=False)
        return AIResponse(
            text=text,
            model_name="mock-model",
            token_count=max(1, len(prompt + text) // 4),
            cost_usd=0.0,
            task_type=task_type,
        )

    # --- قالب‌های قطعی ---
    def _mock_question(self, prompt: str) -> str:
        proposition = _extract_marker(prompt, "PROPOSITION") or "گزارهٔ هدفِ نمونه"
        misconception = _extract_marker(prompt, "MISCONCEPTION") or ""
        concept = _extract_marker(prompt, "CONCEPT") or "مفهوم نمونه"
        payload = {
            "question_text": (
                f"یک آزمایشگاه/کارگاه واقعی را در نظر بگیرید: مسئله‌ای دربارهٔ «{concept}» پیش آمده است. "
                "با توجه به داده‌های زیر، توضیح دهید چه اتفاقی می‌افتد و چرا: "
                "(داده‌ها: دمای محیط ۲۵ درجه، جرم نمونه ۱۰ گرم، زمان ۵ دقیقه، مشاهده: تغییر رنگ تدریجی مشاهده شد). "
                "استدلال خود را مرحله‌به‌مرحله بنویسید و به رابطهٔ پدیده با علت آن اشاره کنید."
            ),
            "phenomenon_description": f"موقعیت واقعی مرتبط با {concept} — مشاهدهٔ عینی بدون تفسیر",
            "required_data": ["دمای محیط: ۲۵°C", "جرم نمونه: ۱۰ گرم", "زمان: ۵ دقیقه", "مشاهده: تغییر تدریجی"],
            "question_type": "phenomenon_explain",
            "difficulty": "medium",
            "cognitive_type": "conceptual",
            "rubric": {
                "correct_reasoning": f"دانش‌آموز باید با تکیه بر گزارهٔ «{proposition}» و استدلال علّی (علت → معلول) به پاسخ برسد",
                "misconception_indicators": ({misconception: "نشانهٔ بدفهمیِ هدف در پاسخ دیده می‌شود"} if misconception else {}),
                "partial_credit_signs": ["جهت کلی پاسخ درست است ولی استدلال ناقص است"],
                "non_conceptual_errors": ["خطای محاسباتی بدون خطای مفهومی"],
            },
            "mapped_propositions": [proposition],
            "mapped_misconceptions": ([misconception] if misconception else []),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _mock_analysis(self, prompt: str) -> str:
        response = _extract_marker(prompt, "RESPONSE")
        props_raw = _extract_marker(prompt, "PROPOSITIONS")
        try:
            propositions = json.loads(props_raw) if props_raw else []
        except json.JSONDecodeError:
            propositions = [props_raw] if props_raw else []
        if not propositions:
            propositions = ["گزارهٔ هدف"]

        text = response.strip()
        low = text.lower()
        has_reasoning = any(m in text for m in _REASONING_MARKERS)
        uncertain = any(m in text for m in _UNCERTAINTY_MARKERS)
        word_count = len(text.split())

        evidence = []
        for prop in propositions:
            if uncertain or word_count < 4:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.25
                reasoning = "پاسخ بسیار کوتاه یا همراه با عدم اطمینان است — نمی‌توان نتیجه‌گیری کرد."
                needs_review = True
            elif has_reasoning and word_count >= 25:
                status, etype, conf = "CONFIRMED", "strong_confirming", 0.8
                reasoning = "پاسخ شامل ادعا + دلیل صریح و مرتبط است (ساختار استدلال سالم)."
                needs_review = False
            elif has_reasoning:
                status, etype, conf = "LIKELY_UNDERSTOOD", "strong_confirming", 0.68
                reasoning = "پاسخ شامل استدلال است ولی کوتاه/ناقص؛ شواهد قوی اما محدود."
                needs_review = False
            elif word_count >= 15:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.45
                reasoning = "پاسخ داده شده ولی استدلال صریحی ندارد — واژهٔ کلیدی بدون دلیل، شواهد محسوب نمی‌شود."
                needs_review = False
            else:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.35
                reasoning = "پاسخ کوتاه و بدون استدلال صریح است."
                needs_review = True
            evidence.append(
                {
                    "proposition_id": prop,
                    "status": status,
                    "evidence_type": etype,
                    "reasoning": reasoning,
                    "confidence": conf,
                    "error_type": "none",
                    "needs_teacher_review": needs_review,
                }
            )
        return json.dumps({"evidence": evidence, "overall_reasoning": "تحلیل آفلاین (mock)"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# روتر مدل + ثبت لاگ + کنترل بودجه
# ---------------------------------------------------------------------------
_TASK_ROUTE = {
    "generate_question": "gemini_free",
    "analyze_response": "gemini_free",
    "build_graph": "gemini_free",
}

_OPENROUTER_ROUTE = {
    "generate_question": "openrouter",
    "analyze_response": "openrouter",
    "build_graph": "openrouter",
}


def _log_usage(provider: str, response: AIResponse | None, task_type: str,
               success: bool, error: str | None = None) -> None:
    """ثبت لاگ استفاده — شکست یا موفقیت. خود خطای لاگ نباید سیستم را بخواباند."""
    try:
        from models.database import SessionLocal
        from models.ai_log import AIUsageLog

        db = SessionLocal()
        try:
            db.add(
                AIUsageLog(
                    provider=provider,
                    model_name=response.model_name if response else "",
                    task_type=task_type,
                    token_count=response.token_count if response else 0,
                    cost_usd=response.cost_usd if response else 0.0,
                    success=success,
                    error=error,
                    timestamp=datetime.utcnow(),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        # لاگ نباید مسیر اصلی را بشکند؛ به خروجی استاندارد اکتفا می‌کنیم
        print(f"[AI-LOG] {task_type} success={success} error={error}")


class ModelRouter:
    """مسیریابیِ وظایف به پروایدر مناسب + سقف بودجه + لاگ‌گیری."""

    def __init__(self) -> None:
        self.provider_name = (settings.AI_PROVIDER or "gemini_free").lower()
        self._providers: dict[str, AIProvider] = {}

    def get_provider(self, task_type: str) -> AIProvider:
        if self.provider_name == "mock":
            key = "mock"
        elif self.provider_name == "openrouter":
            key = _OPENROUTER_ROUTE.get(task_type, "openrouter")
        else:
            key = _TASK_ROUTE.get(task_type, "gemini_free")
        if key not in self._providers:
            if key == "mock":
                self._providers[key] = MockProvider()
            elif key == "gemini_free":
                self._providers[key] = GeminiFreeProvider()
            elif key == "openrouter":
                self._providers[key] = OpenRouterProvider()
            else:  # pragma: no cover
                raise AIProviderError(f"پروایدر ناشناخته: {key}")
        return self._providers[key]

    @staticmethod
    def total_cost_usd() -> float:
        try:
            from sqlalchemy import func
            from models.database import SessionLocal
            from models.ai_log import AIUsageLog

            db = SessionLocal()
            try:
                total = db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).scalar()
                return float(total or 0.0)
            finally:
                db.close()
        except Exception:
            return 0.0

    def budget_remaining(self) -> float:
        return max(0.0, settings.BUDGET_LIMIT_USD - self.total_cost_usd())

    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        if self.total_cost_usd() >= settings.BUDGET_LIMIT_USD:
            _log_usage(self.provider_name, None, task_type, success=False, error="budget_exceeded")
            raise BudgetExceededError(
                f"سقف بودجهٔ هوش مصنوعی ({settings.BUDGET_LIMIT_USD} دلار) تمام شده است."
            )
        provider = self.get_provider(task_type)
        try:
            response = await provider.generate(prompt, task_type, temperature)
            _log_usage(provider.name, response, task_type, success=True)
            return response
        except BudgetExceededError:
            raise
        except Exception as exc:
            _log_usage(self.provider_name, None, task_type, success=False, error=str(exc))
            raise


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
