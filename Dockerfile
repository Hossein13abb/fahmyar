# ─────────────────────────────────────────────────────────────────────────────
# فهم‌یار — Fahmyar
#
# سه مرحله:
#   frontend-build : باندل Vite را می‌سازد (خروجی در /app/frontend/dist)
#   pdf-browser    : لایهٔ پایه + Chromium و همهٔ کتابخانه‌های سیستمی‌اش
#   runtime        : بک‌اند FastAPI + باندل فرانت‌اند، بدون ابزار build
#
# چرا چندمرحله‌ای: npm و ابزارهای کامپایل نباید در تصویر نهایی باشند، اما
# خروجی build باید باشد — چون موتور PDF صفحهٔ frontend/dist/print.html را در
# Chromium باز می‌کند.
# ─────────────────────────────────────────────────────────────────────────────

# ═══ مرحلهٔ ۱ — ساخت باندل فرانت‌اند ═══════════════════════════════════════════
FROM node:20-bookworm-slim AS frontend-build

WORKDIR /build

# ابتدا فقط فایل‌های وابستگی: تا وقتی package.json تغییر نکند، لایهٔ npm ci
# از کش می‌آید و build سریع می‌ماند.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# سپس بقیهٔ کد فرانت‌اند
COPY frontend/ ./
RUN npm run build

# خروجی: /build/dist  (شامل index.html اپ و print.html موتور PDF)


# ═══ مرحلهٔ ۲ — پایهٔ اجرا + مرورگر ═══════════════════════════════════════════
FROM python:3.13-slim-bookworm AS pdf-browser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # مسیر مشترکِ باینری مرورگر: باید در همان مرحله‌ای تعریف شود که
    # `playwright install` اجرا می‌شود، وگرنه باینری جای پیش‌فرض (~/.cache) نصب
    # می‌شود و COPY از /ms-playwright با «not found» شکست می‌خورد.
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Chromium هدلس به این کتابخانه‌های اشتراکی نیاز دارد. بدون آن‌ها با خطای
# «error while loading shared libraries: libnspr4.so» می‌میرد — دقیقاً همان
# چیزی که در محیط توسعه هم رخ داد. pip فقط پکیج پایتون را می‌آورد، نه این‌ها.
#
# فهرست عمداً صریح است (نه اتکا به `playwright install-deps` که به مخزن apt
# بیرونی و sudo نیاز دارد): هر کتابخانه با نقشش مستند شده تا معلوم باشد چرا
# هست و حذفش چه چیزی را می‌شکند.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # libatomic — ابزارِ نصبِ خودِ playwright (درایورِ Node) پیش از دانلود مرورگر
    # به آن نیاز دارد؛ بدونش `playwright install` در همان گام اول می‌میرد.
    libatomic1 \
    # NSPR — لایهٔ پورت‌پذیری که NSS روی آن سوار است؛ بارگذارِ دینامیک Chromium
    # پیش از هر چیز دیگری به آن نیاز دارد.
    libnspr4 \
    # NSS — رمزنگاری/TLS؛ Chromium حتی برای بارگذاری file:// و http:// محلی
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
    # ابزارهای تشخیصی که در logs مفیدند
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# وابستگی‌های پایتون
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium و اسکریپت کمکی‌اش. نسخه از requirements.txt می‌آید تا پکیج
# پایتون و باینری مرورگر همیشه هم‌خوان بمانند.
# بدون `|| true`: اگر نصبِ مرورگر شکست بخورد، build باید همان‌جا شکست بخورد.
# (این خط پیش‌تر با `|| true` بی‌صدا رد می‌شد و تصویر بدون مرورگر ساخته می‌شد.)
RUN python -m playwright install chromium

# ابزار تأیید سلامت — در build اجرا می‌شود تا اگر باینری/کتابخانه‌ای جا افتاد،
# ساخت همان‌جا شکست بخورد نه در اولین درخواست کاربر.
COPY deploy/verify_runtime.py /app/deploy/verify_runtime.py


# ═══ مرحلهٔ ۳ — تصویر نهایی ═══════════════════════════════════════════════════
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    APP_HOME=/app

# همان کتابخانه‌های سیستمی، از مرحلهٔ ۲ کپی می‌شوند تا تعریف دوباره نشوند.
# apt-get و کش آن در تصویر نهایی نمی‌مانند.
COPY --from=pdf-browser /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
COPY --from=pdf-browser /usr/share/fonts /usr/share/fonts
COPY --from=pdf-browser /etc/fonts /etc/fonts

# باینری مرورگر و پکیج‌های پایتون
COPY --from=pdf-browser /ms-playwright /ms-playwright
COPY --from=pdf-browser /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=pdf-browser /usr/local/bin /usr/local/bin

WORKDIR /app

# کد بک‌اند
COPY . /app

# باندل فرانت‌اند از مرحلهٔ ۱ — قلبِ موتور PDF. بدون این، capture.py با
# CaptureError سر بلند می‌کند و API خطای 503 با پیام روشن می‌دهد.
COPY --from=frontend-build /build/dist /app/frontend/dist

# ریشهٔ فرانت‌اند نباید node_modules یا کد منبعِ اضافی با خود ببرد؛ فقط خروجی
# build لازم است. (این خط در صورت وجود فایل‌های اضافی آن‌ها را پاک می‌کند.)
RUN rm -rf /app/frontend/node_modules /app/frontend/src /app/frontend/public

# کاربر غیر‌ریشه. Chromium با --no-sandbox اجرا می‌شود (پایین‌تر توضیح داده شده)
# و کش/پروفایل مرورگر به HOME نیاز دارد.
RUN useradd --create-home --uid 10001 --shell /bin/bash fahmyar \
 && mkdir -p /app/.cache /tmp/fahmyar-pdf \
 && chown -R fahmyar:fahmyar /app/.cache /tmp/fahmyar-pdf /app

ENV HOME=/home/fahmyar \
    XDG_CACHE_HOME=/app/.cache \
    TMPDIR=/tmp/fahmyar-pdf

USER fahmyar

# تأیید سلامت: Chromium واقعاً اجرا می‌شود و یک صفحه می‌سازد.
# اگر این شکست بخورد، تصویر معیوب است و باید در build معلوم شود.
RUN python /app/deploy/verify_runtime.py

EXPOSE 8000

# یک worker: هر درخواست PDF خودش یک Chromium کوتاه‌عمر بالا می‌آورد.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
