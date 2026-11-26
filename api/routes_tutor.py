"""معلمِ هوشمندِ درلحظه (On-Demand Tutor) — فاز ۱۴.

قبل از این فاز، متنِ آموزشی در همان فراخوانیِ اولِ ارزیابی ساخته می‌شد:
هر کارنامه ۱۰ بلوکِ ``tutor_teaching`` با خودش حمل می‌کرد، حتی اگر هیچ‌کس
هرگز دکمهٔ معلم را نمی‌زد. این ماژول آن هزینه را از مسیرِ اصلی برمی‌دارد.

سه تصمیمِ طراحی:

۱. **مرزِ امنیتی.** این اندپوینت متنِ آزادِ کاربر را به مدل نمی‌فرستد. فقط
   شناسهٔ نشست + شمارهٔ سؤال (یا شناسهٔ یافته) می‌گیرد و بقیهٔ محتوا را از
   دیتابیس می‌خواند. دلیل: هر کاربری که توکن دارد نباید بتواند مدل را با
   پرامپتِ دلخواه صدا بزند و هزینه بسازد.

۲. **کش.** یک نشست چند بار «باز» می‌شود (دانش‌آموز برمی‌گردد، معلم نگاه
   می‌کند). پاسخ در حافظه کش می‌شود تا دکمهٔ دوم هزینهٔ دوم نسازد.

۳. **تاب‌آوری.** اگر مدل شکست بخورد، متنِ آموزشی از شواهدِ خودِ کارنامه
   ساخته می‌شود. دکمهٔ معلم هرگز به خطا یا پنجرهٔ خالی نمی‌رسد.
"""
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.json_sanitize import extract_json_object
from ai.model_abstraction import get_router
from api.routes_auth import get_current_user
from models.database import get_db
from models.user import User
from reports.exam_report import build_exam_report
from engine.session_manager import SessionError, SessionManager

router = APIRouter(prefix="/api/tutor", tags=["tutor"])

