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

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        cost_usd: float = 0.0,
        token_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        # هزینه/توکنِ همین تلاشِ شکست‌خورده — تا در حسابداریِ کل گم نشود.
        self.cost_usd = cost_usd
        self.token_count = token_count


@dataclass
class AIResponse:
    text: str
    model_name: str
    token_count: int
    cost_usd: float = 0.0
    task_type: str = ""
    raw: Optional[dict[str, Any]] = field(default=None, repr=False)
    # حسابداریِ تلاش‌ها: هزینهٔ فراخوانیِ موفق *به‌تنهایی* گزارش نشود؛
    # تلاش‌های شکست‌خورده‌ای که سمتِ سرویس‌دهنده توکن سوزانده‌اند هم حساب‌اند.
    attempts: int = 1
    failed_cost_usd: float = 0.0
    failed_tokens: int = 0
    # تفکیکِ توکن از usage پاسخ (اگر سرویس داده باشد)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_cost_usd(self) -> float:
        """جمعِ هزینهٔ همهٔ تلاش‌ها — آنچه باید در بودجه و لاگ بنشیند."""
        return round(self.cost_usd + self.failed_cost_usd, 6)

    @property
    def total_tokens(self) -> int:
        return self.token_count + self.failed_tokens


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
# کش لیست مدل‌های رایگان — مشترک بین همهٔ نمونه‌ها
_FREE_MODELS_TTL_SECONDS = 15 * 60
_free_models_cache: dict[str, Any] = {"ts": 0.0, "models": []}
_free_models_lock = threading.Lock()

MAX_FALLBACK_ATTEMPTS = 8
#: برای مدلِ پین‌شدهٔ ارزیابی، سه تلاش روی همان مدل و تمام. هیچ مدلِ دیگری
#: جایش را نمی‌گیرد و صفِ retry بی‌نهایت نمی‌شود.
#: حداکثر «تلاشِ مجدد» = ۲ (یعنی در مجموع حداکثر ۳ فراخوانی، اولی + دو retry).
#: بیشتر از این، کاربر را معطل می‌کند و اعتبار را غیرقابل‌پیش‌بینی.
PINNED_MODEL_MAX_ATTEMPTS = int(os.getenv("OPENROUTER_PINNED_MAX_ATTEMPTS", "2")) + 1


def _preference_rank(model_id: str) -> int:
    """رتبهٔ اولویتِ یک مدل در فهرستِ زندهٔ رایگان (۰ = بهترین).

    قبلاً این تابع یک فهرستِ دستی از نام‌ها را می‌گشت
    (`llama-3.3-70b`، `qwen-2.5-72b`). آن مدل‌ها دیگر در فهرست رایگان
    نیستند، پس هر مدلی به گروهِ آخر می‌افتاد و ترتیب عملاً تصادفی بود.
    اکنون امتیاز از `ai.model_catalog` می‌آید که خودش از دادهٔ زندهٔ
    OpenRouter (JSON mode، شاخصِ هوش، پنجرهٔ زمینه، فیلترِ محتوا) می‌سازد.
    """
    from ai.model_catalog import fetch_free_models

    try:
        models = fetch_free_models()
    except Exception:
        return len(model_id)  # بدونِ کاتالوگ، ترتیبِ الفبایی
    for index, model in enumerate(models):
        if model.id == model_id:
            return index
    return len(models)


