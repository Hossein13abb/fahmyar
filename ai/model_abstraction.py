"""لایهٔ انتزاع مدل هوش مصنوعی — تعویض مدل بدون تغییر کد بقیهٔ سیستم.

پروایدرها:
  - GeminiFreeProvider  : گوگل جمینی ۲ فلش (پلن رایگان) — نیازمند GEMINI_API_KEY
  - OpenRouterProvider  : OpenRouter (ده‌ها مدل رایگان و پولی) — نیازمند OPENROUTER_API_KEY
  - MockProvider        : بدون شبکه و کلید؛ پاسخ‌های قالب‌بندی‌شدهٔ قطعی (برای تست)

ModelRouter:
  - مسیریابی بر اساس task_type
  - ثبتِ همهٔ فراخوانی‌ها در جدول ai_usage_logs (مدل، توکن، هزینه، نوع وظیفه، زمان)
  - کنترل سقف بودجه (پیش‌فرض ۱۰ دلار — پلن رایگان همیشه صفر است)
"""
from __future__ import annotations

import asyncio
import json
import os
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
            import google.generativeai as genai  # import تنبل
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
            raise AIProviderError("پاسخ خالی از Gemini (ممکن است فیلتر ایمنی فعال شده باشد).")

        token_count = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            token_count = int(getattr(usage, "total_token_count", 0) or 0)
        if not token_count:
            token_count = max(1, (len(prompt) + len(text)) // 4)

        return AIResponse(
            text=text,
            model_name=self.model_name,
            token_count=token_count,
            cost_usd=0.0,
            task_type=task_type,
        )


# ---------------------------------------------------------------------------
# OpenRouter (سازگار با فرمت OpenAI) — ده‌ها مدل رایگان و پولی
# ---------------------------------------------------------------------------
class OpenRouterProvider(AIProvider):
    """پروایدر OpenRouter — یک API برای ده‌ها مدل مختلف (رایگان و پولی).

    پیش‌فرض‌ها:
      - OPENROUTER_API_KEY      : کلید API از https://openrouter.ai
      - OPENROUTER_MODEL        : نام مدل (مثلاً google/gemini-2.0-flash-exp:free)
      - OPENROUTER_BASE_URL     : پیش‌فرض https://openrouter.ai/api/v1
      - OPENROUTER_SITE_URL     : (اختیاری) آدرس سایت شما برای HTTP-Referer
      - OPENROUTER_APP_NAME     : (اختیاری) نام برنامه برای X-Title
    """

    name = "openrouter"

    # هزینهٔ تقریبی مدل‌های رایج (USD per 1K tokens) — برای مدل‌های `:free` صفر است
    _PRICING_PER_1K = {
        # مدل‌های رایگان
        "google/gemini-2.0-flash-exp:free": 0.0,
        "meta-llama/llama-3.3-70b-instruct:free": 0.0,
        "mistralai/mistral-7b-instruct:free": 0.0,
        "qwen/qwen-2.5-72b-instruct:free": 0.0,
        "deepseek/deepseek-chat:free": 0.0,
        "deepseek/deepseek-r1:free": 0.0,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or getattr(settings, "OPENROUTER_API_KEY", None)
        self.model_name = (
            model_name
            or os.getenv("OPENROUTER_MODEL")
            or getattr(settings, "OPENROUTER_MODEL", None)
            or "google/gemini-2.0-flash-exp:free"
        )
        self.base_url = (
            base_url
            or os.getenv("OPENROUTER_BASE_URL")
            or getattr(settings, "OPENROUTER_BASE_URL", None)
            or "https://openrouter.ai/api/v1"
        )
        self.site_url = os.getenv("OPENROUTER_SITE_URL") or getattr(settings, "OPENROUTER_SITE_URL", "")
        self.app_name = os.getenv("OPENROUTER_APP_NAME") or getattr(settings, "OPENROUTER_APP_NAME", "Fahmyar")

        if not self.api_key:
            raise AIProviderError(
                "OPENROUTER_API_KEY تنظیم نشده است. کلید را از https://openrouter.ai بگیرید "
                "و در .env قرار دهید."
            )

        try:
            from openai import AsyncOpenAI  # import تنبل
        except ImportError as exc:
            raise AIProviderError(
                "کتابخانهٔ openai نصب نیست. `pip install openai` را اجرا کنید."
            ) from exc

        default_headers: dict[str, str] = {}
        if self.site_url:
            default_headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            default_headers["X-Title"] = self.app_name

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=default_headers or None,
        )

        # محدودیت نرخ ملایم — برای مدل‌های رایگان مفید است
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._min_interval = float(
            os.getenv("OPENROUTER_MIN_INTERVAL_SECONDS")
            or getattr(settings, "OPENROUTER_MIN_INTERVAL_SECONDS", 0.0)
        )

    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

        # پیام سیستمی: پاسخ‌دهی به فارسی + خروجی JSON ساخت‌یافته در صورت نیاز
        system_message = (
            "You are an educational diagnostic AI for a Persian (Farsi) school system named Fahmyar. "
            "Respond in Persian unless the prompt explicitly requests otherwise. "
            "When the user prompt expects a structured output, return ONLY valid JSON without markdown fences. "
            "Do not add explanations outside the JSON. Follow all constraints in the user prompt strictly."
        )

        try:
            completion = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
        except Exception as exc:
            raise AIProviderError(f"خطای فراخوانی OpenRouter: {exc}") from exc

        if not completion.choices:
            raise AIProviderError("پاسخ خالی از OpenRouter (choices خالی بود).")

        message = completion.choices[0].message
        text = (message.content or "").strip()
        if not text:
            raise AIProviderError(
                "پاسخ خالی از OpenRouter (ممکن است مدل رایگان در حال حاضر در دسترس نباشد "
                "یا فیلتر ایمنی فعال شده باشد)."
            )

        # پاکسازی احتمالی بلوک‌های markdown
        text = self._strip_markdown_fences(text)

        token_count = 0
        usage = getattr(completion, "usage", None)
        if usage is not None:
            token_count = int(getattr(usage, "total_tokens", 0) or 0)
        if not token_count:
            token_count = max(1, (len(prompt) + len(text)) // 4)

        cost_usd = self._estimate_cost(token_count)

        return AIResponse(
            text=text,
            model_name=self.model_name,
            token_count=token_count,
            cost_usd=cost_usd,
            task_type=task_type,
        )

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """اگر مدل خروجی JSON را داخل ```json ... ``` گذاشته باشد، آن را پاک می‌کنیم."""
        stripped = text.strip()
        if stripped.startswith("```"):
            # حذف خط اول (```json یا ```) و خط آخر (```)
            lines = stripped.splitlines()
            if len(lines) >= 2:
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                return "\n".join(lines).strip()
        return stripped

    def _estimate_cost(self, token_count: int) -> float:
        """تخمین هزینه. برای مدل‌های `:free` همیشه صفر است."""
        if self.model_name.endswith(":free"):
            return 0.0
        price = self._PRICING_PER_1K.get(self.model_name)
        if price is None:
            # مدل ناشناخته — اگر در .env اعلام شده، از آن استفاده کن
            try:
                price = float(os.getenv("OPENROUTER_PRICE_PER_1K", "0") or 0.0)
            except ValueError:
                price = 0.0
        return round((token_count / 1000.0) * price, 6)


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
# مسیر پیش‌فرض برای هر وظیفه؛ اگر AI_PROVIDER در .env تنظیم شده باشد، همهٔ وظایف به آن می‌روند.
_TASK_ROUTE_DEFAULT = {
    "generate_question": "gemini_free",
    "analyze_response": "gemini_free",
    "build_graph": "gemini_free",
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
        print(f"[AI-LOG] {task_type} success={success} error={error}")


class ModelRouter:
    """مسیریابیِ وظایف به پروایدر مناسب + سقف بودجه + لاگ‌گیری."""

    _VALID_PROVIDERS = {"mock", "gemini_free", "openrouter"}

    def __init__(self) -> None:
        self.provider_name = (settings.AI_PROVIDER or "gemini_free").lower().strip()
        if self.provider_name not in self._VALID_PROVIDERS:
            raise AIProviderError(
                f"AI_PROVIDER نامعتبر: «{self.provider_name}». مقادیر مجاز: {sorted(self._VALID_PROVIDERS)}"
            )
        self._providers: dict[str, AIProvider] = {}

    def get_provider(self, task_type: str) -> AIProvider:
        # اگر کاربر در .env یک پروایدر مشخص کرده، همهٔ وظایف را به همان می‌فرستیم.
        # این ساده‌ترین و قابل‌پیش‌بینی‌ترین رفتار برای نسخهٔ MVP است.
        key = self.provider_name
        if key == "mock":
            key = "mock"
        elif key not in self._VALID_PROVIDERS:
            key = _TASK_ROUTE_DEFAULT.get(task_type, "gemini_free")

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