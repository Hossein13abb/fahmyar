"""کراولر و رتبه‌بندِ مدل‌های رایگانِ OpenRouter.

**چرا این ماژول جدا شد؟** منطقِ انتخابِ مدل قبلاً داخل `model_abstraction`
بود و معیارش یک فهرستِ دستی از نام‌ها (`llama-3.3-70b`، `qwen-2.5-72b`).
آن مدل‌ها دیگر در فهرست رایگان نیستند، پس رتبه‌بندی عملاً تصادفی شده بود و
هر مدل در یک گروه مساوی می‌افتاد. این‌جا معیارها از *دادهٔ زندهٔ* خودِ
OpenRouter می‌آیند، نه از حدس.

معیارهای رتبه‌بندی (به ترتیبِ اهمیت برای این پروژه):

1. **JSON قابلِ اتکا** — موتور فهم‌سنجی خروجی را با `json.loads` می‌خواند.
   مدلی که `response_format` را پشتیبانی نکند، ناگهان متنِ آزاد برمی‌گرداند
   و کل ارزیابی می‌شکند. این سخت‌ترین شرط است.
2. **توانِ استدلال** — امتیازِ `artificial_analysis.intelligence_index` اگر
   موجود باشد؛ وگرنه مدل‌های `reasoning` ترجیح دارند.
3. **پنجرهٔ زمینه** — پرامپتِ ارزیاب شاملِ پنج سؤال + پنج پاسخ + نقشهٔ مفهومی
   است و می‌تواند چند ده هزار توکن شود.
4. **نبودِ فیلتر محتوا** — `is_moderated` یعنی پاسخ ممکن است به‌خاطرِ محتوای
   آموزشی رد شود. برای این پروژه نامطلوب است.
5. **تازگی** — مدلِ قدیمی‌ترِ هم‌امتیاز، احتمالاً بازنشسته می‌شود.

خروجیِ نهایی: فهرستِ مرتب‌شده‌ای از شناسه‌ها که `OpenRouterProvider` به‌عنوانِ
زنجیرهٔ fallback استفاده می‌کند.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 15 * 60

#: حدِ کافی برای پرامپتِ ارزیابی + پاسخِ مدل.
MIN_CONTEXT_TOKENS = 32_000


@dataclass
class ModelScore:
    """یک مدلِ رایگان با معیارهایش — قابلِ نمایش در /api/ai/models."""

    id: str
    name: str = ""
    context_length: int = 0
    supports_json: bool = False
    supports_reasoning: bool = False
    intelligence_index: Optional[float] = None
    is_moderated: bool = False
    created: int = 0
    score: float = 0.0
    rank: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "context_length": self.context_length,
            "supports_json": self.supports_json,
            "supports_reasoning": self.supports_reasoning,
            "intelligence_index": self.intelligence_index,
            "is_moderated": self.is_moderated,
            "score": round(self.score, 2),
            "rank": self.rank,
            "reasons": list(self.reasons),
        }


def is_free(entry: dict[str, Any]) -> bool:
    """آیا مدل رایگان است؟ ``:free`` در شناسه، یا قیمتِ صفرِ prompt و completion."""
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


def is_text_model(entry: dict[str, Any]) -> bool:
    """آیا مدل خروجیِ متنی می‌دهد؟

    فهرستِ رایگان شاملِ مدل‌های صوتی و موسیقی هم هست
    (مثلاً ``google/lyria-3-pro-preview`` که آهنگ می‌سازد). آن‌ها از نظرِ
    امتیازِ JSON و زمینهٔ بزرگ بالا می‌آیند اما برای تولیدِ آزمون بی‌فایده‌اند،
    پس باید پیش از رتبه‌بندی کنار گذاشته شوند.
    """
    architecture = entry.get("architecture") or {}

    # شرط این است که خروجی **فقط** متن باشد. مدلِ موسیقی هم «متن» تولید
    # می‌کند (متنِ آهنگ)، پس «text in outputs» کافی نیست؛ باید audio و image
    # در خروجی نباشند.
    outputs = architecture.get("output_modalities")
    if isinstance(outputs, list) and outputs:
        kinds = [str(x).strip().lower() for x in outputs]
        return "text" in kinds and not ({"audio", "image", "video"} & set(kinds))

    modality = str(architecture.get("modality") or "").lower()
    if "->" in modality:
        produced = modality.split("->", 1)[1]
        return "text" in produced and not any(
            token in produced for token in ("audio", "image", "video")
        )
    return True  # بدونِ اطلاعات، فرض کن متنی است (رفتارِ محافظه‌کارانه)


def score_model(entry: dict[str, Any]) -> ModelScore:
    """امتیازِ یک مدل را از دادهٔ خامِ OpenRouter حساب می‌کند.

    امتیازها عمداً جمعِ وزنیِ ساده‌اند، نه یک معادلهٔ پیچیده: هدف این است که
    ترتیب قابلِ توضیح و قابلِ بازبینی باشد. هر امتیاز در `reasons` هم نوشته
    می‌شود تا در UI معلوم باشد *چرا* یک مدل اول شد.
    """
    model_id = (entry.get("id") or "").strip()
    params = entry.get("supported_parameters") or []
    benchmarks = entry.get("benchmarks") or {}
    analysis = benchmarks.get("artificial_analysis") or {}
    raw_index = analysis.get("intelligence_index")

    try:
        intelligence = float(raw_index) if raw_index is not None else None
    except (TypeError, ValueError):
        intelligence = None

    score = ModelScore(
        id=model_id,
        name=(entry.get("name") or model_id).strip(),
        context_length=int(entry.get("context_length") or 0),
        supports_json="response_format" in params or "structured_outputs" in params,
        supports_reasoning="reasoning" in params,
        intelligence_index=intelligence,
        is_moderated=bool((entry.get("top_provider") or {}).get("is_moderated")),
        created=int(entry.get("created") or 0),
    )

    total = 0.0
    reasons: list[str] = []

    # ۱) JSON — شرطِ سخت. بدونِ آن، قراردادِ خروجی قابلِ اتکا نیست.
    #
    # چرا این وزن این‌قدر سنگین است؟ شاخصِ هوش حداکثر ۶۰ × ۰.۹ = ۵۴ امتیاز
    # می‌دهد، پس اختلافِ ۱۰۰ امتیازیِ دروازهٔ JSON هرگز با هوش جبران
    # نمی‌شود. برای موتور فهم‌سنجی این ترتیب درست است: مدلِ باهوشی که JSON
    # برنمی‌گرداند، کلِ ارزیابی را می‌شکند؛ مدلِ متوسطی که قرارداد را
    # رعایت می‌کند، کار را انجام می‌دهد.
    if score.supports_json:
        total += 100
        reasons.append("JSON mode دارد")
    else:
        total -= 60
        reasons.append("JSON mode ندارد (خطرِ شکستنِ قرارداد)")

    # ۲) استدلال — مهم‌ترین کیفیتِ محتوایی برای این پروژه.
    if intelligence is not None:
        # شاخصِ AA معمولاً ۰ تا ۱۰۰ است؛ ۳۰ = خوب، ۵۰+ = عالی
        total += min(intelligence, 60.0) * 0.9
        reasons.append(f"شاخصِ هوش {intelligence:.1f}")
    if score.supports_reasoning:
        total += 12
        reasons.append("حالتِ استدلال دارد")

    # ۳) پنجرهٔ زمینه
    if score.context_length >= 200_000:
        total += 10
        reasons.append("پنجرهٔ زمینهٔ بزرگ")
    elif score.context_length >= MIN_CONTEXT_TOKENS:
        total += 4

    # ۴) فیلتر محتوا — برای محتوایِ آموزشی دردسر می‌سازد.
    if score.is_moderated:
        total -= 8
        reasons.append("فیلترِ محتوا فعال است")
    else:
        total += 3

    # ۵) تازگی (تا ۳ سال)، تا مدلِ بازنشسته‌شده بالا نیاید.
    if score.created:
        age_years = max(0.0, (time.time() - score.created) / (365.25 * 24 * 3600))
        total += max(0.0, 6.0 - age_years * 2.0)

    # روترهای OpenRouter («openrouter/free») یک مدل نیستند؛ هر بار مدلِ
    # تصادفی انتخاب می‌کنند. برای آزمونِ قابلِ بازتولید مناسب نیستند.
    if "/free" == model_id[len(model_id.split("/")[0]) :] or model_id.startswith("openrouter/"):
        total -= 15
        reasons.append("روتر است، مدلِ مشخص نیست")

    score.score = total
    score.reasons = reasons
    return score


def rank_models(entries: list[dict[str, Any]], *, require_json: bool = True) -> list[ModelScore]:
    """مدل‌های رایگان را امتیاز می‌دهد و از بهترین به بدترین مرتب می‌کند.

    `require_json=True` مدل‌های بدونِ JSON را در انتها می‌گذارد (حذف نمی‌کند)،
    چون اگر همهٔ مدل‌های خوب از دسترس خارج شوند، داشتنِ یک گزینهٔ ضعیف
    بهتر از نداشتنِ هیچ است.
    """
    scored: list[ModelScore] = []
    for entry in entries:
        if not isinstance(entry, dict) or not is_free(entry):
            continue
        if not is_text_model(entry):
            continue
        model = score_model(entry)
        if not model.id:
            continue
        scored.append(model)

    scored.sort(
        key=lambda m: (
            0 if (m.supports_json or not require_json) else 1,
            -m.score,
            m.id,
        )
    )
    for index, model in enumerate(scored, start=1):
        model.rank = index
    return scored


# ---------------------------------------------------------------------------
# کراول با کش
# ---------------------------------------------------------------------------
_cache: dict[str, Any] = {"ts": 0.0, "models": []}
_lock = threading.Lock()


def fetch_free_models(
    *,
    api_key: str = "",
    force_refresh: bool = False,
    timeout: float = 30.0,
) -> list[ModelScore]:
    """فهرستِ زندهٔ مدل‌های رایگان، مرتب‌شده. نتیجه کش می‌شود.

    `/api/models` کلید لازم ندارد، ولی اگر کلید بدهیم OpenRouter ممکن است
    فهرستِ متناسب با حساب را برگرداند. در خطا، کشِ قبلی (حتی قدیمی) برگردانده
    می‌شود تا یک قطعیِ شبکه، سرویس را از کار نیندازد.
    """
    now = time.monotonic()
    with _lock:
        cached: list[ModelScore] = _cache["models"]
        if not force_refresh and cached and (now - _cache["ts"]) < CACHE_TTL_SECONDS:
            return list(cached)

    import requests

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = requests.get(MODELS_URL, headers=headers, timeout=timeout)
        response.raise_for_status()
        entries = response.json().get("data", [])
    except Exception as exc:  # noqa: BLE001
        with _lock:
            if _cache["models"]:
                print(f"[models] کراول ناموفق ({exc})؛ از کشِ قبلی استفاده شد.")
                return list(_cache["models"])
        raise

    ranked = rank_models(entries)
    with _lock:
        _cache.update(ts=time.monotonic(), models=ranked)
    return list(ranked)


def free_model_ids(**kwargs: Any) -> list[str]:
    """فقط شناسه‌ها — همان چیزی که زنجیرهٔ fallback نیاز دارد."""
    return [m.id for m in fetch_free_models(**kwargs)]


def clear_cache() -> None:
    with _lock:
        _cache.update(ts=0.0, models=[])
