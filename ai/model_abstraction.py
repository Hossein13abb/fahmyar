"""لایهٔ انتزاع مدل هوش مصنوعی — تعویض مدل بدون تغییر کد بقیهٔ سیستم.

پروایدرها:
  - GeminiFreeProvider : گوگل جمینی ۲ فلش (پلن رایگان) — نیازمند GEMINI_API_KEY
  - OpenRouterProvider : مدل‌های OpenRouter با فراخوانی HTTP محض (requests) — کشف پویای مدل‌های رایگان + فال‌بک خودکار — نیازمند OPENROUTER_API_KEY
  - MockProvider       : بدون شبکه و کلید؛ پاسخ‌های قالب‌بندی‌شدهٔ قطعی (برای تست)

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
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from config import settings


class BudgetExceededError(Exception):
    """سقف بودجهٔ هوش مصنوعی رد شده است."""


class AIProviderError(Exception):
    """خطای پروایدر مدل.

    retryable=True یعنی «با مدل دیگری شاید حل شود» (۴۰۴/۴۰۰/۴۰۲/محدودیت نرخ/۵xx/مشکل شبکه).
    retryable=False یعنی اشکال ساختاری است (مثلاً ۴۰۱ کلید نامعتبر) و تعویض مدل فایده‌ای ندارد.
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


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
# OpenRouter — کشف پویای مدل‌های رایگان (کش ۱۵ دقیقه‌ای) + اولویت‌بندی + فال‌بک خودکار
# فراخوانی از طریق requests (همزمان) — بدون نیاز به کتابخانهٔ openai
# ---------------------------------------------------------------------------

# پیام سیستمی — پاسخ فارسی + خروجی JSON ساخت‌یافته در صورت نیاز
_OPENROUTER_SYSTEM_MESSAGE = (
    "You are an educational diagnostic AI for a Persian (Farsi) school system named Fahmyar. "
    "Respond in Persian unless the prompt explicitly requests otherwise. "
    "When the user prompt expects a structured output, return ONLY valid JSON without markdown fences. "
    "Do not add explanations outside the JSON. Follow all constraints in the user prompt strictly."
)

# گروه‌های اولویت — گروه‌های قبلی اولویت بیشتری دارند؛ داخل هر گروه به ترتیب
_PREFERENCE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("llama-3.3-70b", "llama-3.1-70b"),
    ("qwen-2.5-72b", "qwen-2.5-32b"),
    ("gemini-2.0", "gemini-1.5"),
    ("mistral", "qwen", "phi"),
)

# کش لیست مدل‌های رایگان — مشترک بین همهٔ نمونه‌ها
_FREE_MODELS_TTL_SECONDS = 15 * 60
_free_models_cache: dict[str, Any] = {"ts": 0.0, "models": []}
_free_models_lock = threading.Lock()

MAX_FALLBACK_ATTEMPTS = 8


def _preference_rank(model_id: str) -> int:
    low = model_id.lower()
    for rank, group in enumerate(_PREFERENCE_GROUPS):
        if any(pattern in low for pattern in group):
            return rank
    return len(_PREFERENCE_GROUPS)


def rank_free_models(model_ids: list[str]) -> list[str]:
    """مرتب‌سازی پایدارِ مدل‌های رایگان بر اساس اولویت (گروه، سپس نام)."""
    return sorted(dict.fromkeys(model_ids), key=lambda m: (_preference_rank(m), m))


def _is_free_model(entry: dict[str, Any]) -> bool:
    """آیا مدل رایگان است؟ :free در انتهای شناسه یا قیمت صفر prompt و completion."""
    model_id = (entry.get("id") or "").strip().lower()
    if not model_id:
        return False
    if model_id.endswith(":free"):
        return True
    pricing = entry.get("pricing") or {}

    def _zero(value: Any) -> bool:
        if value is None:
            return False
        try:
            return float(str(value).strip()) == 0.0
        except (TypeError, ValueError):
            return str(value).strip() == "0"

    return _zero(pricing.get("prompt")) and _zero(pricing.get("completion"))


