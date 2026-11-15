"""آزمونِ واقعیِ مدل‌ها با پرامپتِ فارسی — معیاری که از فراداده بهتر است.

**چرا لازم شد؟** رتبه‌بندی بر پایهٔ فراداده («JSON mode دارد»، «شاخصِ هوش ۳۰»)
مدلی را اول نشاند که در عمل بدترین بود: `nvidia/nemotron-3.5-super-vl`
نامزدِ رتبهٔ ۱ بود، ولی در آزمونِ فارسی «مشduc» تولید کرد (ترکیبِ فارسی و
لاتین) و ۹ ثانیه طول کشید. در همان آزمون، `baidu/ernie-5.5-flash` با
۱.۶ ثانیه فارسیِ بی‌نقص داد.

فراداده می‌گوید مدل *چه قابلیتی اعلام می‌کند*؛ probe می‌گوید *چه کاری
واقعاً انجام می‌دهد*. این دو یکی نیستند.

نتیجهٔ probe در یک فایلِ کش کنارِ پروژه ذخیره می‌شود تا انتخابِ مدل بینِ
اجراها پایدار بماند.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: پرامپتِ آزمون عمداً کوتاه اما نماینده است: فارسی + JSON + نمادِ ریاضی.
#: اگر مدل این را درست انجام دهد، پرامپتِ بزرگ‌ترِ ارزیابی را هم می‌تواند.
PROBE_PROMPT = """فقط یک شیءِ JSON برگردان و هیچ متنِ دیگری ننویس.
یک سؤالِ کوتاهِ ریاضیِ فارسی دربارهٔ مشتق بساز، دقیقاً با این ساختار:
{"question": "متنِ سؤال با نمادهای ریاضی در $...$", "answer": 0}
قواعد: متن کاملاً فارسی باشد؛ هیچ واژهٔ انگلیسی یا آوانویسیِ لاتین در آن نباشد."""

CACHE_PATH = Path(__file__).resolve().parent.parent / ".model_probe_cache.json"
CACHE_TTL_SECONDS = 6 * 3600  # ۶ ساعت

#: نشانه‌های خروجیِ معیوب — همان چیزی که در آزمونِ واقعی دیدیم.
_MIXED_SCRIPT_RE = re.compile(r"[\u0600-\u06FF][A-Za-z]|[A-Za-z][\u0600-\u06FF]")


@dataclass
class ProbeResult:
    model: str
    ok: bool = False
    elapsed_seconds: float = 0.0
    json_ok: bool = False
    persian_ok: bool = False
    mixed_script: bool = False
    quality: float = 0.0
    error: str = ""
    preview: str = ""
    probed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "ok": self.ok,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "json_ok": self.json_ok,
            "persian_ok": self.persian_ok,
            "mixed_script": self.mixed_script,
            "quality": round(self.quality, 1),
            "error": self.error,
            "preview": self.preview,
            "probed_at": self.probed_at,
        }


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    from ai.json_sanitize import extract_json_object, sanitize_json_string

    for parser in (sanitize_json_string, extract_json_object):
        try:
            value = parser(text)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, dict):
            return value
    return None


def score_response(text: str, elapsed: float) -> ProbeResult:
    """کیفیتِ یک پاسخ را می‌سنجد: JSON، فارسیِ سالم، سرعت."""
    result = ProbeResult(model="", elapsed_seconds=elapsed, preview=(text or "")[:200])
    payload = _parse_json(text or "")

    if payload is None:
        result.error = "خروجی JSON معتبر نبود"
        return result
    result.json_ok = True

    question = str(payload.get("question") or "")
    if not question.strip():
        result.error = "کلیدِ question خالی بود"
        return result

    result.persian_ok = bool(re.search(r"[\u0600-\u06FF]", question))
    result.mixed_script = bool(_MIXED_SCRIPT_RE.search(question))

    # امتیاز: JSON (۴۰) + فارسی (۳۰) + سرعت (تا ۳۰) − جریمهٔ خطِ مختلط
    quality = 40.0
    if result.persian_ok:
        quality += 30.0
    if result.mixed_script:
        quality -= 35.0  # این تک‌تکش در عمل متن را برای دانش‌آموز بی‌معنا می‌کند
    # سرعت: ۲ ثانیه یا کمتر = ۳۰ امتیاز، ۳۰ ثانیه = ۰
    quality += max(0.0, 30.0 * (1.0 - min(elapsed, 30.0) / 30.0))

    result.quality = quality
    result.ok = result.json_ok and result.persian_ok and not result.mixed_script
    return result


def load_cache() -> dict[str, Any]:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_cache(cache: dict[str, Any]) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass  # کش نباید هرگز اجرای اصلی را بشکند


def cached_result(model: str, cache: Optional[dict[str, Any]] = None) -> Optional[ProbeResult]:
    data = cache if cache is not None else load_cache()
    entry = data.get(model)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get("probed_at") or 0) > CACHE_TTL_SECONDS:
        return None
    return ProbeResult(
        model=model,
        ok=bool(entry.get("ok")),
        elapsed_seconds=float(entry.get("elapsed_seconds") or 0),
        json_ok=bool(entry.get("json_ok")),
        persian_ok=bool(entry.get("persian_ok")),
        mixed_script=bool(entry.get("mixed_script")),
        quality=float(entry.get("quality") or 0),
        error=str(entry.get("error") or ""),
        preview=str(entry.get("preview") or ""),
        probed_at=float(entry.get("probed_at") or 0),
    )


async def probe_model(model: str, *, router: Any = None) -> ProbeResult:
    """یک مدل را واقعاً صدا می‌زند و کیفیتش را می‌سنجد."""
    if router is None:
        from ai.model_abstraction import get_router

        router = get_router()

    started = time.time()
    try:
        response = await router.generate(
            PROBE_PROMPT, "probe", temperature=0.2, model_override=model
        )
    except Exception as exc:  # noqa: BLE001
        result = ProbeResult(model=model, elapsed_seconds=time.time() - started, error=str(exc)[:200])
        return result

    result = score_response(response.text or "", time.time() - started)
    result.model = model
    return result


async def probe_and_cache(models: list[str], *, router: Any = None, concurrency: int = 3) -> list[ProbeResult]:
    """چند مدل را با محدودیتِ هم‌زمانی صدا می‌زند و نتیجه را کش می‌کند."""
    import asyncio

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(model: str) -> ProbeResult:
        async with semaphore:
            return await probe_model(model, router=router)

    results = await asyncio.gather(*(one(m) for m in models), return_exceptions=False)
    cache = load_cache()
    stamp = time.time()
    for result in results:
        if result.error and not result.json_ok:
            continue  # شکستِ موقت را کش نکن تا دفعهٔ بعد دوباره تلاش شود
        payload = result.to_dict()
        payload["probed_at"] = stamp
        cache[result.model] = payload
    save_cache(cache)
    return list(results)


def best_models(results: list[ProbeResult], *, require_ok: bool = True) -> list[str]:
    """مدل‌ها را بر اساسِ کیفیتِ واقعی مرتب می‌کند (نه فراداده)."""
    pool = [r for r in results if r.ok] if require_ok else list(results)
    return [r.model for r in sorted(pool, key=lambda r: (-r.quality, r.elapsed_seconds))]
