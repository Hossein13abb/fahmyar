"""کشِ دفترچهٔ آزمون — برای صرفه‌جویی در توکن (فاز ۱۱، بندِ ۴).

مبحثِ تکراری نباید دوباره از مدل پرسیده شود. کلیدِ کش از *مشخصاتِ مفهومی*
ساخته می‌شود (نام، درس، پایه) و نه از شناسهٔ ردیفِ دیتابیس؛ پس دو مفهومِ
هم‌نام در دو پایهٔ متفاوت با هم قاطی نمی‌شوند.

سه لایه:
  ۱. **کشِ درون‌حافظه‌ای** (سریع، برای درخواست‌های پشتِ‌سرهمِ یک پروسه)
  ۲. **کشِ دیسک** (JSON، تا با ری‌استارتِ سرور هم باقی بماند)
  ۳. اگر ``FAHMYAR_BOOKLET_CACHE=0`` باشد، کلِ سازوکار خاموش می‌شود.

کش فقط برای دفترچهٔ **تولیدشده با مدل** به کار می‌رود؛ قالبِ اضطراری هیچ‌وقت
کش نمی‌شود تا یک شکستِ گذرا به «تولیدِ موفقِ همیشگی» تبدیل نشود.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

_CACHE_VERSION = "v1"

#: مسیرِ دیسک. با متغیرِ محیطی قابلِ تغییر است (برای تست‌ها).
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".cache" / "booklets.json"

#: کشِ درون‌حافظه‌ای: کلید → (items, model_name, cost)
_memory: dict[str, tuple[list[dict[str, Any]], str, float]] = {}
_loaded = False


def cache_enabled() -> bool:
    return str(os.getenv("FAHMYAR_BOOKLET_CACHE", "1")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _cache_path() -> Path:
    override = os.getenv("FAHMYAR_BOOKLET_CACHE_PATH")
    return Path(override) if override else _DEFAULT_PATH


def booklet_cache_key(concept, wrong_answer: dict | None = None) -> str:
    """کلیدِ پایدار بر اساسِ مشخصاتِ محتواییِ مفهوم (نه شناسهٔ دیتابیس)."""
    payload = {
        "v": _CACHE_VERSION,
        "name": str(getattr(concept, "name", "") or "").strip(),
        "subject": str(getattr(concept, "subject", "") or "").strip(),
        "grade": str(getattr(concept, "grade", "") or "").strip(),
        "propositions": [
            str(p).strip()
            for p in (getattr(concept, "core_propositions", None) or [])
            if str(p).strip()
        ],
        "misconceptions": [
            str(m).strip()
            for m in (getattr(concept, "common_misconceptions", None) or [])
            if str(m).strip()
        ],
        # trigger از نوعِ «پاسخِ غلط» دفترچهٔ متفاوتی می‌سازد
        "wrong": (wrong_answer or {}).get("problem_text") if wrong_answer else None,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_disk() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not cache_enabled():
        return
    path = _cache_path()
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        items = entry.get("items")
        if not isinstance(items, list):
            continue
        _memory[key] = (
            [i for i in items if isinstance(i, dict)],
            str(entry.get("model") or ""),
            float(entry.get("cost") or 0.0),
        )


def _flush_disk() -> None:
    if not cache_enabled():
        return
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {"items": items, "model": model, "cost": cost}
            for key, (items, model, cost) in _memory.items()
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)
    except OSError:
        # کش نباید هرگز مسیرِ آزمون را بشکند.
        pass


def get_cached_booklet(
    key: str,
) -> Optional[tuple[list[dict[str, Any]], str, float]]:
    """دفترچهٔ کش‌شده یا ``None``. خروجی یک کپیِ عمیق است تا مصرف‌کننده نتواند
    کشِ مشترک را تغییر دهد."""
    if not cache_enabled():
        return None
    _load_disk()
    hit = _memory.get(key)
    if hit is None:
        return None
    items, model, cost = hit
    return json.loads(json.dumps(items)), model, cost


def put_cached_booklet(
    key: str, items: list[dict[str, Any]], model_name: str, cost: float
) -> None:
    """دفترچهٔ تولیدشده را کش می‌کند. بی‌صدا از خطا می‌گذرد."""
    if not cache_enabled():
        return
    _load_disk()
    safe_items = json.loads(json.dumps(items))
    _memory[key] = (safe_items, model_name, float(cost or 0.0))
    _flush_disk()


def clear_cache() -> None:
    """پاک‌کردنِ کاملِ کش — برای تست‌ها و ابزارِ مدیریت."""
    global _loaded
    _memory.clear()
    _loaded = False
    if cache_enabled():
        try:
            _cache_path().unlink(missing_ok=True)
        except OSError:
            pass


def cache_stats() -> dict[str, Any]:
    _load_disk()
    return {
        "enabled": cache_enabled(),
        "entries": len(_memory),
        "path": str(_cache_path()),
    }