# کشِ درون‌حافظه: کلید = (session_id, kind, key) → پاسخِ آماده
_CACHE: dict[tuple[int, str, str], dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 30 * 60
_CACHE_STAMP: dict[tuple[int, str, str], float] = {}


def clear_tutor_cache() -> None:
    """برای تست‌ها و برای آزادسازیِ حافظه."""
    _CACHE.clear()
    _CACHE_STAMP.clear()


class ExplainRequest(BaseModel):
    session_id: int
    type: str = Field(pattern="^(question|contradiction|learning_gap)$")
    order: int | None = Field(default=None, ge=1, le=10)
    finding_index: int | None = Field(default=None, ge=0, le=20)
    # برای type="learning_gap": شناسهٔ گره در کارنامه. متن از دیتابیس
    # خوانده می‌شود، نه از ورودی — همان مرزِ امنیتیِ دو نوعِ دیگر.
    gap_id: str | None = Field(default=None, max_length=64)


_QUESTION_SYSTEM = """تو «معلمِ خصوصیِ فهم‌یار» هستی: معلمی صمیمی، مشوق، باهوش و
خوش‌بیان که روبه‌روی دانش‌آموز نشسته و دارد با خودِ او حرف می‌زند.

لحن: دومِ‌شخص محاوره‌ای («تو»، «خودت»، «ببین»)، گرم و پر از تمثیلِ ملموس.
هرگز سومِ‌شخصِ گزارشی ننویس («دانش‌آموز فکر کرد»، «ذهنِ او») و هرگز تحقیر نکن.
این یک جلسهٔ تدریسِ زنده است، نه گزارشِ اداری.

⛔ **قانون اکیدِ نگارش:** هرگز از استعارهٔ «ساعت»، «ساعت‌ساز»، «چرخ‌دنده» یا
«بستنِ ساعت» استفاده نکن، و نه از نام‌های متدولوژی («نقاب»، «فاینمن»،
«مونتاژِ ذهنی»، «تصویرِ کلان»). به‌جای استعاره، **مستقیماً خودِ مفهومِ علمی**
را با ادبیاتِ روان، صمیمی و استانداردِ کتابِ درسی توضیح بده. دانش‌آموز باید
مفهوم را بفهمد، نه استعاره را ترجمه کند.

فقط یک آبجکتِ JSON برگردان، بدونِ هیچ متنِ اضافه:
{
  "misconception_root": "کجای مسیر لغزید — با همدلی، اشاره به فرایندِ فکر نه به شخص (۲ تا ۳ جمله)",
  "intuitive_explanation": "اصلِ ماجرا — با یک داستان یا مثالِ شهودیِ میخکوب‌کننده آموزش بده، گام‌به‌گام (۴ تا ۶ جمله)",
  "golden_tip": "کلیدِ طلایی — یک کدِ ذهنی یا تمثیلِ کوتاه که دیگر تکرارش نکند (۱ تا ۲ جمله)"
}"""

_CONTRADICTION_SYSTEM = """تو «کارآگاهِ فهم‌یار» هستی: نیمی معلم، نیمی کارآگاه.
دانش‌آموز در یک جا حرفی زده و در جای دیگر برعکسش را. تو باید با لحنِ
دومِ‌شخصِ گرم توضیح بدهی چرا این دو تکهٔ پازل در ذهنش به هم خورده‌اند و
چطور باید به هم پل بزنند.

⛔ هرگز سومِ‌شخصِ گزارشی ننویس («دانش‌آموز فکر کرد»، «ذهنِ او»)، هرگز
تحقیر نکن، و هرگز گزارشِ اداری نده. تو با او حرف می‌زنی، نه دربارهٔ او.

⛔ **قانون اکیدِ نگارش:** هرگز از استعارهٔ «ساعت»، «ساعت‌ساز»، «چرخ‌دنده» یا
«بستنِ ساعت» استفاده نکن، و نه از نام‌های متدولوژی («نقاب»، «فاینمن»،
«مونتاژِ ذهنی»، «تصویرِ کلان»). به‌جای استعاره، **مستقیماً خودِ مفهومِ علمی**
را با ادبیاتِ روان، صمیمی و استانداردِ کتابِ درسی توضیح بده. دانش‌آموز باید
مفهوم را بفهمد، نه استعاره را ترجمه کند.

فقط یک آبجکتِ JSON برگردان، بدونِ هیچ متنِ اضافه:
{
  "why_it_happened": "چرا این تناقض در ذهنش شکل گرفت — حفظ در برابر شهود (۲ تا ۳ جمله)",
  "how_to_connect_bridge": "پلِ اتصالِ این دو مفهوم، گام‌به‌گام (۳ تا ۵ جمله)",
  "exam_shield_tip": "چطور سرِ آزمون در این دام نیفتد (۱ تا ۲ جمله)"
}"""

_GAP_SYSTEM = """تو یک استادِ برجستهٔ صمیمی هستی که روبه‌روی دانش‌آموز نشسته.
او در مبحثِ فعلی لغزیده، ولی ریشهٔ ماجرا در یک **گرهِ پیش‌نیازِ پایه‌ای** است —
چیزی که در یک پایهٔ پایین‌تر یا یک درسِ دیگر باید محکم می‌شد.

لحن: دومِ‌شخص («تو»، «خودت»، «ببین»)، گرم و بدونِ کوچک‌کردن. هرگز نگو
«این را باید از قبل می‌دانستی» — بگو «بیا این را با هم محکم کنیم».

⛔ **قانون اکیدِ نگارش:** هرگز از استعارهٔ «ساعت»، «ساعت‌ساز»، «چرخ‌دنده» یا
«بستنِ ساعت» استفاده نکن، و نه از نام‌های متدولوژی («نقاب»، «فاینمن»،
«مونتاژِ ذهنی»، «تصویرِ کلان»، «گراف وابستگی»). به‌جای استعاره، **مستقیماً
خودِ مفهومِ علمی** را با ادبیاتِ روان و استانداردِ کتابِ درسی توضیح بده.

سه بخش، دقیقاً با همین کلیدها:
{
  "why_it_matters": "چرا این موضوعِ پایه‌ای باعثِ به دام افتادن در مباحثِ بالاتر می‌شود (۲ تا ۳ جمله)",
  "intuitive_rebuild": "بازخوانیِ شهودی و سادهٔ مفهوم، با یک مثالِ ملموسِ روزمره (۴ تا ۶ جمله)",
  "memory_key": "کلیدِ ذهنیِ ماندگار برای به‌خاطر سپردنِ همیشگی (۱ تا ۲ جمله)"
}"""

_QUESTION_FALLBACK_KEYS = ("misconception_root", "intuitive_explanation", "golden_tip")
_CONTRADICTION_FALLBACK_KEYS = ("why_it_happened", "how_to_connect_bridge", "exam_shield_tip")
_GAP_FALLBACK_KEYS = ("why_it_matters", "intuitive_rebuild", "memory_key")


def _build_question_prompt(payload: dict[str, Any]) -> str:
    return (
        f"{_QUESTION_SYSTEM}\n\n"
        f"مفهوم: {payload.get('concept_title') or '—'}\n"
        f"صورتِ سؤال: {payload.get('question_text') or '—'}\n"
        f"پاسخِ دانش‌آموز: {payload.get('student_answer') or '(بدون پاسخ)'}\n"
        f"وضعیتِ تشخیصی: {payload.get('diagnostic_status') or '—'}\n"
        f"تشخیصِ اولیهٔ کارنامه: {payload.get('diagnostic_insight') or '—'}\n"
    )


def _build_contradiction_prompt(payload: dict[str, Any]) -> str:
    return (
        f"{_CONTRADICTION_SYSTEM}\n\n"
        f"مفهوم: {payload.get('concept_title') or '—'}\n"
        f"عنوانِ تناقض: {payload.get('contradiction_title') or '—'}\n"
        f"زمینهٔ دو پاسخِ متناقض: {payload.get('conflicting_answers_context') or '—'}\n"
    )


def _coerce_fields(raw: Any, keys: tuple[str, ...], fallbacks: dict[str, str]) -> dict[str, str]:
    """هر سه کلید باید غیرخالی برگردند — وگرنه متنِ جایگزین می‌نشیند."""
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, str] = {}
    for key in keys:
        value = str(src.get(key) or "").strip()
        out[key] = value or fallbacks.get(key, "")
    return out


