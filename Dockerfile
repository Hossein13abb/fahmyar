# ─────────────────────────────────────────────────────────────────────────────
# فهم‌یار — Fahmyar
#
# دو مرحله:
#   frontend-build : باندل Vite را می‌سازد (index.html اپ + print.html موتور PDF)
#   runtime        : Python + Chromium + کتابخانه‌های سیستمی + باندل فرانت‌اند
#
# چرا باندل فرانت‌اند بخشی از تصویر است و نه یک دارایی بیرونی: موتور تولید PDF،
# صفحهٔ frontend/dist/print.html را در Chromium باز می‌کند تا سند را با همان
# کامپوننت‌های پیش‌نمایش رندر کند. بدون آن، تولید PDF اصلاً شروع نمی‌شود.
# ─────────────────────────────────────────────────────────────────────────────

# ═══ مرحلهٔ ۱ — ساخت باندل فرانت‌اند ═══════════════════════════════════════════
FROM node:20-bookworm-slim AS frontend-build

WORKDIR /build

# ابتدا فقط فایل‌های وابستگی: تا وقتی package.json تغییر نکند، لایهٔ npm ci از
# کش می‌آید و build سریع می‌ماند.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# سپس بقیهٔ کد فرانت‌اند
COPY frontend/ ./
RUN npm run build

# خروجی: /build/dist


# ═══ مرحلهٔ ۲ — تصویر نهایی ═══════════════════════════════════════════════════
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # مسیر مشترکِ باینری مرورگر: باید در همان مرحله‌ای تعریف شود که
    # `playwright install` اجرا می‌شود، وگرنه باینری جای پیش‌فرض (~/.cache) نصب
    # می‌شود و در مسیر مورد انتظار پیدا نمی‌شود.
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    APP_HOME=/app

# Chromium هدلس به این کتابخانه‌های اشتراکی نیاز دارد. بدون آن‌ها با خطای
# «error while loading shared libraries: libnspr4.so» می‌میرد — دقیقاً همان
# چیزی که در محیط توسعه هم رخ داد.
#
# فهرست عمداً صریح است (نه اتکا به `playwright install-deps` که به مخزن apt
# بیرونی و sudo نیاز دارد): هر کتابخانه با نقشش مستند شده تا معلوم باشد چرا
# هست و حذفش چه چیزی را می‌شکند.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # libatomic — ابزار نصبِ خودِ playwright (درایورِ Node) پیش از دانلود مرورگر
    # به آن نیاز دارد؛ بدونش `playwright install` در همان گام اول می‌میرد.
    libatomic1 \
    # NSPR — لایهٔ پورت‌پذیری که NSS روی آن سوار است؛ بارگذارِ دینامیک Chromium
    # پیش از هر چیز دیگری به آن نیاز دارد.
    libnspr4 \
    # NSS — رمزنگاری/TLS؛ Chromium حتی برای بارگذاری http://127.0.0.1 محلی
    # این لایه را مقدار‌دهی می‌کند و بدون آن سقوط می‌کند.
    libnss3 \
    # ATK و ATK-Bridge — درخت دسترس‌پذیری (a11y)؛ Chromium همیشه می‌سازدش.
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    # محیط میزکار GTK که Chromium برای دیالوگ‌های چاپ/فایل لینک می‌کند.
    libgtk-3-0 \
    # cups — زیرسیستم چاپ؛ Chromium آن را در زمان لینک لازم دارد.
    libcups2 \
    # مدیریت حافظه/گرافیک سطح پایین کارت گرافیک و DRM
    libdrm2 \
    libgbm1 \
    # کتابخانهٔ ورودی صفحه‌کلید/ماوس (X11) — حتی هدلس لینک می‌شود
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxext6 \
    libx11-6 \
    libxcb1 \
    # Pango/Cairo — موتور چیدمان و رستر متن؛ کیفیت رندر فونت فارسی به آن‌ها وابسته است
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    # ALSA — Chromium صدای سیستم را لینک می‌کند؛ حتی بی‌کاربرد باید حاضر باشد.
    # نامِ «libasound2» یک بستهٔ مجازی است: در bookworm به libasound2 می‌رسد و
    # در trixie به libasound2t64. با همین نام، build روی هر دو توزیع کار
    # می‌کند؛ نوشتن libasound2t64 صریح، bookworm را می‌شکند.
    libasound2 \
    # فونت‌های پایهٔ سیستم به‌عنوان آخرین سنگرِ fallback؛ متن اصلی با
    # Vazirmatn و KaTeX رندر می‌شود که همراه خود پروژه‌اند
    fonts-dejavu-core \
    fonts-liberation \
    # ابزار تشخیصی برای HEALTHCHECK و عیب‌یابی
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# وابستگی‌های پایتون
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium و اسکریپت کمکی‌اش. نسخه از requirements.txt می‌آید تا پکیج پایتون
# و باینری مرورگر همیشه هم‌خوان بمانند.
#
# بدون `|| true`: اگر نصبِ مرورگر شکست بخورد، build باید همان‌جا شکست بخورد.
# (این خط پیش‌تر با `|| true` بی‌صدا رد می‌شد و تصویر بدون مرورگر ساخته می‌شد.)
RUN python -m playwright install chromium

# کد بک‌اند
COPY . /app

# باندل فرانت‌اند از مرحلهٔ ۱ — قلبِ موتور PDF.
COPY --from=frontend-build /build/dist /app/frontend/dist

# ریشهٔ فرانت‌اند نباید کد منبع یا node_modules با خود ببرد؛ فقط خروجی build
# لازم است. (اگر .dockerignore چیزی جا گذاشت، این خط آن را پاک می‌کند.)
RUN rm -rf /app/frontend/node_modules /app/frontend/src /app/frontend/public

# کاربر غیر‌ریشه. Chromium با --no-sandbox اجرا می‌شود (پایین‌تر توضیح داده شده)
# و کش/پروفایل موقت به HOME و TMPDIR نیاز دارد.
RUN useradd --create-home --uid 10001 --shell /bin/bash fahmyar \
 && mkdir -p /app/.cache /tmp/fahmyar-pdf \
 && chown -R fahmyar:fahmyar /app/.cache /tmp/fahmyar-pdf /app

ENV HOME=/home/fahmyar \
    XDG_CACHE_HOME=/app/.cache \
    TMPDIR=/tmp/fahmyar-pdf

USER fahmyar

# تأیید سلامت: Chromium واقعاً اجرا می‌شود و یک صفحه می‌سازد، باندل و فونت
# سرجایشان هستند. اگر این شکست بخورد، تصویر معیوب است و باید در build معلوم
# شود — نه در اولین درخواست کاربر.
RUN python /app/deploy/verify_runtime.py

EXPOSE 8000

# هر درخواست PDF خودش یک Chromium کوتاه‌عمر بالا می‌آورد.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
