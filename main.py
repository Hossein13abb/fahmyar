"""نقطه‌ی ورود اپلیکیشن فهم‌یار (Fahmyar) — سنجش فهم، نه فقط درستی پاسخ.

اجرا:
    python -c "from models.database import init_db; init_db()"
    python -c "from graph.seed_data import seed_all; seed_all()"
    uvicorn main:app --reload

سپس: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from models.database import SessionLocal, init_db
from models.concept import Concept


@asynccontextmanager
async def lifespan(app: FastAPI):
    # راه‌اندازی: جدول‌ها و (در صورت خالی بودن) داده‌های اولیه
    init_db()
    db = SessionLocal()
    try:
        if db.query(Concept).count() == 0:
            from graph.seed_data import seed_all

            print("🌱 پایگاه داده خالی است — در حال seed کردن داده‌های اولیه…")
            seed_all(db=db)
    finally:
        db.close()

    # مدلِ ارزیابی هنگام بالا آمدنِ سرور صریح چاپ می‌شود. اگر این خط نباشد،
    # تنها راهِ فهمیدنِ «با کدام مدل آزمون دادیم» خواندنِ لاگِ درخواست‌هاست —
    # و همین باعث شده بود مدلِ اشتباه بی‌سروصدا کار کند.
    try:
        from ai.model_abstraction import assessment_model_name

        print(
            f"[AI] assessment model = {assessment_model_name()} "
            f"(source: OPENROUTER_ASSESSMENT_MODEL; "
            f"timeout={settings.OPENROUTER_TIMEOUT_SECONDS}s)"
        )
        if not (settings.OPENROUTER_API_KEY or "").strip():
            print("[AI] ⚠ OPENROUTER_API_KEY خالی است — فراخوانی‌های مدل شکست می‌خورند.")
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] could not resolve assessment model: {exc}")
    yield


app = FastAPI(
    title="فهم‌یار — Fahmyar",
    description=(
        "سیستم تشخیصیِ آموزشی برای سنجشِ فهمیدن (نه فقط درستی پاسخ). "
        "شواهد کیفی جمع می‌کند، ریشهٔ خطا را (حتی بین‌درسی) ایزوله می‌کند و گزارش کیفی می‌سازد. "
        "هیچ نمره/رتبه/مقایسه‌ای تولید نمی‌شود."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # برای محیط توسعه؛ در تولید محدود کنید
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes_auth import router as auth_router  # noqa: E402
from api.routes_ai_models import router as ai_models_router  # noqa: E402
from api.routes_assessment import router as assessment_router  # noqa: E402
from api.routes_exam import router as exam_router  # noqa: E402
from api.routes_admin import router as admin_router  # noqa: E402
from api.routes_tutor import router as tutor_router  # noqa: E402

app.include_router(auth_router)
app.include_router(ai_models_router)
app.include_router(assessment_router)
app.include_router(exam_router)
app.include_router(admin_router)
app.include_router(tutor_router)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "فهم‌یار — Fahmyar",
        "tagline": "سنجش فهمیدن، نه فقط درستی پاسخ",
        "version": "0.1.0",
        "docs": "/docs",
        "ai_provider": settings.AI_PROVIDER,
        "disclaimer": "⚠️ نمرهٔ آزمون — نه سنجش فهم",
    }


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "ai_provider": settings.AI_PROVIDER}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # اطمینان از پاسخ JSON به‌جای HTML
    return JSONResponse(status_code=500, content={"detail": f"خطای داخلی سرور: {exc}"})