def _question_fallbacks(payload: dict[str, Any]) -> dict[str, str]:
    insight = str(payload.get("diagnostic_insight") or "").strip()
    answer = str(payload.get("student_answer") or "").strip()
    return {
        "misconception_root": insight
        or (
            "این‌جا جوابی نرسید، پس با هم از صفر شروع می‌کنیم — اشکالی ندارد."
            if not answer
            else "استدلالت یک قدم زودتر از جایی که لازم بود ایستاد؛ بیا با هم کاملش کنیم."
        ),
        "intuitive_explanation": (
            "بیا قدم‌به‌قدم برویم: اول ببین صورتِ سؤال واقعاً چه می‌خواهد، "
            "بعد همان رابطه را روی کمیت‌های دخیل به کار ببر، و در آخر یک بار "
            "نتیجه را در دنیای واقعی تصور کن تا حسش کنی."
        ),
        "golden_tip": (
            "کلیدِ مفهومی: قبل از هر محاسبه از خودت بپرس «کدام کمیت واقعاً این‌جا "
            "نقش دارد و کدام یکی فقط تماشاچی است؟»"
        ),
    }


def _contradiction_fallbacks(payload: dict[str, Any]) -> dict[str, str]:
    context = str(payload.get("conflicting_answers_context") or "").strip()
    return {
        "why_it_happened": (
            f"دو جوابت یک حرف را نمی‌زنند: {context}"
            if context
            else "دو جوابت یک حرف را نمی‌زنند — یکی از حفظ آمده و آن یکی از شهودِ خودت."
        ),
        "how_to_connect_bridge": (
            "هر دو پاسخ را کنارِ هم بگذار و ببین کدام‌شان با قانونِ اصلیِ مفهوم "
            "هم‌خوان است؛ همان یکی حرفِ آخر را می‌زند و آن یکی باید اصلاح شود."
        ),
        "exam_shield_tip": (
            "قبل از زدنِ گزینه یک ثانیه از خودت بپرس: «اگر همین را می‌خواستم "
            "تشریح کنم، همین جواب را می‌دادم؟»"
        ),
    }


def _build_gap_prompt(payload: dict[str, Any]) -> str:
    return (
        f"{_GAP_SYSTEM}\n\n"
        f"مفهومِ فعلیِ دانش‌آموز: {payload.get('concept_title') or '—'}\n"
        f"گرهٔ پیش‌نیاز: {payload.get('gap_title') or '—'}\n"
        f"جایگاهِ آن: {payload.get('source_topic') or '—'}\n"
        f"چرا همین گره باعثِ لغزش شده: {payload.get('why_you_slipped') or '—'}\n"
        f"کلیدِ سریعِ کارنامه: {payload.get('quick_fix_tip') or '—'}\n"
    )


