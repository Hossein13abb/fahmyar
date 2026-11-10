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
# OpenRouter — کشف پویای مدل‌های رایگان (کش ۱۵ دقیقه‌ای) + اولویت‌بندی + فال‌بک خودکار
# ---------------------------------------------------------------------------

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
    name = "openrouter"

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        # پاکسازی کلید: فاصلهٔ انتهایی/خط جدید (.strip()) علت رایج خطای 401 است
        raw_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.api_key = (raw_key or "").strip()
        self.model_name = (model_name if model_name is not None else settings.OPENROUTER_MODEL).strip() or "auto"
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.timeout = settings.OPENROUTER_TIMEOUT_SECONDS
        if not self.api_key:
            raise AIProviderError(
                "OPENROUTER_API_KEY تنظیم نشده است. کلید را در .env قرار دهید "
                "یا AI_PROVIDER=mock را انتخاب کنید."
            )

    # ------------------------------------------------------------------
    # هدرهای سفارشی — روی همهٔ درخواست‌ها (کش، فهرست مدل‌ها، فال‌بک) اعمال می‌شود
    # ------------------------------------------------------------------
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

        payload = {
            "model": model,
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
        if not text:
            raise AIProviderError(f"پاسخ خالی از OpenRouter (مدل {model}).", retryable=True)

        usage = data.get("usage") or {}
        token_count = int(usage.get("total_tokens") or 0) or max(1, (len(prompt) + len(text)) // 4)
        try:
            cost_usd = float(usage.get("cost") or 0.0)
        except (TypeError, ValueError):
            cost_usd = 0.0

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
                merged = [m for m in free if m not in attempted] + [m for m in queue if m not in attempted]
                queue = list(dict.fromkeys(merged))
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
        # شبیه‌سازی تأخیر واقعی شبکه نیست؛ تست‌ها سریع می‌مانند
        if task_type == "generate_question":
            text = self._mock_question(prompt)
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

    # --- قالب‌های قطعی ---
    def _mock_test_booklet(self, prompt: str) -> str:
        proposition = _extract_marker(prompt, "PROPOSITION") or "گزارهٔ هدفِ نمونه"
        misconception = _extract_marker(prompt, "MISCONCEPTION") or "بدفهمیِ رایجِ نمونه"
        concept = _extract_marker(prompt, "CONCEPT") or "مفهوم نمونه"
        svg1 = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 160" role="img">'
                '<rect x="10" y="120" width="40" height="30" fill="#0f766e"/>'
                '<rect x="80" y="80" width="40" height="70" fill="#115e59"/>'
                '<rect x="150" y="40" width="40" height="110" fill="#134e4a"/>'
                '<line x1="5" y1="150" x2="310" y2="150" stroke="#334155"/>'
                '<text x="200" y="30" font-size="14" fill="#0f172a">V∝I</text></svg>')
        svg2 = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 120" role="img">'
                '<circle cx="60" cy="60" r="16" fill="none" stroke="#0f766e" stroke-width="3"/>'
                '<line x1="76" y1="60" x2="140" y2="60" stroke="#334155" stroke-width="3"/>'
                '<rect x="140" y="45" width="60" height="30" fill="none" stroke="#b45309" stroke-width="3"/>'
                '<line x1="200" y1="60" x2="280" y2="60" stroke="#334155" stroke-width="3"/>'
                '<text x="150" y="35" font-size="12" fill="#0f172a">R</text></svg>')
        qs = [
            ("conceptual", f"«{concept}» را با کلمات خودتان توضیح دهید؛ چرا این پدیده رخ می‌دهد و چه رابطه‌ای بین علت و معلول وجود دارد؟", "medium"),
            ("real_world", f"یک گارگاه واقعی را در نظر بگیرید که در آن مسئله‌ای دربارهٔ «{concept}» پیش آمده است. چه اتفاقی می‌افتد و علت علمی آن چیست؟", "medium"),
            ("diagram", f"به نمودار داده‌شده نگاه کنید. با توجه به محورها، روند تغییرات کدام گزاره را تأیید می‌کند؟ استدلال خود را بنویسید.", "medium"),
            ("misconception_trap", f"«{misconception}» — دوستتان چنین استدلالی کرده است. آیا درست است؟ با دلیل علمی بررسی کنید.", "hard"),
            ("computational", f"با داده‌های فرضی (V=۱۲ ولت، R=۴ اهم)، کمیت خواسته‌شده را محاسبه کنید و هر مرحله را بنویسید.", "easy"),
            ("definitional", f"تعریف دقیق «{concept}» را بنویسید و بگویید چه چیزی آن را از مفاهیم مشابه متمایز می‌کند.", "easy"),
            ("conceptual", f"اگر یکی از کمیت‌های «{concept}» دو برابر شود، چه اتفاقی می‌افتد و چرا؟", "medium"),
            ("real_world", "یک مثال از زندگی روزمره بیاورید که در آن این قانون/مفهوم نقش دارد و توضیح دهید چگونه عمل می‌کند.", "hard"),
            ("diagram", "با توجه به مدار/نمودار روبه‌رو، اگر مقدار R دو برابر شود چه اتفاقی برای جریان می‌افتد؟ استدلال خود را بنویسید.", "hard"),
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
