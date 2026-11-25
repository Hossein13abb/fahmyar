"""تنظیمات فهم‌یار (Fahmyar) — خواندن پیکربندی از متغیرهای محیطی / فایل .env

توجه: هیچ کلید API یا راز امنیتی داخل کد قرار نمی‌گیرد؛ همه از محیط خوانده می‌شوند.
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Settings:
    # --- هوش مصنوعی ---
    # "gemini_free" (پیش‌فرض، نیازمند GEMINI_API_KEY رایگان از ai.google.dev)،
    # "openrouter" (مدل‌های OpenRouter از طریق HTTP — نیازمند OPENROUTER_API_KEY) یا "mock" برای تست آفلاین
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini_free")

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_MIN_INTERVAL_SECONDS: float = float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "4.0"))

    # OpenRouter
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free")
    # مدلِ اختصاصیِ زنجیرهٔ فهم‌سنجی (تولیدِ ۵ مرحله + تحلیلِ مقایسه‌ای + بازپرسی).
    # این یک تنظیمِ مستقل است، نه تکرارِ OPENROUTER_MODEL: OPENROUTER_MODEL برای
    # بقیهٔ وظایف (تولیدِ پیش‌نمایشِ کنکور، گراف، ...) به کار می‌رود و این یکی
    # فقط مسیرِ ارزیابی را می‌گیرد. اگر خالی باشد، به OPENROUTER_MODEL برمی‌گردد.
    OPENROUTER_ASSESSMENT_MODEL: str = os.getenv(
        "OPENROUTER_ASSESSMENT_MODEL", "deepseek/deepseek-v4.1-flash-1017"
    )
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # مهلت پاسخ OpenRouter (ثانیه)
    OPENROUTER_TIMEOUT_SECONDS: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "180"))
    # سقفِ توکنِ خروجی — بدونِ آن مدل‌های استدلالی پاسخِ نهایی نمی‌دهند
    OPENROUTER_MAX_TOKENS: int = int(os.getenv("OPENROUTER_MAX_TOKENS", "8000"))
    # فاصله‌گذاری ملایم بین فراخوانی‌ها (ثانیه) — برای پلن‌های رایگان مفید است
    OPENROUTER_MIN_INTERVAL_SECONDS: float = float(os.getenv("OPENROUTER_MIN_INTERVAL_SECONDS", "1.0"))
    # اختیاری: شناساندن برنامه به OpenRouter (HTTP-Referer و X-Title)
    OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "Fahmyar App")

    # --- پایگاه داده ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'fahmyar.db')}"
    )

    # --- امنیت (JWT) ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "fahmyar-dev-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    # --- بودجهٔ هزینهٔ هوش مصنوعی ---
    BUDGET_LIMIT_USD: float = float(os.getenv("BUDGET_LIMIT_USD", "10.0"))

    # --- جلسهٔ ارزیابی ---
    SESSION_TIME_LIMIT_SECONDS: int = int(os.getenv("SESSION_TIME_LIMIT_SECONDS", "1800"))
    MAX_SESSION_QUESTIONS: int = int(os.getenv("MAX_SESSION_QUESTIONS", "12"))

    # --- تحلیل پاسخ ---
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

    # --- گزارش ---
    REPORT_RESPONSE_QUOTE_CHARS: int = int(os.getenv("REPORT_RESPONSE_QUOTE_CHARS", "140"))


settings = Settings()