def _gap_fallbacks(payload: dict[str, Any]) -> dict[str, str]:
    """متنِ جایگزین وقتی مدل در دسترس نیست — از دادهٔ خودِ کارنامه."""
    topic = str(payload.get("source_topic") or "").strip()
    where = f"در {topic}" if topic else "در یک پایهٔ پایین‌تر"
    title = str(payload.get("gap_title") or "").strip() or "این گرهٔ پیش‌نیاز"
    why = str(payload.get("why_you_slipped") or "").strip().replace("$", "")
    return {
        "why_it_matters": (
            f"«{title}» {where} ساخته می‌شود، و مبحثِ فعلی روی همین بنا شده. "
            "تا وقتی این پایه سست باشد، هر بار در سطحِ بالاتر به همان نقطه می‌رسی."
        ),
        "intuitive_rebuild": (
            f"چرا این گره مهم است؟ {why} همین حلقه، وقتی به مبحثِ بالاتر می‌رسی "
            "دوباره سرِ راهت سبز می‌شود؛ پس ارزش دارد یک بار بنشینی و تا ته "
            "بفهمیش. یک راهِ عملی: همین مفهوم را برای خودت با یک مثالِ روزمره "
            "تعریف کن — یک مثال که بتوانی بدونِ هیچ فرمولی برای یک نفر دیگر "
            "بگویی. اگر توانستی، گره باز شده است."
        ),
        "memory_key": str(payload.get("quick_fix_tip") or "").strip()
        or "هر وقت به این مبحث رسیدی، اول از خودت بپرس «این از کدام پایه آمده؟»",
    }


def _pick_question(per_question: list[dict[str, Any]], order: int | None) -> dict[str, Any]:
    if not per_question:
        raise HTTPException(status_code=404, detail="این نشست هنوز کارنامه‌ای ندارد.")
    if order is None:
        return per_question[0]
    match = next((q for q in per_question if int(q.get("order") or 0) == order), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"سؤالِ {order} در این کارنامه نیست.")
    return match


def _answers_context(q: dict[str, Any]) -> str:
    """زمینه‌ای که مدل می‌بیند: پاسخ چیست و چرا کارنامه ایراد گرفت."""
    parts = [
        f"پاسخ: {q.get('response') or q.get('student_answer_summary') or '(بدون پاسخ)'}",
        f"وضعیت: {q.get('status') or '—'}",
    ]
    if q.get("diagnostic_insight"):
        parts.append(f"تشخیص: {q['diagnostic_insight']}")
    if q.get("cognitive_verdict"):
        parts.append(f"داوری: {q['cognitive_verdict']}")
    return " | ".join(parts)