def rank_free_models(model_ids: list[str]) -> list[str]:
    """مرتب‌سازیِ مدل‌ها بر اساسِ امتیازِ زندهٔ کاتالوگ."""
    unique = list(dict.fromkeys(model_ids))
    return sorted(unique, key=lambda m: (_preference_rank(m), m))


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

    # قیمت هیچ‌جا هاردکد نمی‌شود: هزینه فقط از usage.cost پاسخِ OpenRouter
    # خوانده می‌شود (نگاه کنید به _usage_from).

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        # پاکسازی کلید: فاصلهٔ انتهایی/خط جدید (.strip()) علت رایج خطای 401 است
        raw_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.api_key = (raw_key or "").strip()
        self.model_name = (model_name if model_name is not None else settings.OPENROUTER_MODEL).strip() or "auto"
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        # تایم‌اوت از .env خوانده می‌شود (OPENROUTER_TIMEOUT_SECONDS)؛
        # عددِ ۱۸۰ِ هاردکد با ۶۰ ثانیهٔ تنظیمات تناقض داشت و کدام‌شان برنده
        # می‌شد به ترتیبِ ساختِ شیء بستگی داشت.
        self.timeout = float(getattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 60) or 60)
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

    @staticmethod
    def _usage_from(
        data: dict[str, Any], prompt: str, text: str, model: str
    ) -> tuple[int, float, int, int]:
        """توکن و هزینهٔ **واقعیِ گزارش‌شدهٔ OpenRouter** را برمی‌گرداند.

        قیمت هیچ‌جا هاردکد نمی‌شود: اگر پاسخ فیلد ``usage.cost`` داشت، همان
        مرجع است. تخمینِ توکن فقط وقتی زده می‌شود که سرور ``usage`` نداده باشد،
        و هزینه در آن حالت صفر می‌ماند — چون «حدسِ قیمت» بدتر از «صفرِ صادق»
        است: بودجه را بی‌دلیل می‌بلعد و عددی در گزارش می‌نشاند که واقعی نیست.
        """
        usage = data.get("usage") or {}

        def _int(key: str) -> int:
            try:
                return int(usage.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        prompt_tokens = _int("prompt_tokens")
        completion_tokens = _int("completion_tokens")
        token_count = _int("total_tokens")
        if token_count <= 0:
            token_count = prompt_tokens + completion_tokens
        if token_count <= 0:
            token_count = max(1, (len(prompt) + len(text)) // 4)

        cost_usd = 0.0
        for key in ("cost", "total_cost"):
            raw = usage.get(key)
            if raw is None:
                continue
            try:
                cost_usd = float(raw)
                break
            except (TypeError, ValueError):
                continue
        return token_count, round(cost_usd, 8), prompt_tokens, completion_tokens

    # ------------------------------------------------------------------
    # کشف مدل‌های رایگان فعال — کش ۱۵ دقیقه‌ای
    # ------------------------------------------------------------------
    def fetch_active_free_models(self, force_refresh: bool = False) -> list[str]:
        """شناسهٔ مدل‌های رایگانِ فعال، از بهترین به بدترین.

        منطقِ انتخاب در `ai.model_catalog` است تا جداگانه آزمون‌پذیر باشد.
        نتیجه ۱۵ دقیقه کش می‌شود.
        """
        from ai.model_catalog import fetch_free_models

        try:
            models = fetch_free_models(
                api_key=self.api_key, force_refresh=force_refresh, timeout=30.0
            )
        except Exception as exc:  # noqa: BLE001
            with _free_models_lock:
                if _free_models_cache["models"]:
                    print(f"[OpenRouter] کراولِ مدل‌ها ناموفق بود ({exc})؛ از کشِ درون‌حافظه استفاده شد.")
                    return list(_free_models_cache["models"])
            raise AIProviderError(
                f"دریافت فهرست مدل‌های OpenRouter ناموفق بود: {exc}", retryable=True
            ) from exc

        ids = [m.id for m in models]
        with _free_models_lock:
            _free_models_cache.update(ts=time.monotonic(), models=ids)
        return list(ids)

    # ------------------------------------------------------------------
    # فراخوانی chat/completions
    # ------------------------------------------------------------------
    @staticmethod
    def _model_supports_json(model: str) -> bool:
        """آیا این مدل ``response_format`` را پشتیبانی می‌کند؟ (از کاتالوگ)

        فرستادنِ ``response_format`` به مدلی که پشتیبانی نمی‌کند، خطای ۴۰۰
        می‌دهد و کلِ زنجیرهٔ fallback را بیهوده می‌سوزاند.
        """
        from ai.model_catalog import fetch_free_models

        try:
            for candidate in fetch_free_models():
                if candidate.id == model:
                    return candidate.supports_json
        except Exception:  # noqa: BLE001
            pass
        return False

    def _post_chat_completion(self, prompt: str, temperature: float, model: str) -> dict[str, Any]:
        import requests

        self._throttle()

        # سقفِ خروجی: بدونِ آن، مدل‌های استدلالی همهٔ بودجه را صرف فیلدِ
        # reasoning می‌کنند و content خالی می‌ماند. ۸۰۰۰ برای پاسخِ ارزیابیِ
        # کامل (چند یافته + تحلیلِ پنج سؤال) کافی است.
        max_tokens = int(
            getattr(settings, "OPENROUTER_MAX_TOKENS", 16000) or 16000
        )

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": _OPENROUTER_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # JSON mode: قراردادِ موتور فهم‌سنجی به json.loads تکیه می‌کند. اگر مدل
        # آن را پشتیبانی کند، تضمینِ ساختار رایگان به دست می‌آید. اگر نکند،
        # OpenRouter خطا می‌دهد؛ پس فقط برای مدل‌هایی می‌فرستیم که کاتالوگ
        # اعلامشان کرده است.
        if self._model_supports_json(model):
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                # مهلت هر تلاش از تنظیمات خوانده می‌شود. با ۸ مدلِ نامزد، مهلتِ
                # ۱۸۰ ثانیه‌ای یعنی بدترین حالت ۲۴ دقیقه — بیشتر از تحملِ هر
                # درخواستِ HTTP. ۶۰ ثانیه برای یک تولیدِ کامل کافی است.
                timeout=float(getattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 60) or 60),
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
        choice = (data.get("choices") or [{}])[0]
        try:
            text = (choice["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"ساختار پاسخ OpenRouter نامعتبر بود (مدل {model}): {exc}", retryable=True) from exc

        # مدل‌های استدلالی می‌توانند کلِ بودجهٔ توکن را صرفِ فیلدِ reasoning کنند و
        # content را null بگذارند (finish_reason = "length"). نتیجه یک پاسخِ
        # «خالی» است که بی‌دلیل به نظر می‌رسد. این حالت را صریح گزارش می‌کنیم تا
        # در لاگ معلوم باشد مشکل از سهمیه/طول است، نه از مدل.
        if not text:
            reason = choice.get("finish_reason") or ""
            reasoning = (choice.get("message") or {}).get("reasoning") or ""
            if reason == "length" and reasoning:
                raise AIProviderError(
                    f"مدل {model} همهٔ توکن‌ها را صرفِ استدلال کرد و پاسخ نهایی نداد "
                    "(finish_reason=length). سقفِ max_tokens یا max_completion_tokens را بالا ببرید.",
                    retryable=True,
                )
            if reason == "content_filter":
                raise AIProviderError(
                    f"مدل {model} پاسخ را به‌دلیلِ فیلترِ محتوا قطع کرد.", retryable=True
                )

        text = self._strip_markdown_fences(text)
        if not text:
            raise AIProviderError(f"پاسخ خالی از OpenRouter (مدل {model}).", retryable=True)

        token_count, cost_usd, prompt_tokens, completion_tokens = self._usage_from(
            data, prompt, text, model
        )

        return AIResponse(
            text=text,
            model_name=model,
            token_count=token_count,
            cost_usd=cost_usd,
            task_type=task_type,
            raw=data,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    # ------------------------------------------------------------------
    # تولید با فال‌بک خودکار بین مدل‌های رایگان فعال
    # ------------------------------------------------------------------
    async def generate(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.7,
        model_override: str | None = None,
    ) -> AIResponse:
        # requests همزمان است؛ در thread اجرا می‌شود تا event loop قفل نشود
        return await asyncio.to_thread(
            self._generate_with_fallback, prompt, task_type, temperature, model_override
        )

    def _initial_candidates(self, model_override: str | None = None) -> list[str]:
        """مدل‌های نامزد، به ترتیب.

        ``model_override`` (یا مدلِ پین‌شدهٔ ارزیابی) **صریح** است: فقط همان
        مدل امتحان می‌شود و هیچ مدلِ رایگانِ دیگری جایش را نمی‌گیرد. دلیلش
        این است که سوییچِ خاموش به مدلِ دیگر، کیفیتِ ارزیابی را بی‌آنکه کسی
        بفهمد عوض می‌کند و هزینه هم قابلِ پیش‌بینی نیست.

        فقط در حالتِ ``OPENROUTER_MODEL=auto`` (بقیهٔ وظایف) فهرستِ رایگان
        کشف می‌شود — همان رفتارِ قبلیِ همان مسیر.
        """
        if model_override and model_override.strip():
            return [model_override.strip()]
        if self.model_name.lower() == "auto":
            return self.fetch_active_free_models()
        return [self.model_name]

    def _generate_with_fallback(
        self,
        prompt: str,
        task_type: str,
        temperature: float,
        model_override: str | None = None,
    ) -> AIResponse:
        """فراخوانیِ مدل با تلاشِ محدود و حسابداریِ کاملِ تلاش‌ها.

        * مدلِ پین‌شده هرگز به مدلِ دیگری سوییچ نمی‌کند؛ تلاشِ دوباره فقط روی
          همان مدل و فقط برای خطاهای گذرا (شبکه/۴۲۹/۵xx) انجام می‌شود.
        * هزینه و توکنِ تلاش‌های شکست‌خورده هم جمع می‌شوند، چون سرویس‌دهنده
          آن‌ها را مصرف کرده است. هزینهٔ آخرین تلاش جایگزینِ مجموع نمی‌شود.
        """
        pinned = bool(model_override and model_override.strip())
        initial = self._initial_candidates(model_override=model_override)
        if not initial:
            raise AIProviderError("هیچ مدلِ فعالی برای فراخوانی یافت نشد.", retryable=False)

        max_attempts = (
            PINNED_MODEL_MAX_ATTEMPTS if pinned else MAX_FALLBACK_ATTEMPTS
        )
        queue = list(initial)
        attempted: set[str] = set()
        last_error: str | None = None
        attempts = 0
        failed_cost = 0.0
        failed_tokens = 0

        while attempts < max_attempts:
            current = queue.pop(0) if queue else None
            if current is None:
                if pinned:
                    break  # مدلِ پین‌شده تمام شد — هیچ جایگزینی وجود ندارد
                free = self.fetch_active_free_models(force_refresh=True)
                current = next((m for m in free if m not in attempted), None)
                if current is None:
                    break
            attempts += 1
            attempted.add(current)
            try:
                response = self._attempt(current, prompt, task_type, temperature)
            except AIProviderError as exc:
                last_error = str(exc)
                print(
                    f"[AI] {task_type}: تلاشِ {attempts}/{max_attempts} با مدل "
                    f"{current} شکست خورد: {last_error[:160]}"
                )
                if not exc.retryable:
                    raise
                # توکن/هزینه‌ای که این تلاش سوزاند را نگه دار (اگر سرویس داد)
                failed_cost += float(getattr(exc, "cost_usd", 0.0) or 0.0)
                failed_tokens += int(getattr(exc, "token_count", 0) or 0)
                if pinned:
                    # همان مدل، تلاش دوباره؛ هیچ مدلِ دیگری امتحان نمی‌شود
                    queue = [current]
                    continue
                free = self.fetch_active_free_models(force_refresh=True)
                merged = [m for m in free if m not in attempted] + [
                    m for m in queue if m not in attempted
                ]
                queue = list(dict.fromkeys(merged))
                upcoming = queue[0] if queue else None
                print(f"[OpenRouter Dynamic Fallback] Switched from {current} to {upcoming}")
                continue

            print(
                f"[AI] {task_type}: موفق با «{response.model_name}» در تلاشِ "
                f"{attempts} — توکن {response.token_count}, هزینه ${response.cost_usd}"
            )
            response.attempts = attempts
            response.failed_cost_usd = round(failed_cost, 8)
            response.failed_tokens = failed_tokens
            return response

        raise AIProviderError(
            f"فراخوانیِ مدل پس از {attempts} تلاش شکست خورد. آخرین خطا: {last_error}",
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


_SUBJECT_LABELS = {
    "math": "ریاضی",
    # نامِ رشته‌ها (از curriculum_bridge) — بدونِ این‌ها _subject_label
    # مقدارِ خامِ انگلیسی را برمی‌گرداند و در خروجیِ AI می‌ماند.
    "mathematics": "ریاضی",
    "experimental": "علوم تجربی",
    "calculus": "حسابان",
    "geometry": "هندسه",
    "discrete": "گسسته",
    "statistics": "آمار و احتمال",
    "physics": "فیزیک",
    "chemistry": "شیمی",
    "biology": "زیست‌شناسی",
}


def _subject_label(slug: str) -> str:
    return _SUBJECT_LABELS.get(slug, slug)


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
        "statistics": [
            {"text": "از ۵ نفر به‌تصادف ۲ نفر برای گروه انتخاب می‌کنیم. چند انتخاب ممکن است؟",
             "options": ["۸", "۱۰", "۱۶", "۲۰"], "correct_answer": 2,
             "explanation": "تعداد انتخاب‌های ۲ نفر از ۵ نفر برابرِ ترکیب ۲ از ۵ است که می‌شود ۱۰."},
            {"text": "میانگینِ سه عدد ۴، ۷ و ۱۰ چیست؟",
             "options": ["۶", "۷", "۸", "۲۱"], "correct_answer": 2,
             "explanation": "میانگین برابر است با مجموعِ اعداد تقسیم بر تعدادشان: ۲۱ تقسیم بر ۳ = ۷."},
            {"text": "احتمالِ آمدنِ عدد زوج در پرتاب یک تاس سالم چیست؟",
             "options": ["یک‌ششم", "یک‌سوم", "یک‌دوم", "دوسوم"], "correct_answer": 3,
             "explanation": "سه حالت مطلوب (۲، ۴ و ۶) از شش حالت کل — احتمالِ یک‌دوم."},
            {"text": "واریانسِ مجموعه‌دادهٔ {۲، ۴، ۴، ۴، ۵، ۵، ۷، ۹} چیست؟",
             "options": ["۲", "۴", "۶", "۸"], "correct_answer": 2,
             "explanation": "میانگین این داده‌ها ۵ است و میانگینِ توانِ دومِ انحراف‌ها برابرِ ۴ می‌شود؛ پس واریانس ۴ است."},
        ],
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
            {"text": "مشتق تابع $y = x^۳ - ۳x$ کدام است؟",
             "options": ["$y' = ۳x^۲ - ۳$", "$y' = x^۲ - ۳$", "$y' = ۳x^۲ + ۳$", "$y' = ۳x - ۳$"], "correct_answer": 1,
             "explanation": "طبق قاعدهٔ مشتقِ توان: مشتق $x^۳$ برابر $۳x^۲$ و مشتق $-۳x$ برابر $-۳$ است."},
            {"text": "مقدار $\\log_{۲}(۱۶)$ برابر است با:",
             "options": ["$۳$", "$۴$", "$۵$", "$۸$"], "correct_answer": 2,
             "explanation": "چون $۱۶ = ۲^۴$ است، پس $\\log_{۲}(۱۶) = ۴$ می‌باشد."},
            {"text": "دامنهٔ تابع $f(x) = \\sqrt{x - ۱}$ کدام است؟",
             "options": ["$x \\ge ۰$", "$x \\ge ۱$", "$x > ۱$", "تمام اعداد حقیقی"], "correct_answer": 2,
             "explanation": "عبارت زیر رادیکال باید نامنفی باشد: $x - ۱ \\ge ۰ \\Rightarrow x \\ge ۱$."},
            {"text": "مقدار $\\lim_{x \\to ۰} \\frac{\\sin x}{x}$ برابر است با:",
             "options": ["$۰$", "$۱$", "$\\infty$", "تعریف‌ناپذیر"], "correct_answer": 2,
             "explanation": "طبق قضیهٔ حد مثلثاتی، $\\lim_{x \\to ۰} \\frac{\\sin x}{x} = ۱$ است."},
            {"text": "اگر $f(x) = x^۲ + ۲x - ۵$ باشد، مقدار $f'(۳)$ چقدر است؟",
             "options": ["$۶$", "$۸$", "$۹$", "$۴$"], "correct_answer": 2,
             "explanation": "داریم $f'(x) = ۲x + ۲$؛ بنابراین $f'(۳) = ۲(۳) + ۲ = ۸$."},
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
            {"text": "دترمینان ماتریس $$\\begin{bmatrix} ۱ & ۲ \\\\ ۳ & ۴ \\end{bmatrix}$$ کدام است؟",
             "options": ["$-۲$", "$۲$", "$۱۰$", "$-۱۰$"], "correct_answer": 1,
             "explanation": "دترمینان ماتریس $۲ \\times ۲$ برابر است با $(۱ \\times ۴) - (۲ \\times ۳) = ۴ - ۶ = -۲$."},
            {"text": "در مثلث قائم‌الزاویه‌ای، دو ضلع قائم $۳$ و $۴$ سانتی‌مترند. وتر چند سانتی‌متر است؟",
             "options": ["$۵$", "$۶$", "$۷$", "$\\sqrt{۷}$"], "correct_answer": 1,
             "explanation": "طبق قضیهٔ فیثاغورس: $۳^۲ + ۴^۲ = ۲۵ \\Rightarrow c = ۵$."},
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
        subjects_raw = _extract_marker(prompt, "SUBJECTS") or _extract_marker(prompt, "SUBJECT") or "physics"
        subjects = [part.strip() for part in re.split(r"[،,]", subjects_raw) if part.strip()] or ["physics"]
        topic = (_extract_marker(prompt, "TOPIC") or "").strip()
        try:
            count = max(1, min(60, int(_extract_marker(prompt, "COUNT") or "5")))
        except ValueError:
            count = 5
        custom = _extract_marker(prompt, "CUSTOM")

        configs_raw = _extract_marker(prompt, "SUBJECT_CONFIGS")
        subject_configs: list[dict] = []
        if configs_raw:
            try:
                parsed_cfg = json.loads(configs_raw)
                if isinstance(parsed_cfg, list):
                    subject_configs = [c for c in parsed_cfg if isinstance(c, dict) and c.get("subject")]
            except Exception:
                subject_configs = []

        ai_pct_raw = _extract_marker(prompt, "AI_RATIO") or _extract_marker(prompt, "AI_PERCENTAGE")
        try:
            ai_pct = max(0, min(100, int(ai_pct_raw))) if ai_pct_raw != "" else None
        except ValueError:
            ai_pct = None

        default_diff = _extract_marker(prompt, "DIFFICULTY") or "متوسط"
        bank_tags = ["کنکور ۱۴۰۲", "قلم‌چی", "گاج"]
        legacy_tags = ["کنکور ۱۴۰۲", "قلم‌چی", "تألیفی AI"]
        fa_digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

        # لیستِ (slug درس، اندیس سؤال در آن درس، سطح دشواری درس، ریز‌مبحث هدف)
        plan: list[tuple[str, int, str, str]] = []
        if subject_configs:
            for cfg in subject_configs:
                slug = str(cfg.get("subject") or "physics").strip()
                c_count = max(1, min(20, int(cfg.get("count") or 1)))
                c_diff = str(cfg.get("difficulty") or default_diff).strip() or "متوسط"
                subs = [str(x).strip() for x in (cfg.get("subTopics") or cfg.get("topics") or []) if str(x).strip()]
                for idx in range(c_count):
                    sub_label = subs[idx % len(subs)] if subs else ""
                    plan.append((slug, idx, c_diff, sub_label))
        else:
            for i in range(count):
                slug = subjects[i % len(subjects)]
                plan.append((slug, i // len(subjects), default_diff, ""))

        total = len(plan)
        ai_quota = round(total * (ai_pct / 100.0)) if ai_pct is not None else None

        items = []
        for i, (slug, local_idx, s_diff, sub_label) in enumerate(plan):
            bank = self._KONKUR_BANK.get(slug) or self._KONKUR_BANK["physics"]
            base = bank[local_idx % len(bank)]
            text = base["text"]
            if sub_label:
                text = f"[{sub_label}] {text}"
            elif topic and topic != "—":
                text = f"{text}"
            if custom:
                text = f"{text}"
            if ai_quota is not None:
                source_tag = "تألیفی AI" if i < ai_quota else bank_tags[(i - ai_quota) % len(bank_tags)]
            else:
                source_tag = legacy_tags[i % len(legacy_tags)]
            diagram_svg = None
            if slug == "physics":
                diagram_svg = (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                    '<rect x="60" y="80" width="280" height="140" fill="none" stroke="black" stroke-width="2"/>'
                    '<rect x="160" y="66" width="80" height="28" fill="white" stroke="black" stroke-width="2"/>'
                    '<circle cx="200" cy="220" r="18" fill="white" stroke="black" stroke-width="2"/>'
                    '<text x="200" y="42" font-family="Vazirmatn, Arial" font-size="13" text-anchor="middle">R = ۶ Ω</text>'
                    '<text x="200" y="268" font-family="Vazirmatn, Arial" font-size="13" text-anchor="middle">V = ۱۲ V</text>'
                    '</svg>'
                )
            elif slug == "geometry":
                diagram_svg = (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                    '<line x1="80" y1="220" x2="320" y2="220" stroke="black" stroke-width="2"/>'
                    '<line x1="80" y1="220" x2="80" y2="80" stroke="black" stroke-width="2"/>'
                    '<line x1="80" y1="80" x2="320" y2="220" stroke="black" stroke-width="2"/>'
                    '<text x="200" y="255" font-family="Vazirmatn, Arial" font-size="13" text-anchor="middle">۴</text>'
                    '<text x="48" y="155" font-family="Vazirmatn, Arial" font-size="13" text-anchor="middle">۳</text>'
                    '<text x="220" y="135" font-family="Vazirmatn, Arial" font-size="13" text-anchor="middle">۵</text>'
                    '</svg>'
                )
            items.append({
                "id": i + 1,
                "text": str(text).translate(fa_digits),
                "options": [str(o).translate(fa_digits) for o in base["options"]],
                "correct_answer": int(base["correct_answer"]),
                "source_tag": str(source_tag).translate(fa_digits),
                "explanation": str(base["explanation"]).translate(fa_digits),
                "subject": str(_subject_label(slug)).translate(fa_digits),
                "difficulty": str(s_diff).translate(fa_digits),
                "diagram_svg": diagram_svg,
            })
        return json.dumps(items, ensure_ascii=False)

    # --- قالب‌های قطعی ---
    def _mock_test_booklet(self, prompt: str) -> str:
        """زنجیرهٔ ۵ مرحله‌ایِ نمونه — همان قراردادِ مدلِ واقعی."""
        proposition = _extract_marker(prompt, "PROPOSITION") or "گزارهٔ هدفِ نمونه"
        misconception = _extract_marker(prompt, "MISCONCEPTION") or "بدفهمیِ رایجِ نمونه"
        concept = _extract_marker(prompt, "CONCEPT") or "مفهوم نمونه"
        items = [
            {
                "order": 1,
                "exam_type": "philosophy",
                "text": (
                    f"این که در آزمایشِ «{concept}» عددها را جابه‌جا کنید و نتیجه ثابت بماند، "
                    "به چه ویژگیِ ریشه‌ای در جهانِ فیزیکی برمی‌گردد؟ به زبانِ خودت بگو، "
                    "بدونِ اینکه به فرمول اشاره کنی."
                ),
                "difficulty": "hard",
                "cognitive_type": "conceptual",
                "mapped_propositions": [proposition],
                "forbidden_words": [],
                "expected_logic": (
                    "ریشه در تراکمِ مادّه و فشارِ ناشی از وزنِ ستونِ بالایی است، "
                    "نه در عدد یا نامِ فرمول."
                ),
                "diagram_svg": None,
            },
            {
                "order": 2,
                "exam_type": "mask_mcq",
                "text": (
                    f"در سه ظرف با شکل‌های مختلف (باریک، پهن و نامنظم) که سطحِ آزادِ «{concept}» "
                    "در آن‌ها هم‌ارتفاع است، فشار در کفِ ظرف چگونه است؟"
                ),
                "options": [
                    "در ظرفِ باریک بیشتر است چون ستون بلندتر است",
                    "در ظرفِ پهن بیشتر است چون مایعِ بیشتری دارد",
                    "در هر سه ظرف برابر است",
                    "به جنسِ دیوارهٔ ظرف بستگی دارد",
                ],
                "correct_option_index": 3,  # گزینهٔ سوم (یک‌پایه)
                "difficulty": "medium",
                "cognitive_type": "conceptual",
                "mapped_propositions": [proposition],
                "forbidden_words": [],
                "expected_logic": "فشار به ارتفاعِ ستون وابسته است؛ شکلِ ظرف دخالتی ندارد.",
                "diagram_svg": (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
                    '<line x1="40" y1="250" x2="380" y2="250" stroke="black" stroke-width="2"/>'
                    '<rect x="70" y="120" width="50" height="130" fill="none" stroke="black" stroke-width="2"/>'
                    '<rect x="175" y="120" width="90" height="130" fill="none" stroke="black" stroke-width="2"/>'
                    '<rect x="310" y="120" width="50" height="130" fill="none" stroke="black" stroke-width="2"/>'
                    '<line x1="60" y1="120" x2="370" y2="120" stroke="black" stroke-width="1" stroke-dasharray="5,4"/>'
                    '<text x="95" y="275" font-size="12" text-anchor="middle">A</text>'
                    '<text x="220" y="275" font-size="12" text-anchor="middle">B</text>'
                    '<text x="335" y="275" font-size="12" text-anchor="middle">C</text>'
                    "</svg>"
                ),
            },
            {
                "order": 3,
                "exam_type": "perturbation",
                "text": (
                    f"اگر همین آزمایشِ «{concept}» را به ماه ببریم، چه چیزی در نتایج تغییر می‌کند و چه "
                    "چیزی دست‌نخورده می‌ماند؟ پاسخ را بدونِ نوشتنِ هیچ رابطهٔ ریاضی توضیح بده."
                ),
                "difficulty": "hard",
                "cognitive_type": "conceptual",
                "mapped_propositions": [proposition],
                "forbidden_words": [],
                "expected_logic": (
                    "وزنِ ستون کم می‌شود ⇒ فشار در همان ارتفاع کمتر؛ اما هندسهٔ ظرف و "
                    "هم‌ارتفاعیِ سطح‌ها تغییری نمی‌کند."
                ),
                "diagram_svg": None,
            },
            {
                "order": 4,
                "exam_type": "debugging",
                "text": (
                    f"امیر می‌گوید: «{misconception}». سارا هم تأیید می‌کند. دقیقاً بگو این استدلال "
                    "از کجا شروع به غلط شدن می‌کند، و اگر بخواهی با یک مثالِ ساده آن را رد کنی چه می‌گویی؟"
                ),
                "difficulty": "hard",
                "cognitive_type": "combined",
                "mapped_propositions": [proposition],
                "forbidden_words": [],
                "expected_logic": (
                    "اشتباه در جایگزین کردنِ «کمیتِ کل» به‌جای «ارتفاعِ ستون» است؛ "
                    "مثالِ نقض: دو ظرف با سطحِ مقطعِ متفاوت و ارتفاعِ برابر."
                ),
                "diagram_svg": None,
            },
            {
                "order": 5,
                "exam_type": "feynman_synthesis",
                "text": (
                    f"«{concept}» را برای یک بچهٔ ۱۰ ساله توضیح بده؛ طوری که خودش بتواند با دو لیوان "
                    "آب آزمایشش را تکرار کند. باید بفهمد چرا و کِی این اتفاق می‌افتد."
                ),
                "difficulty": "hard",
                "cognitive_type": "conceptual",
                "mapped_propositions": [proposition],
                "forbidden_words": ["فشار", "چگالی", "فرمول", "قانون", "ارتفاع"],
                "expected_logic": "وزنِ آبِ روی سر و سنگینیِ آن روی بدن، با مثالِ شنا و دو لیوان.",
                "diagram_svg": None,
            },
        ]
        return json.dumps({"questions": items}, ensure_ascii=False)

    def _mock_exam_analysis(self, prompt: str) -> str:
        """تحلیلِ نمونه با همان قراردادِ Cross-Check (برای AI_PROVIDER=mock)."""
        m_answers = re.search(r"<<<ANSWERS>>>(.*?)<<<END>>>", prompt, re.DOTALL)
        answers_raw = m_answers.group(1) if m_answers else ""
        sections = re.split(r"<<<STAGE (\d+)>>>", answers_raw)
        pairs = list(zip(sections[1::2], sections[2::2])) if len(sections) >= 3 else []
        # فقط خطِ «پاسخِ دانش‌آموز» را می‌خوانیم. کلِ بلوک شاملِ فهرستِ کلماتِ
        # ممنوعه و منطقِ موردانتظار است؛ خواندنِ کلِ بلوک باعث می‌شد mock هر
        # پاسخِ سالمی را هم «نقضِ کلماتِ ممنوعه» ببیند.
        def _student_answer(body: str) -> str:
            for line in body.splitlines():
                if line.startswith("پاسخِ دانش‌آموز:"):
                    return line.split(":", 1)[1].strip()
            return ""

        body_by_order = {int(o): _student_answer(b) for o, b in pairs}

        def _words(order: int) -> int:
            return len(body_by_order.get(order, "").split())

        forbidden_hit = any(w in body_by_order.get(5, "") for w in ("فرمول", "چگالی", "ارتفاع", "قانون"))
        gave_debug = _words(4) >= 12

        status = "JARGON_DEPENDENT" if forbidden_hit else ("MASTERED" if gave_debug else "PARTIAL_FRAGMENTED")
        # فاز ۳۰: عنوان‌های دوم‌شخص و هم‌راستا با _STATUS_PERSONA در cross_check.
        persona = {
            "JARGON_DEPENDENT": "زبانِ کتاب را داری، تصویرِ ذهنی‌اش را نه",
            "MASTERED": "مفهوم را داری — پیوندها را می‌بینی",
            "PARTIAL_FRAGMENTED": "قطعه‌قطعه فهمیدی — زنجیره هنوز بسته نشده",
        }[status]

        per_question = []
        for order in range(1, 6):
            words = _words(order)
            verdict = (
                "پاسخی ثبت نشد؛ برای داوریِ این بخش شاهدی در دست نیست." if words == 0
                else "توضیح کوتاه است ولی جهتِ کلیِ استدلال قابلِ داوری است." if words < 12
                else "استدلال پیوسته و در جهتِ منطقِ موردانتظار است."
            )
            per_question.append({
                "order": order,
                "cognitive_verdict": verdict,
                "missing_gear": None if words >= 12 else "پیوندِ علّی بین ادعا و دلیل",
                "status": "CONFIRMED" if words >= 12 else "UNCLEAR",
                "error_type": "none",
                "evidence_type": "strong_confirming" if words >= 12 else "weak_confirming",
                "reasoning": verdict,
                "confidence": 0.7 if words >= 12 else 0.3,
                "needs_teacher_review": words < 12,
                "qualitative_feedback": verdict,
            })

        findings = []
        if forbidden_hit:
            findings.append({
                "title": "شکستنِ قانونِ کلماتِ ممنوعه",
                "type": "JARGON_VIOLATION",
                "description": "در توضیحِ ساده به اصطلاحِ تخصصی تکیه کردی، نه به شهودِ خودت.",
            })
        if gave_debug:
            findings.append({
                "title": "عیب‌یابیِ منسجم",
                "type": "SYNERGY",
                "description": "نقدِ استدلالِ غلط را با پیوندِ علّی نوشتی.",
            })

        return json.dumps(
            {
                "needs_clarification": False,
                "clarification_data": None,
                "mastery_status": status,
                "persona_title": persona,
                "executive_summary": (
                    "استدلالت بین ایده و نتیجه پیوسته است — یعنی مسیرِ رسیدن به جواب را "
                    "می‌دانی. آنچه لنگ می‌زند، بیرون آمدن از پشتِ اصطلاح و گفتنِ همین "
                    "مفهوم با زبانِ خودت است: وقتی ناچار می‌شوی بدونِ واژه‌های کتاب "
                    "توضیح بدهی، معلوم می‌شود تصویرِ ذهنی هنوز کامل نشده."
                ),
                "cross_check_findings": findings,
                "per_question": per_question,
                "dimension_findings": [
                    {"dimension": "درک مفهومی و علّی", "status": per_question[0]["status"],
                     "finding": per_question[0]["cognitive_verdict"]},
                    {"dimension": "مقاومت در برابرِ اصطلاح", "status": "NEEDS_REVIEW" if forbidden_hit else "CONFIRMED",
                     "finding": "در توضیحِ ساده، به‌جای زبانِ خودت به اصطلاحِ تخصصی تکیه کردی."},
                ],
                "root_cause_hypotheses": [],
                "improvement_suggestions": [
                    "همان پدیده را برای یک بچهٔ ۱۰ ساله، بدونِ هیچ اصطلاحِ تخصصی، بازگو کن.",
                    "یک مثالِ نقض برای بدفهمیِ رایج بساز و خودت آن را رد کن.",
                ],
            },
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
    "cognitive_generate": "gemini_free",
    "cognitive_evaluate": "gemini_free",
    "cognitive_clarify": "gemini_free",
    "generate_question": "gemini_free",
    "generate_test_booklet": "gemini_free",
    "analyze_response": "gemini_free",
    "analyze_exam": "gemini_free",
    "tutor_explain": "gemini_free",
    "build_graph": "gemini_free",
}

#: وظایفی که زنجیرهٔ فهم‌سنجی را می‌سازند. این‌ها همیشه روی
#: OPENROUTER_ASSESSMENT_MODEL اجرا می‌شوند (بدونِ سوییچِ خاموش).
ASSESSMENT_TASKS = frozenset(
    {
        "generate_test_booklet",
        "analyze_exam",
        "analyze_response",
        # تدریسِ درلحظه از همان مدلِ داوری می‌آید تا لحن و کیفیت یکدست بماند.
        "tutor_explain",
    }
)


def assessment_model_name() -> str:
    """مدلِ ارزیابی — یک منبعِ حقیقت، نه دو تنظیمِ موازی."""
    pinned = (getattr(settings, "OPENROUTER_ASSESSMENT_MODEL", "") or "").strip()
    return pinned or (getattr(settings, "OPENROUTER_MODEL", "") or "").strip()


_OPENROUTER_ROUTE = {
    "cognitive_generate": "openrouter",
    "cognitive_evaluate": "openrouter",
    "cognitive_clarify": "openrouter",
    "generate_question": "openrouter",
    "generate_test_booklet": "openrouter",
    "analyze_response": "openrouter",
    "analyze_exam": "openrouter",
    "tutor_explain": "openrouter",
    "build_graph": "openrouter",
}


# ---------------------------------------------------------------------------
# دفترِ مصرف — جمعِ هزینه و توکن در محدودهٔ یک جلسهٔ ارزیابی
# ---------------------------------------------------------------------------
# چرا لازم است: AIUsageLog ردیفِ هر فراخوانی را نگه می‌دارد ولی شناسهٔ جلسه
# ندارد؛ و گزارش باید «مجموعِ هزینهٔ این آزمون» را نشان دهد. این دفتر یک
# بافرِ سبک و thread-safe است که مسیرِ ارزیابی آن را پر و در پایان می‌بلعد.
_USAGE_LEDGER: list[dict[str, Any]] = []
_LEDGER_LOCK = threading.Lock()


def reset_usage_ledger() -> None:
    with _LEDGER_LOCK:
        _USAGE_LEDGER.clear()


def record_usage(entry: dict[str, Any]) -> None:
    with _LEDGER_LOCK:
        _USAGE_LEDGER.append(dict(entry))


def usage_summary() -> dict[str, Any]:
    """جمعِ هزینه/توکن و فهرستِ فراخوانی‌ها — برای متادیتای گزارش."""
    with _LEDGER_LOCK:
        entries = [dict(e) for e in _USAGE_LEDGER]
    total_cost = round(sum(float(e.get("cost_usd") or 0.0) for e in entries), 8)
    total_tokens = sum(int(e.get("total_tokens") or 0) for e in entries)
    prompt_tokens = sum(int(e.get("prompt_tokens") or 0) for e in entries)
    completion_tokens = sum(int(e.get("completion_tokens") or 0) for e in entries)
    models = sorted({str(e.get("model") or "") for e in entries if e.get("model")})
    return {
        "calls": entries,
        "call_count": len(entries),
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "models": models,
    }


def _log_usage(
    provider: str,
    response: AIResponse | None,
    task_type: str,
    success: bool,
    error: str | None = None,
    model_name: str = "",
) -> None:
    """ثبتِ هر فراخوانی — موفق یا ناموفق — با مدل، توکن، هزینه و زمان.

    هزینه **جمع** می‌شود (``total_cost_usd``)، نه اینکه با تلاشِ آخر
    جایگزین شود؛ توکنِ ورودی/خروجی هم جدا نگه داشته می‌شود.

    خودِ خطای لاگ هرگز سیستم را نمی‌خواباند — ولی چاپِ کنسول همیشه انجام
    می‌شود تا در لاگِ سرور ردِ فراخوانی بماند.
    """
    resolved_model = (response.model_name if response else "") or model_name
    prompt_tokens = getattr(response, "prompt_tokens", 0) or 0
    completion_tokens = getattr(response, "completion_tokens", 0) or 0
    total_tokens = response.total_tokens if response else 0
    cost = response.total_cost_usd if response else 0.0
    stamp = datetime.utcnow().isoformat(timespec="seconds")

    record_usage(
        {
            "timestamp": stamp,
            "task_type": task_type,
            "model": resolved_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "success": success,
            "attempts": getattr(response, "attempts", 1) if response else 0,
        }
    )

    print(
        f"[AI-LOG] {stamp} task={task_type} model={resolved_model or '—'} "
        f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
        f"total_tokens={total_tokens} cost_usd={cost} success={success}"
        + (f" error={error}" if error else "")
    )

    try:
        from models.database import SessionLocal
        from models.ai_log import AIUsageLog

        db = SessionLocal()
        try:
            db.add(
                AIUsageLog(
                    provider=provider,
                    model_name=resolved_model,
                    task_type=task_type,
                    token_count=total_tokens,
                    cost_usd=cost,
                    success=success,
                    error=error,
                    timestamp=datetime.utcnow(),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[AI-LOG] (db write failed: {exc})")


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

    async def generate(
        self,
        prompt: str,
        task_type: str,
        temperature: float = 0.7,
        model_override: str | None = None,
    ) -> AIResponse:
        if self.total_cost_usd() >= settings.BUDGET_LIMIT_USD:
            _log_usage(self.provider_name, None, task_type, success=False, error="budget_exceeded")
            raise BudgetExceededError(
                f"سقف بودجهٔ هوش مصنوعی ({settings.BUDGET_LIMIT_USD} دلار) تمام شده است."
            )
        provider = self.get_provider(task_type)
        # زنجیرهٔ فهم‌سنجی همیشه روی مدلِ پین‌شده می‌رود؛ مگر کسی صریحاً
        # override داده باشد (تست/ابزار).
        if model_override is None and task_type in ASSESSMENT_TASKS:
            model_override = assessment_model_name() or None
        try:
            try:
                response = await provider.generate(
                    prompt, task_type, temperature, model_override=model_override
                )
            except TypeError:
                response = await provider.generate(prompt, task_type, temperature)
            # در لاگ باید معلوم باشد هر فراخوانی کدام مدل را به کار برده است.
            print(
                f"[AI] task={task_type} model={response.model_name} "
                f"attempts={response.attempts} tokens={response.total_tokens} "
                f"cost=${response.total_cost_usd}"
            )
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