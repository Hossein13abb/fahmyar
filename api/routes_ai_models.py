"""مسیرهای کاتالوگ مدل‌های هوش مصنوعی.

    GET  /api/ai/models          → رتبه‌بندیِ زندهٔ مدل‌های رایگان
    POST /api/ai/models/refresh  → کراولِ اجباری (نادیده‌گرفتنِ کش)
    POST /api/ai/models/probe    → آزمونِ واقعیِ یک مدل روی پرامپتِ کوچک

هدف: انتخابِ مدل نباید یک جعبهٔ سیاه باشد. مدیر مدرسه باید بتواند ببیند
*کدام* مدل انتخاب شده، *چرا*، و آیا واقعاً جواب می‌دهد.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ai.model_abstraction import get_router
from ai.model_catalog import (
    CACHE_TTL_SECONDS,
    MIN_CONTEXT_TOKENS,
    clear_cache,
    fetch_free_models,
    score_model,
)
from ai.model_probe import (
    best_models,
    cached_result,
    load_cache,
    probe_and_cache,
    probe_model,
)
from api.routes_auth import get_current_user, require_roles
from config import settings
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai-models"])


class ProbeRequest(BaseModel):
    model: str = Field(min_length=3, max_length=120)
    prompt: str = Field(
        default="فقط این JSON را برگردان: {\"ok\": true}",
        max_length=2000,
        description="پرامپتِ کوتاه برای آزمونِ مدل",
    )
    expect_json: bool = Field(default=True, description="آیا خروجی باید JSON باشد؟")


def _require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("teacher", "admin", "school_staff"):
        raise HTTPException(
            status_code=403,
            detail={"message": "این بخش مخصوصِ کادر مدرسه است.", "reason": "role_forbidden"},
        )
    return user


@router.get("/models")
def list_models(
    limit: int = Query(default=15, ge=1, le=50),
    force: bool = Query(default=False, description="نادیده‌گرفتنِ کش"),
    user: User = Depends(_require_staff),
):
    """مدل‌های رایگانِ OpenRouter، از بهترین به بدترین، با دلیلِ هر امتیاز."""
    try:
        models = fetch_free_models(
            api_key=settings.OPENROUTER_API_KEY, force_refresh=force
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"دریافتِ فهرستِ مدل‌ها از OpenRouter ناموفق بود: {exc}",
                "reason": "catalog_unavailable",
            },
        ) from exc

    return {
        "provider": settings.AI_PROVIDER,
        "configured_model": settings.OPENROUTER_MODEL,
        "is_auto": settings.OPENROUTER_MODEL.strip().lower() == "auto",
        "has_api_key": bool(settings.OPENROUTER_API_KEY),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "min_context_tokens": MIN_CONTEXT_TOKENS,
        "total_free": len(models),
        "models": [m.to_dict() for m in models[:limit]],
    }


@router.post("/models/refresh")
def refresh_models(user: User = Depends(_require_staff)):
    """کراولِ اجباری — پس از اینکه مدلی بازنشسته شد یا سهمیه‌اش تمام شد."""
    clear_cache()
    try:
        models = fetch_free_models(
            api_key=settings.OPENROUTER_API_KEY, force_refresh=True
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"کراولِ دوبارهٔ مدل‌ها ناموفق بود: {exc}",
                "reason": "catalog_unavailable",
            },
        ) from exc
    return {"total_free": len(models), "top": [m.id for m in models[:5]]}


@router.post("/models/probe")
async def probe_model(body: ProbeRequest, user: User = Depends(_require_staff)):
    """یک مدل را با پرامپتِ کوچک واقعاً صدا می‌زند و زمان و صحتِ JSON را می‌گوید.

    این تنها راهِ مطمئن شدن است: «دارد در فهرست» یعنی مدل وجود دارد، نه اینکه
    همین حالا جواب می‌دهد. سهمیهٔ مدل‌های رایگان ممکن است تمام شده باشد.
    """
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "OPENROUTER_API_KEY تنظیم نشده است؛ برای آزمونِ مدل باید کلید بگذارید.",
                "reason": "missing_api_key",
            },
        )

    router_ = get_router()
    started = time.time()
    try:
        response = await router_.generate(
            body.prompt, "probe", temperature=0.0, model_override=body.model
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.time() - started, 2)
        return {
            "ok": False,
            "model": body.model,
            "elapsed_seconds": elapsed,
            "error": str(exc)[:400],
        }

    elapsed = round(time.time() - started, 2)
    text = (response.text or "").strip()
    looks_json = text.lstrip().startswith(("{", "["))

    result = {
        "ok": True,
        "model": response.model_name or body.model,
        "elapsed_seconds": elapsed,
        "cost_usd": float(response.cost_usd or 0),
        "token_count": response.token_count,
        "preview": text[:300],
        "json_ok": looks_json,
    }
    if body.expect_json and not looks_json:
        result["warning"] = (
            "مدل جواب داد ولی JSON برنگرداند. برای موتور فهم‌سنجی مناسب نیست — "
            "قراردادِ خروجی می‌شکند."
        )
    return result


# ---------------------------------------------------------------------------
# آزمونِ واقعیِ کاتالوگ
# ---------------------------------------------------------------------------
@router.post("/models/benchmark")
async def benchmark_models(
    top: int = Query(default=6, ge=1, le=15, description="چند مدلِ اول آزمون شوند"),
    user: User = Depends(_require_staff),
):
    """مدل‌های اولِ کاتالوگ را با پرامپتِ فارسیِ واقعی می‌آزماید.

    چرا لازم است: رتبه‌بندیِ فراداده می‌تواند گمراه‌کننده باشد. در آزمونِ
    واقعی، مدلی که فراداده‌اش بهترین بود («JSON دارد، شاخصِ هوش بالا»)
    خروجیِ «مشduc» داد، در حالی که مدلِ پایین‌ترِ فهرست فارسیِ بی‌نقص داد.
    این اندپوینت همان آزمون را اجرا و نتیجه را کش می‌کند.
    """
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "برای آزمونِ واقعیِ مدل‌ها باید OPENROUTER_API_KEY تنظیم شود.",
                "reason": "missing_api_key",
            },
        )

    try:
        catalog = fetch_free_models(api_key=settings.OPENROUTER_API_KEY)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail={"message": f"کاتالوگ در دسترس نیست: {exc}", "reason": "catalog_unavailable"},
        ) from exc

    candidates = [m.id for m in catalog[:top]]
    results = await probe_and_cache(candidates)
    winners = best_models(results)

    return {
        "probed": [r.to_dict() for r in results],
        "recommended": winners[:3],
        "all_failed": not winners,
        "note": (
            "این نتیجه ۶ ساعت کش می‌شود. مدلِ پیشنهادی را در .env "
            "به‌عنوان OPENROUTER_MODEL بگذارید."
            if winners
            else "هیچ مدلی آزمونِ فارسی+JSON را پاس نکرد؛ کلید و سهمیه را بررسی کنید."
        ),
    }


@router.get("/models/recommended")
def recommended_model(user: User = Depends(_require_staff)):
    """بهترین مدل بر اساسِ آخرین آزمونِ واقعی (بدونِ فراخوانیِ دوباره).

    اگر هیچ آزمونی در کش نباشد، `configured` را برمی‌گرداند تا فرانت‌اند
    بداند هنوز باید benchmark اجرا شود.
    """
    cache = load_cache()
    probed = [cached_result(model, cache) for model in cache]
    valid = [r for r in probed if r is not None and r.ok]
    winners = best_models(valid)
    return {
        "configured_model": settings.OPENROUTER_MODEL,
        "recommended": winners[0] if winners else None,
        "alternatives": winners[1:4],
        "probed_count": len([r for r in probed if r]),
        "source": "probe" if winners else "none",
        "detail": [r.to_dict() for r in valid] if valid else [],
    }