def _offline() -> bool:
    """حالتِ آفلاین: هیچ فراخوانیِ مدل انجام نمی‌شود.

    برای تستِ فرانت/دمو بدونِ هزینهٔ API. اگر روشن باشد، پاسخ همیشه از
    متنِ جایگزین ساخته می‌شود — همان مسیری که وقتی مدل می‌میرد طی می‌شود.
    """
    return (os.getenv("FAHMYAR_TUTOR_OFFLINE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


async def _call_model(prompt: str) -> dict[str, Any] | None:
    """فراخوانیِ مدل با گاردِ کامل. ``None`` یعنی «نتوانستیم»."""
    if _offline():
        return None
    try:
        router_instance = get_router()
        response = await router_instance.generate(
            prompt, task_type="tutor_explain", temperature=0.75
        )
        parsed = extract_json_object(getattr(response, "text", "") or "")
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001 — هر شکستی باید به fallback برسد
        return None


@router.post("/explain")
async def explain(
    body: ExplainRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """تدریسِ درلحظه برای یک سؤال یا یک تناقض.

    ورودی فقط شناسه است، نه متنِ آزاد: مرزِ امنیتی در برابرِ سوءاستفاده از
    مدل با پرامپتِ دلخواهِ کاربر.
    """
    # دسترسی همان مسیرِ کارنامه سنجیده می‌شود: دانش‌آموز فقط نشستِ خودش
    # را می‌بیند، معلم/مدیر نشستِ مدرسه را. هیچ راهِ دوری وجود ندارد.
    try:
        session = SessionManager(db).get_session(body.session_id, user)
    except SessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = build_exam_report(db, session)
    concept_title = str(report.get("concept_name") or "—")

    cache_key = (
        body.session_id,
        body.type,
        f"{body.order}:{body.finding_index}:{body.gap_id or ''}",
    )
    stamp = _CACHE_STAMP.get(cache_key)
    if stamp and time.time() - stamp < _CACHE_TTL_SECONDS and cache_key in _CACHE:
        return {**_CACHE[cache_key], "cached": True}

    if body.type == "question":
        q = _pick_question(list(report.get("per_question") or []), body.order)
        payload = {
            "concept_title": concept_title,
            "question_text": q.get("question_text") or "",
            "student_answer": q.get("response") or "",
            "diagnostic_status": q.get("status") or "",
            "diagnostic_insight": q.get("diagnostic_insight") or "",
        }
        raw = await _call_model(_build_question_prompt(payload))
        content = _coerce_fields(
            raw, _QUESTION_FALLBACK_KEYS, _question_fallbacks(payload)
        )
        result = {
            "type": "question",
            "order": q.get("order"),
            "concept_title": concept_title,
            "generated_by": "model" if raw else "fallback",
            "content": content,
        }
    elif body.type == "learning_gap":
        # گره از کارنامه خوانده می‌شود، نه از ورودی. اگر کارنامه این شناسه را
        # ندارد، همان ۴۰۴ — کاربر نمی‌تواند با ساختنِ gap_id دلخواه، مدل را
        # با پرامپتِ خودش صدا بزند.
        gaps = list(report.get("learning_gaps") or [])
        if not gaps:
            raise HTTPException(
                status_code=404, detail="در این کارنامه گرهٔ پیش‌نیازی ثبت نشده است."
            )
        gap = next(
            (g for g in gaps if str(g.get("id")) == body.gap_id), None
        ) if body.gap_id else gaps[0]
        if gap is None:
            raise HTTPException(
                status_code=404, detail="این گره در کارنامهٔ این آزمون پیدا نشد."
            )
        payload = {
            "concept_title": concept_title,
            "gap_title": gap.get("gap_title") or "",
            "source_topic": gap.get("source_topic") or "",
            "why_you_slipped": gap.get("why_you_slipped") or "",
            "quick_fix_tip": gap.get("quick_fix_tip") or "",
        }
        raw = await _call_model(_build_gap_prompt(payload))
        content = _coerce_fields(raw, _GAP_FALLBACK_KEYS, _gap_fallbacks(payload))
        result = {
            "type": "learning_gap",
            "gap_id": gap.get("id"),
            "gap_title": gap.get("gap_title"),
            "concept_title": concept_title,
            "generated_by": "model" if raw else "fallback",
            "content": content,
        }
    else:
        all_findings = list(report.get("cross_check_findings") or [])
        # ``finding_index`` ایندکسِ **کلِ** فهرست است، نه فهرستِ فیلترشده.
        # فرانت کارت‌ها را به همین ترتیب رندر می‌کند؛ اگر این‌جا فقط
        # CONTRADICTIONها شمرده شوند، کاربر تناقضِ اشتباه (یا ۴۰۴) می‌گیرد.
        idx = body.finding_index if body.finding_index is not None else 0
        if idx >= len(all_findings):
            raise HTTPException(status_code=404, detail="شمارهٔ تناقض خارج از فهرست است.")
        candidate = all_findings[idx]
        if str(candidate.get("type") or "").upper() != "CONTRADICTION":
            # تحملِ ورودیِ قدیمی: ایندکس ممکن است نسبت به فهرستِ فیلترشده باشد.
            contradictions = [
                f
                for f in all_findings
                if str(f.get("type") or "").upper() == "CONTRADICTION"
            ]
            if not contradictions:
                raise HTTPException(
                    status_code=404, detail="در این کارنامه تناقضی ثبت نشده است."
                )
            if idx >= len(contradictions):
                raise HTTPException(
                    status_code=404, detail="شمارهٔ تناقض خارج از فهرست است."
                )
            candidate = contradictions[idx]
        finding = candidate
        payload = {
            "concept_title": concept_title,
            "contradiction_title": finding.get("contradiction_title") or finding.get("title"),
            "conflicting_answers_context": finding.get("description") or "",
        }
        raw = await _call_model(_build_contradiction_prompt(payload))
        content = _coerce_fields(
            raw, _CONTRADICTION_FALLBACK_KEYS, _contradiction_fallbacks(payload)
        )
        result = {
            "type": "contradiction",
            "finding_index": idx,
            "title": payload["contradiction_title"],
            "concept_title": concept_title,
            "generated_by": "model" if raw else "fallback",
            "content": content,
        }

    _CACHE[cache_key] = result
    _CACHE_STAMP[cache_key] = time.time()
    return {**result, "cached": False}
