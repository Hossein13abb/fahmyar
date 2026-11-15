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