class OpenRouterProvider(AIProvider):
    """پروایدر OpenRouter — یک API برای ده‌ها مدل (رایگان و پولی).

    پیش‌فرض‌ها:
      - OPENROUTER_API_KEY      : کلید API از https://openrouter.ai
      - OPENROUTER_MODEL        : شناسهٔ مدل (مثلاً nvidia/nemotron-3.5-super-vl:free) یا «auto» (کشف پویای مدل‌های رایگان)
      - OPENROUTER_BASE_URL     : پیش‌فرض https://openrouter.ai/api/v1
      - OPENROUTER_TIMEOUT_SECONDS          : مهلت پاسخ (پیش‌فرض ۶۰)
      - OPENROUTER_MIN_INTERVAL_SECONDS     : فاصله‌گذاری ملایم بین فراخوانی‌ها (پیش‌فرض ۱)
      - OPENROUTER_SITE_URL     : (اختیاری) HTTP-Referer
      - OPENROUTER_APP_NAME     : (اختیاری) X-Title (پیش‌فرض: Fahmyar App)
    """

    name = "openrouter"

    # هزینهٔ تقریبی مدل‌های پرداختی رایج (USD per 1K tokens) — برای مدل‌های `:free` صفر است
    _PRICING_PER_1K = {
        # مدل‌های رایگان
        "google/gemini-2.0-flash-exp:free": 0.0,
        "meta-llama/llama-3.3-70b-instruct:free": 0.0,
        "mistralai/mistral-7b-instruct:free": 0.0,
        "qwen/qwen-2.5-72b-instruct:free": 0.0,
        "deepseek/deepseek-chat:free": 0.0,
        "deepseek/deepseek-r1:free": 0.0,
    }

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        # پاکسازی کلید: فاصلهٔ انتهایی/خط جدید (.strip()) علت رایج خطای 401 است
        raw_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.api_key = (raw_key or "").strip()
        self.model_name = (model_name if model_name is not None else settings.OPENROUTER_MODEL).strip() or "auto"
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.timeout = settings.OPENROUTER_TIMEOUT_SECONDS
        self.min_interval = float(getattr(settings, "OPENROUTER_MIN_INTERVAL_SECONDS", 0.0) or 0.0)
        self.site_url = (getattr(settings, "OPENROUTER_SITE_URL", "") or "").strip()
        self.app_name = (getattr(settings, "OPENROUTER_APP_NAME", "Fahmyar App") or "Fahmyar App").strip() or "Fahmyar App"
        self._rate_lock = threading.Lock()
        self._last_call = 0.0
        if not self.api_key:
            raise AIProviderError(
                "OPENROUTER_API_KEY تنظیم نشده است. کلید را در .env قرار دهید "
                "یا AI_PROVIDER=mock را انتخاب کنید."
            )

    # ------------------------------------------------------------------
    # هدرها — روی همهٔ درخواست‌ها (کش، فهرست مدل‌ها، فال‌بک) اعمال می‌شود
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url or "https://fahmyar.ir",
            "X-Title": self.app_name,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    # ------------------------------------------------------------------
    # فاصله‌گذاری ملایم بین فراخوانی‌ها (برای پلن‌های رایگان مفید است)
    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._rate_lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    # ------------------------------------------------------------------
    # ابزارهای کمکی خروجی و هزینه
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """اگر مدل خروجی JSON را داخل ```json ... ``` گذاشته باشد، آن را پاک می‌کنیم."""
        stripped = text.strip()
        if stripped.startswith("```"):
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
        if (self.model_name or "").endswith(":free"):
            return 0.0
        price = self._PRICING_PER_1K.get(self.model_name)
        if price is None:
            # مدل ناشناخته — اگر در .env اعلام شده، از آن استفاده کن
            try:
                price = float(os.getenv("OPENROUTER_PRICE_PER_1K", "0") or 0.0)
            except ValueError:
                price = 0.0
        return round((token_count / 1000.0) * price, 6)

    # ------------------------------------------------------------------
    # کشف مدل‌های رایگان فعال — کش ۱۵ دقیقه‌ای
    # ------------------------------------------------------------------
    def fetch_active_free_models(self, force_refresh: bool = False) -> list[str]:
        """فهرست مدل‌های رایگان فعال OpenRouter را برمی‌گرداند (مرتب‌شده بر اساس اولویت).

        نتیجه ۱۵ دقیقه کش می‌شود؛ force_refresh=True یعنی دریافت تازه (پس از شکست مدل).
        """
        now = time.monotonic()
        with _free_models_lock:
            cached = _free_models_cache["models"]
            age = now - _free_models_cache["ts"]
            if not force_refresh and cached and age < _FREE_MODELS_TTL_SECONDS:
                return list(cached)

        import requests

        try:
            resp = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=30)
        except requests.RequestException as exc:
            with _free_models_lock:
                if _free_models_cache["models"]:
                    print(f"[OpenRouter] دریافت فهرست مدل‌ها ناموفق بود ({exc})؛ از کش (حتی قدیمی) استفاده شد.")
                    return list(_free_models_cache["models"])
            raise AIProviderError(f"خطای شبکه در دریافت فهرست مدل‌های OpenRouter: {exc}", retryable=True) from exc

        if resp.status_code >= 400:
            with _free_models_lock:
                if _free_models_cache["models"]:
                    print(f"[OpenRouter] HTTP {resp.status_code} از /models؛ از کش استفاده شد.")
                    return list(_free_models_cache["models"])
            raise AIProviderError(
                f"دریافت فهرست مدل‌ها از OpenRouter ناموفق بود (HTTP {resp.status_code}): {(resp.text or '')[:200]}",
                retryable=False,
            )

        try:
            entries = resp.json().get("data", [])
        except ValueError as exc:
            raise AIProviderError("پاسخ غیرJSON از /models دریافت شد.", retryable=True) from exc

        free_ids = [e["id"].strip() for e in entries if isinstance(e, dict) and _is_free_model(e)]
        ranked = rank_free_models(free_ids)
        with _free_models_lock:
            _free_models_cache.update(ts=time.monotonic(), models=ranked)
        return list(ranked)

    # ------------------------------------------------------------------
    # فراخوانی chat/completions
    # ------------------------------------------------------------------
    def _post_chat_completion(self, prompt: str, temperature: float, model: str) -> dict[str, Any]:
        import requests

        self._throttle()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _OPENROUTER_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
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
            raise AIProviderError(f"خطای شبکه در اتصال به OpenRouter (مدل {model}): {exc}", retryable=True) from exc

        if resp.status_code == 401:
            raise AIProviderError(
                f"خطای 401 از OpenRouter — کلید API یافت نشد یا نامعتبر است (پس از .strip() بررسی شد). "
                f"پاسخ سرور: {(resp.text or '')[:300]}",
                retryable=False,  # تعویض مدل ۴۰۱ را حل نمی‌کند
            )
        if resp.status_code >= 400:
            # 400/402/403/404/408/409/429/5xx — یعنی مدل ناموجود/پولی/محدود یا خطای سرور: فال‌بک منطقی است
            raise AIProviderError(
                f"خطای {resp.status_code} از OpenRouter (مدل {model}): {(resp.text or '')[:300]}",
                retryable=True,
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise AIProviderError(f"پاسخ غیرJSON از OpenRouter (مدل {model}).", retryable=True) from exc

    def _attempt(self, model: str, prompt: str, task_type: str, temperature: float) -> AIResponse:
        data = self._post_chat_completion(prompt, temperature, model)
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"ساختار پاسخ OpenRouter نامعتبر بود (مدل {model}): {exc}", retryable=True) from exc
        text = self._strip_markdown_fences(text)
        if not text:
            raise AIProviderError(f"پاسخ خالی از OpenRouter (مدل {model}).", retryable=True)

        usage = data.get("usage") or {}
        try:
            token_count = int(usage.get("total_tokens") or 0)
        except (TypeError, ValueError):
            token_count = 0
        if token_count <= 0:
            token_count = max(1, (len(prompt) + len(text)) // 4)
        try:
            cost_usd = float(usage.get("cost") or 0.0)
        except (TypeError, ValueError):
            cost_usd = 0.0
        if cost_usd == 0.0 and not model.endswith(":free"):
            # اگر مدل رایگان نباشد و سرور هزینه را صفر/خالی داده باشد، تخمین بزن
            cost_usd = self._estimate_cost(token_count)

        return AIResponse(
            text=text,
            model_name=model,
            token_count=token_count,
            cost_usd=cost_usd,
            task_type=task_type,
            raw=data,
        )

    # ------------------------------------------------------------------
    # تولید با فال‌بک خودکار بین مدل‌های رایگان فعال
    # ------------------------------------------------------------------
    async def generate(self, prompt: str, task_type: str, temperature: float = 0.7) -> AIResponse:
        # requests همزمان است؛ در thread اجرا می‌شود تا event loop قفل نشود
        return await asyncio.to_thread(self._generate_with_fallback, prompt, task_type, temperature)

    def _initial_candidates(self) -> list[str]:
        if self.model_name.lower() == "auto":
            return self.fetch_active_free_models()
        return [self.model_name]

    def _generate_with_fallback(self, prompt: str, task_type: str, temperature: float) -> AIResponse:
        attempted: set[str] = set()
        last_error: str | None = None
        current: str | None = None

        initial = self._initial_candidates()
        if not initial:
            raise AIProviderError("هیچ مدل رایگان فعالی در OpenRouter یافت نشد.", retryable=False)
        queue = list(initial)

        for _ in range(MAX_FALLBACK_ATTEMPTS):
            current = queue.pop(0) if queue else None
            if current is None:
                # صف تمام شد — با رفرش اجباری فهرست، مدل‌های نزده را پیدا کن
                free = self.fetch_active_free_models(force_refresh=True)
                current = next((m for m in free if m not in attempted), None)
            if current is None:
                break
            attempted.add(current)
            try:
                return self._attempt(current, prompt, task_type, temperature)
            except AIProviderError as exc:
                last_error = str(exc)
                if not exc.retryable:
                    raise  # ۴۰۱ و اشکال‌های ساختاری — تعویض مدل بی‌فایده است
                # رفرش اجباری فهرست پس از شکست (یعنی مدل پولی/حذف‌شده شده)
                free = self.fetch_active_free_models(force_refresh=True)
                # ادغام: مدل‌های تازه‌کشف‌شده اولویت دارند؛ سپس بقیهٔ صف؛ بدون تکرار
                merged_q = [m for m in free if m not in attempted] + [m for m in queue if m not in attempted]
                queue = list(dict.fromkeys(merged_q))
                upcoming = queue[0] if queue else None
                print(f"[OpenRouter Dynamic Fallback] Switched from {current} to {upcoming}")

        raise AIProviderError(
            f"همهٔ تلاش‌ها برای فراخوانی OpenRouter شکست خورد ({len(attempted)} مدل امتحان شد). "
            f"آخرین خطا: {last_error}",
            retryable=True,
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
        if task_type == "generate_question":
            text = self._mock_question(prompt)
        elif task_type == "generate_konkur_preview":
            text = self._mock_konkur_preview(prompt)
        elif task_type == "generate_test_booklet":
            text = self._mock_test_booklet(prompt)
        elif task_type == "analyze_exam":
            text = self._mock_exam_analysis(prompt)
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

    # --- قالب‌های قطعی: پیش‌نمایش چهارگزینه‌ای کنکوری ---
    _KONKUR_BANK = {
        "physics": [
            {"text": "بارِ نقطهای +Q در نقطهٔ A میدانِ E ایجاد کرده است. اگر فاصلهٔ A تا بار، دو برابر شود، بزرگیِ میدان در A چگونه تغییر می‌کند؟",
             "options": ["همان E باقی می‌ماند", "نصف می‌شود", "یک‌چهارم می‌شود", "دو برابر می‌شود"], "correct_answer": 3,
             "explanation": "میدان بار نقطه‌ای با مجذور فاصله نسبت عکس دارد (E متناسب با ۱ تقسیم بر r به توان ۲)؛ با دو برابر شدنِ فاصله، میدان یک‌چهارم می‌شود."},
            {"text": "مقاومت ۶ اهمی به منبع ولتاژ ۱۲ ولت بسته شده است. جریان عبوری از مدار چند آمپر است؟",
             "options": ["۱", "۲", "۳", "۴"], "correct_answer": 2,
             "explanation": "طبق قانون اهم I = V/R = 12/6 = 2 آمپر است."},
            {"text": "جسمی به جرم ۲ کیلوگرم با شتابِ ۳ متر بر مجذور ثانیه در راستای افقی حرکت می‌کند. نیروی خالص وارد بر جسم چند نیوتن است؟",
             "options": ["۵", "۶", "۱٫۵", "۹"], "correct_answer": 2,
             "explanation": "از قانون دوم نیوتن F = m·a = 2×3 = 6 نیوتن."},
            {"text": "پرتوی نور با زاویهٔ تابش ۳۰ درجه به آینهٔ تخت می‌تابد. زاویهٔ انعکاس نسبت به خطِ عمود چقدر است؟",
             "options": ["۱۵ درجه", "۳۰ درجه", "۶۰ درجه", "۹۰ درجه"], "correct_answer": 2,
             "explanation": "زاویهٔ تابش و زاویهٔ انعکاس (هر دو نسبت به عمود) برابرند؛ پس زاویهٔ انعکاس ۳۰ درجه است."},
            {"text": "دو بار همنام q1 و q2 در فاصلهٔ r از هم قرار دارند. اگر فاصلهٔ آن‌ها نصف شود، نیروی بین آن‌ها چه می‌شود؟",
             "options": ["نصف می‌شود", "همان‌طور می‌ماند", "دو برابر می‌شود", "چهار برابر می‌شود"], "correct_answer": 4,
             "explanation": "نیروی کولن با مجذور فاصله نسبت عکس دارد؛ نصف شدن فاصله ؛ بنابراین نیرو ۴ برابر می‌شود."},
        ],
        "chemistry": [
            {"text": "عدد اکسایش گوگرد (S) در H2SO4 کدام است؟",
             "options": ["+2", "+4", "+6", "−2"], "correct_answer": 3,
             "explanation": "مجموع اعداد اکسایش صفر است: 2(+1) + x + 4(−2) = 0 ؛ بنابراین x = +6."},
            {"text": "حجم ۲ مول گاز O2 در شرایط استاندارد (STP) تقریباً چند لیتر است؟",
             "options": ["۲۲٫۴", "۱۱٫۲", "۴۴٫۸", "۳۳٫۶"], "correct_answer": 3,
             "explanation": "هر مول گاز در STP برابر ۲۲٫۴ لیتر است؛ پس ۲ مول برابر ۴۴٫۸ لیتر است."},
            {"text": "کدام یک از ترکیب‌های زیر بیشترین قطبیتِ پیوند را دارد؟",
             "options": ["H–H", "Cl–Cl", "H–Cl", "C–C"], "correct_answer": 3,
             "explanation": "اختلاف الکترونگاتیوی H و Cl بزرگ‌ترینِ این گزینه‌هاست (~0.9)؛ پیوند H–Cl قطبی‌ترین است."},
            {"text": "در واکنشِ سوختنِ کامل متان (CH4) با اکسیژن، نسبت مول اکسیژن به متان کدام است؟",
             "options": ["۱ به ۱", "۲ به ۱", "۳ به ۱", "۴ به ۱"], "correct_answer": 2,
             "explanation": "CH4 + 2O2 = CO2 + 2H2O؛ نسبت مولی اکسیژن به متان ۲ است."},
            {"text": "کدام گونهٔ زیر بازِ مزدوجِ H2O است؟",
             "options": ["H3O+", "OH-", "O2-", "H2O2"], "correct_answer": 2,
             "explanation": "بازِ مزدوج از حذف یک پروتون ساخته می‌شود؛ H2O با از دست دادن یک یون هیدروژن به OH- تبدیل می‌شود."},
        ],
        "calculus": [
            {"text": "مشتق تابع y = x³ − 3x کدام است؟",
             "options": ["y′ = 3x² − 3", "y′ = x² − 3", "y′ = 3x² + 3", "y′ = 3x − 3"], "correct_answer": 1,
             "explanation": "طبق قاعدهٔ مشتقِ توان: مشتق x³ برابر 3x² و مشتق −3x برابر −3 است."},
            {"text": "مقدار لگاریتم ۱۶ در پایه ۲ برابر است با:",
             "options": ["۳", "۴", "۵", "۸"], "correct_answer": 2,
             "explanation": "16 = 2 به توان 4 است؛ پس لگاریتم 16 در پایه 2 برابر 4 است."},
            {"text": "دامنهٔ تابع f(x) = √(x − 1) کدام است؟",
             "options": ["x ≥ 0", "x ≥ 1", "x > 1", "تمام اعداد حقیقی"], "correct_answer": 2,
             "explanation": "زیرِ رادیکال باید نامنفی باشد: x − 1 ≥ 0 است؛ پس x ≥ 1."},
            {"text": "حدِ (sin x) تقسیم بر x وقتی x به صفر میل می‌کند برابر است با:",
             "options": ["۰", "۱", "∞", "تعریف‌ناپذیر"], "correct_answer": 2,
             "explanation": "حدِ معروفِ تابعِ سینک؛ زیرا sin x در نزدیکی صفر تقریباً برابر x است."},
            {"text": "اگر f(x) = x² مشتق‌پذیر باشد، مقدار f′(3) چقدر است؟",
             "options": ["۳", "۶", "۹", "۲"], "correct_answer": 2,
             "explanation": "f′(x) = 2x؛ پس f′(3) = 6."},
        ],
        "discrete": [
            {"text": "تعداد زیرمجموعه‌های ۴ عضوی از یک مجموعهٔ ۶ عضوی چندتاست؟",
             "options": ["۱۵", "۲۰", "۳۰", "۲۴"], "correct_answer": 1,
             "explanation": "ترکیب 4 از 6: ترکیب 4 از 6 برابر 6! تقسیم بر (4! ضربدر 2!) = 15."},
            {"text": "گرافی کامل با ۵ رأس، چند یال دارد؟",
             "options": ["۵", "۸", "۱۰", "۱۲"], "correct_answer": 3,
             "explanation": "گرافِ کاملِ K دارای n(n−1)/2 یال است؛ برای n=5: 5×4/2 = 10."},
            {"text": "باقیماندهٔ تقسیم ۲ به توان ۱۰ بر ۵ کدام است؟",
             "options": ["۱", "۲", "۳", "۴"], "correct_answer": 4,
             "explanation": "۲ به توان ۱۰ برابر ۱۰۲۴ است؛ ۱۰۲۴ = ۵ × ۲۰۴ + ۴؛ باقیمانده ۴ است."},
            {"text": "تعداد جواب‌های صحیح نامنفیِ معادلهٔ x + y + z = 6 چندتاست؟",
             "options": ["۲۸", "۲۱", "۳۵", "۱۲"], "correct_answer": 1,
             "explanation": "قضیهٔ ستاره و خط: C(6+3−1, 3−1) = C(8,2) = 28."},
            {"text": "کدام رابطه هم بازتابی است و هم متقارن ولی پادتقارنی نیست (روی مجموعهٔ اعداد حقیقی)؟",
             "options": ["a ≤ b", "a = b", "a ≠ b", "a > b"], "correct_answer": 2,
             "explanation": "تساوی بازتابی و متقارن است؛ پادتقارنی نیست زیرا از a=b و b=a نمی‌توان نتیجه گرفت a=b>… به‌طور کلی تساوی معادلِ هر دو جهت است."},
        ],
        "geometry": [
            {"text": "در مثلث قائم‌الزاویه‌ای، دو ضلع قائم ۳ و ۴ سانتی‌مترند. وتر چند سانتی‌متر است؟",
             "options": ["۵", "۶", "۷", "√۷"], "correct_answer": 1,
             "explanation": "طبق قضیهٔ فیثاغورس: 3² + 4² = 25 است؛ پس وتر = ۵."},
            {"text": "مساحتِ دایره‌ای به شعاع ۲ سانتی‌متر چقدر است؟",
             "options": ["۲ پی", "۴ پی", "۶ پی", "پی"], "correct_answer": 2,
             "explanation": "مساحت دایره = پی ضربدر r² = پی ضربدر ۴ = ۴ پی."},
            {"text": "زاویهٔ مرکزی مقابل به یک کمان، دو برابر زاویهٔ محاطیِ مقابل به همان کمان است. اگر زاویهٔ محاطی ۲۵° باشد، زاویهٔ مرکزی چقدر است؟",
             "options": ["۱۲٫۵°", "۲۵°", "۵۰°", "۱۰۰°"], "correct_answer": 3,
             "explanation": "رابطهٔ زاویهٔ مرکزی و محاطی: مرکزی = ۲ × محاطی = ۵۰°."},
            {"text": "مساحتِ ذوزنقه‌ای با قاعده‌های ۴ و ۶ سانتی‌متر و ارتفاع ۵ سانتی‌متر چند سانتی‌متر مربع است؟",
             "options": ["۲۵", "۲۰", "۳۰", "۲۴"], "correct_answer": 1,
             "explanation": "مساحت ذوزنقه = (مجموع قاعده‌ها × ارتفاع) ÷ ۲ = (4+6)×5/2 = 25."},
            {"text": "در یک مکعب، زاویهٔ بین قطرِ مکعب و قاعدهٔ آن تقریباً چند درجه است؟",
             "options": ["۳۰°", "۳۵°", "۴۵°", "۶۰°"], "correct_answer": 2,
             "explanation": "ضلع را a بگیرید: قطر قاعده = a√2؛ تانژانتِ زاویه = a تقسیم بر (a√2) = 1/√2؛ پس زاویه تقریباً ۳۵ درجه است."},
        ],
        "biology": [
            {"text": "در کدام مرحلهٔ میتوز، کروماتیدهای خواهر از هم جدا می‌شوند؟",
             "options": ["پروفاز", "متافاز", "آنافاز", "تلوفاز"], "correct_answer": 3,
             "explanation": "در آنافاز رشته‌های دوک کوتاه می‌شوند و کروماتیدها به دو قطب می‌روند."},
            {"text": "محصولِ نهاییِ مرحلهٔ نوریِ فتوسنتز چیست؟",
             "options": ["گلوکز", "ATP و NADPH", "CO2", "آب و اکسیژن"], "correct_answer": 2,
             "explanation": "مرحلهٔ نوری نور را به انرژی شیمیایی (ATP و NADPH) تبدیل می‌کند و O2 آزاد می‌شود."},
            {"text": "کدام بازِ نیتروژنی فقط در RNA یافت می‌شود؟",
             "options": ["آدنین", "گوانین", "تیمین", "یوراسیل"], "correct_answer": 4,
             "explanation": "در RNA به‌جای تیمین، یوراسیل وجود دارد."},
            {"text": "واحد سازندهٔ پروتئین‌ها کدام است؟",
             "options": ["گلوکز", "نوکلئوتید", "اسید آمینه", "اسید چرب"], "correct_answer": 3,
             "explanation": "پروتئین‌ها زنجیره‌های اسید آمینه هستند که با پیوند پپتیدی به هم متصل شده‌اند."},
            {"text": "کدام ترکیب، ذخیرهٔ اصلیِ انرژی در سلول‌های جانوری است؟",
             "options": ["گلوکز", "گلیکوژن", "نشاسته", "سلولز"], "correct_answer": 2,
             "explanation": "در جانوران، گلوکز اضافی به‌صورت گلیکوژن در کبد و ماهیچه ذخیره می‌شود."},
        ],
        "math": [
            {"text": "ریشه‌های معادلهٔ x² − 5x + 6 = 0 کدام‌اند؟",
             "options": ["۲ و ۳", "۱ و ۶", "−۲ و −۳", "۰ و ۵"], "correct_answer": 1,
             "explanation": "(x−2)(x−3) = 0 است؛ پس x = 2 و 3."},
            {"text": "امیدِ ریاضیِ پرتاب یک تاسِ سالم چند است؟",
             "options": ["۳", "۳٫۵", "۴", "۴٫۵"], "correct_answer": 2,
             "explanation": "امید ریاضی = (1+2+…+6)/6 = 21/6 = 3.5."},
            {"text": "دامنهٔ تابع f(x) = 1/(x − 2) کدام است؟",
             "options": ["تمام اعداد حقیقی", "x ≠ 2", "x > 2", "x ≥ 2"], "correct_answer": 2,
             "explanation": "مخرج نباید صفر شود: x − 2 ≠ 0 است؛ پس x ≠ 2."},
            {"text": "مشتق تابع f(x) = 2x² + 3x چیست؟",
             "options": ["f′(x) = 2x + 3", "f′(x) = 4x + 3", "f′(x) = 4x² + 3", "f′(x) = x + 3"], "correct_answer": 2,
             "explanation": "مشتق 2x² برابر 4x و مشتق 3x برابر 3 است."},
            {"text": "میانگین داده‌های ۲، ۴، ۶، ۸ چقدر است؟",
             "options": ["۴", "۵", "۶", "۴٫۵"], "correct_answer": 2,
             "explanation": "میانگین = (2+4+6+8)/4 = 20/4 = 5."},
        ],
    }

    def _mock_konkur_preview(self, prompt: str) -> str:
        subject = _extract_marker(prompt, "SUBJECT") or "physics"
        topic = _extract_marker(prompt, "TOPIC") or "مبحث کلی"
        try:
            count = max(1, min(20, int(_extract_marker(prompt, "COUNT") or "5")))
        except ValueError:
            count = 5
        difficulty = _extract_marker(prompt, "DIFFICULTY") or "متوسط"
        custom = _extract_marker(prompt, "CUSTOM")
        bank = self._KONKUR_BANK.get(subject) or self._KONKUR_BANK["physics"]
        tags = ["کنکور ۱۴۰۲", "قلم‌چی", "تألیفی AI"]
        items = []
        for i in range(count):
            base = bank[i % len(bank)]
            text = base["text"]
            if custom:
                text = f"{text}"
            items.append({
                "id": i + 1,
                "text": text,
                "options": list(base["options"]),
                "correct_answer": int(base["correct_answer"]),
                "source_tag": tags[i % len(tags)],
                "explanation": base["explanation"],
            })
        return json.dumps(items, ensure_ascii=False)

    # --- قالب‌های قطعی ---
    def _mock_test_booklet(self, prompt: str) -> str:
        proposition = _extract_marker(prompt, "PROPOSITION") or "گزارهٔ هدفِ نمونه"
        misconception = _extract_marker(prompt, "MISCONCEPTION") or "بدفهمیِ رایجِ نمونه"
        concept = _extract_marker(prompt, "CONCEPT") or "مفهوم نمونه"
        svg1 = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                '<line x1="44" y1="228" x2="372" y2="228" stroke="black" stroke-width="2"/>'
                '<line x1="44" y1="228" x2="44" y2="40" stroke="black" stroke-width="2"/>'
                '<rect x="96" y="176" width="36" height="52" fill="none" stroke="black" stroke-width="2"/>'
                '<rect x="182" y="116" width="36" height="112" fill="none" stroke="black" stroke-width="2"/>'
                '<rect x="268" y="56" width="36" height="172" fill="none" stroke="black" stroke-width="2"/>'
                '<text x="114" y="268" font-size="12" text-anchor="middle">A</text>'
                '<text x="200" y="268" font-size="12" text-anchor="middle">B</text>'
                '<text x="286" y="268" font-size="12" text-anchor="middle">C</text></svg>')
        svg2 = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                '<circle cx="90" cy="150" r="18" fill="none" stroke="black" stroke-width="2"/>'
                '<line x1="90" y1="132" x2="90" y2="70" stroke="black" stroke-width="2"/>'
                '<line x1="90" y1="70" x2="180" y2="70" stroke="black" stroke-width="2"/>'
                '<rect x="180" y="56" width="64" height="28" fill="none" stroke="black" stroke-width="2"/>'
                '<line x1="244" y1="70" x2="320" y2="70" stroke="black" stroke-width="2"/>'
                '<line x1="320" y1="70" x2="320" y2="232" stroke="black" stroke-width="2"/>'
                '<line x1="320" y1="232" x2="210" y2="232" stroke="black" stroke-width="2"/>'
                '<circle cx="200" cy="232" r="10" fill="none" stroke="black" stroke-width="2"/>'
                '<line x1="190" y1="232" x2="90" y2="232" stroke="black" stroke-width="2"/>'
                '<line x1="90" y1="232" x2="90" y2="168" stroke="black" stroke-width="2"/>'
                '<text x="212" y="32" font-size="12" text-anchor="middle">R</text>'
                '<text x="46" y="154" font-size="12" text-anchor="middle">V</text>'
                '<text x="200" y="280" font-size="12" text-anchor="middle">A</text></svg>')
        qs = [
            ("conceptual", f"یک تکنسین تعمیرات، دستگاهی را که با «{concept}» کار می‌کند بررسی کرده و نتیجهٔ A گرفته است؛ مهندس ناظر معتقد است نتیجه A اشتباه است. دقیقاً بنویسید کجای استدلال A می‌شکند و زنجیرهٔ علّیِ درست چیست.", "hard"),
            ("real_world", f"در خطِ تولید یک کارخانهٔ قطعه‌سازی، یک قطعهٔ مشخص به‌صورت تکرارشونده پس از چند هفته کار می‌سوزد. شرایط زیر را خودتان تکمیل کنید: دمای محیط، جنس قطعه، شدت بار و زمان کارکرد. چه اتفاقی دقیقاً رخ می‌دهد (مشاهده) و علت ریشه‌ای آن چیست (تفسیر)؟", "hard"),
            ("diagram", "به نمودار داده‌شده نگاه کنید (محورِ عمودی y و سه نمونه A، B، C). کدام نمونه با بقیه سازگار نیست و چرا؟ به محورها و شیب خط‌ها ارجاع دهید.", "medium"),
            ("misconception_trap", f"هم‌کلاسی شما می‌گوید: «{misconception}» و اضافه می‌کند: «وقتی عدد را بزرگ‌تر می‌کنم خروجی هم بزرگ‌تر می‌شود؛ پس همین رابطه در همهٔ جاها درست است.» دقیقاً نقطهٔ فروپاشی این استدلال را پیدا کنید و یک مثالِ نقض بیاورید.", "hard"),
            ("computational", "جدول زیر را برای یک مدار/فرایند واقعی بخوانید و مقادیر خواسته‌شده را محاسبه کنید؛ سپس بنویسید چرا این رابطه برقرار است:\n| کمیت | مقدار | واحد |\n|---|---|---|\n| V | ۱۲ | ولت |\n| R | ۴ | اهم |\n| I | ؟ | آمپر |", "easy"),
            ("conceptual", f"موقعیتی را تصور کنید که خلاف شهود روزمره دربارهٔ «{concept}» است — مثلاً چیزی که انتظار دارید افزایش یابد، اصلاً تغییر نمی‌کند. چه اتفاقی می‌افتد؟ چرا شهود اولیه‌تان گمراهتان کرد؟", "medium"),
            ("conceptual", "یک دانش‌آموز فرضی در دفترچه‌اش نوشته: «این اتفاق می‌افتد چون نیرو بیشتر می‌شود.» دقیقاً مشخص کنید: چه چیزی در این جمله درست است؟ چه چیزی غلط است؟ چرا؟", "medium"),
            ("real_world", "یک پیوند مشخص بین این مفهوم و یک مبحث ریاضی دهم/یازدهم (تناسب، درصد، یا شیب نمودار) در یک موقعیت واقعی بسازید؛ داده‌ها را فرض کنید و نشان دهید این ابزار ریاضی چه تصمیمی را در آن موقعیت ممکن می‌کند.", "hard"),
            ("diagram", "با توجه به مدار/نمودار روبه‌رو (منبع V، مقاومت R و آمپرمتر A): اگر R دو برابر شود چه اتفاقی برای جریان می‌افتد؟ پاسخ خود را فقط با خواندنِ شکل و قانونِ حاکم بنویسید، نه با حفظ کردن.", "hard"),
        ]
        items = []
        for i, (exam_type, text, diff) in enumerate(qs, start=1):
            diagram = svg1 if i == 3 else (svg2 if i == 9 else None)
            items.append({
                "order": i,
                "exam_type": exam_type,
                "text": text,
                "difficulty": diff,
                "cognitive_type": "conceptual" if exam_type in ("conceptual", "real_world", "diagram") else ("computational" if exam_type == "computational" else "recall"),
                "mapped_propositions": [proposition],
                "diagram_svg": diagram,
                "misconception_targeted": misconception if exam_type == "misconception_trap" else None,
            })
        return json.dumps({"questions": items}, ensure_ascii=False)

    def _mock_exam_analysis(self, prompt: str) -> str:
        answers_raw = _extract_marker(prompt, "ANSWERS") or ""
        propositions_raw = _extract_marker(prompt, "PROPOSITIONS") or "[]"
        try:
            propositions = json.loads(propositions_raw)
        except json.JSONDecodeError:
            propositions = ["گزارهٔ هدف"]
        sections = re.split(r"<<<Q(\d+)>>>", answers_raw)
        per_question = []
        pairs = list(zip(sections[1::2], sections[2::2])) if len(sections) >= 3 else []
        for order_str, body in pairs:
            m_qid = re.search(r"question_id=(\d+)", body)
            try:
                qid = int(m_qid.group(1)) if m_qid else int(order_str)
            except ValueError:
                qid = int(order_str)
            text = body.strip()
            low = text.lower()
            has_reasoning = any(m in text for m in _REASONING_MARKERS)
            uncertain = any(m in text for m in _UNCERTAINTY_MARKERS)
            words = len(text.split())
            mis_marker = any(w in text for w in ("اشتباه", "غلط", "نادرست", "تضاد", "برعکس", "معکوس", "NEEDS_REVIEW"))
            if uncertain or words < 4:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.25
                reasoning = "پاسخ بسیار کوتاه یا همراه با عدم اطمینان است — نمی‌توان داوری کرد."
            elif mis_marker:
                status, etype, conf = "NEEDS_REVIEW", "strong_contradicting", 0.9
                reasoning = "دانش‌آموز به اشتباه تصور می‌کند که رابطهٔ فاصله/کمیت خطی و مستقیم است؛ مبانی علمی خلاف آن را نشان می‌دهند."
            elif has_reasoning and words >= 25:
                status, etype, conf = "CONFIRMED", "strong_confirming", 0.8
                reasoning = "استدلال علمی کامل و علّی است."
            elif has_reasoning:
                status, etype, conf = "LIKELY_UNDERSTOOD", "strong_confirming", 0.7
                reasoning = "هستهٔ فهم درست است اما بیان کامل نیست."
            elif words >= 12:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.45
                reasoning = "پاسخ بدون استدلال صریح داده شده — واژهٔ کلیدی بدون دلیل، شواهد نیست."
            else:
                status, etype, conf = "UNCLEAR", "weak_confirming", 0.3
                reasoning = "پاسخ کوتاه و بدون استدلال صریح است."
            per_question.append({
                "question_id": int(qid),
                "status": status,
                "evidence_type": etype,
                "error_type": "conceptual" if status == "NEEDS_REVIEW" else "none",
                "reasoning": reasoning,
                "confidence": conf,
                "needs_teacher_review": status == "UNCLEAR",
                "qualitative_feedback": reasoning,
            })
        wrong = sum(1 for q in per_question if q["status"] == "NEEDS_REVIEW")
        def _first_status(i: int) -> str:
            return per_question[i]["status"] if len(per_question) > i else "UNCLEAR"

        dimensions = [
            {"dimension": "درک مفهومی و علّی", "status": _first_status(0),
             "finding": "بر اساس پاسخ‌های تشریحیِ بخش مفهومی نوشته شد."},
            {"dimension": "کاربرد در دنیای واقعی", "status": _first_status(1),
             "finding": "بر اساس سناریوهای کارگاهی و زندگی واقعی نوشته شد."},
            {"dimension": "مهارت‌های کمی و محاسباتی", "status": _first_status(4),
             "finding": "بر اساس سؤال محاسباتی و گام‌های حل نوشته شد."},
            {"dimension": "بازنمایی نموداری و تصویری", "status": _first_status(2),
             "finding": "بر اساس سؤال نموداری و خواندن محورها نوشته شد."},
            {"dimension": "مواجهه با تله‌ها و بدفهمی‌ها", "status": _first_status(3),
             "finding": "بر اساس تلهٔ بدفهمی شایع نوشته شد."},
            {"dimension": "شفافیت بیان و خودپایشی", "status": _first_status(5),
             "finding": "بر اساس شفافیت تعریف و بیان دانش‌آموز نوشته شد."},
        ]
        root_causes = [
            {"area": "نسبت و تناسب معکوس ریاضی دهم",
             "reasoning": "در سؤالات ۵ و ۷، دانش‌آموز با دو برابر شدن مقاومت انتظارِ افزایشِ جریان داشت؛ یعنی تناسب معکوس I = V/R را مانند تناسب مستقیم خوانده است — ریشه در پیش‌نیازِ ریاضی تناسب معکوس است.",
             "cross_subject": True},
        ] if wrong else []
        suggestions = [
            "ابتدا پیش‌نیازهای ریاضیِ نسبت و توان را مرور کنید (۱۵ دقیقه تمرین هدفمند).",
            "برای هر گزارهٔ «بدفهمی شناسایی‌شده» یک مثالِ نقضِ شهودی طراحی کنید و خودتان برای یک دوست توضیح دهید.",
            "یک نمونهٔ واقعی از زندگی روزمره بسازید که در آن قانون/مفهوم کار می‌کند و علت را بلند بلند توضیح دهید.",
        ]
        return json.dumps(
            {"per_question": per_question, "dimension_findings": dimensions,
             "root_cause_hypotheses": root_causes, "improvement_suggestions": suggestions},
            ensure_ascii=False,
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
    "generate_test_booklet": "gemini_free",
    "analyze_response": "gemini_free",
    "analyze_exam": "gemini_free",
    "build_graph": "gemini_free",
}

_OPENROUTER_ROUTE = {
    "generate_question": "openrouter",
    "generate_test_booklet": "openrouter",
    "analyze_response": "openrouter",
    "analyze_exam": "openrouter",
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
        elif self.provider_name == "openrouter":
            key = _OPENROUTER_ROUTE.get(task_type, "openrouter")
        else:
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