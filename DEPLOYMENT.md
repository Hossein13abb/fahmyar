# استقرار — فهم‌یار

## ساخت و اجرا

```bash
docker build -t fahmyar:latest .
docker run -d -p 8000:8000 --name fahmyar fahmyar:latest
```

سپس: `http://localhost:8000/docs`

### متغیرهای محیطی

از `docker run -e` یا `--env-file .env` بدهید. متغیرهای مؤثر:

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `AI_PROVIDER` | از `.env` | `mock` برای اجرای آفلاین، `gemini_free` برای تولید واقعی |
| `GEMINI_API_KEY` | — | فقط با `gemini_free` لازم است |
| `JWT_SECRET` | `fahmyar-dev-secret-change-me` | **در استقرار تغییر دهید** |

`.env` عمداً در `.dockerignore` است و هرگز داخل تصویر نمی‌رود.

---

## چرا Dockerfile دو مرحله دارد

```
frontend-build   node:20   →  /build/dist   (باندل Vite: index.html + print.html)
runtime          python    →  کد + باندل + Chromium، بدون npm و node_modules
```

نسخهٔ اول سه مرحله بود و کتابخانه‌های سیستمی را بین دو مرحلهٔ پایتونی کپی
می‌کرد. همان کپی، build را روی معماری‌های مختلف می‌شکست (مسیر
`/usr/lib/x86_64-linux-gnu` روی arm64 وجود ندارد و `TARGETARCH` مقدار `amd64`
می‌دهد نه `x86_64`). حذف آن مرحله، هم تصویر را ساده‌تر کرد و هم مسئله را از
ریشه برداشت.

موتور PDF آزمون، صفحهٔ `frontend/dist/print.html` را در Chromium باز می‌کند
تا سند را با همان کامپوننت‌های پیش‌نمایش رندر کند. پس **باندل فرانت‌اند بخشی
از زمان اجراست، نه فقط یک دارایی ثابت** — بدون آن، تولید PDF اصلاً شروع
نمی‌شود. لهذا در تصویر نهایی وجود دارد و در زمان build ساخته می‌شود.

---

## وابستگی‌های سیستمی Chromium

`pip install playwright` فقط پکیج پایتون را می‌آورد. باینری مرورگر و کتابخانه‌های
اشتراکی‌اش جدا هستند. بدون این‌ها، اولین اجرا با
`error while loading shared libraries` می‌میرد — این دقیقاً در محیط توسعه هم
اتفاق افتاد.

| بسته | چرا لازم است |
|---|---|
| `libatomic1` | **ابزار نصب خود playwright** (درایور Node) پیش از هر دانلودی به آن نیاز دارد |
| `libnspr4` | لایهٔ پورت‌پذیری NSPR؛ بارگذارِ دینامیک Chromium اول از همه آن را می‌خواهد |
| `libnss3` | NSS؛ رمزنگاری/TLS — Chromium حتی برای `http://127.0.0.1` مقداردهی می‌کند |
| `libatk1.0-0`, `libatk-bridge2.0-0` | درخت دسترس‌پذیری (a11y) که Chromium همیشه می‌سازد |
| `libgtk-3-0` | محیط میزکار GTK برای دیالوگ‌ها |
| `libcups2` | زیرسیستم چاپ |
| `libdrm2`, `libgbm1` | مدیریت حافظه/گرافیک سطح پایین |
| `libxkbcommon0`, `libxcomposite1`, `libxdamage1`, `libxfixes3`, `libxrandr2`, `libxrender1`, `libxext6`, `libx11-6`, `libxcb1` | ورودی و ترکیب‌بندی X11؛ حتی حالت هدلس لینک می‌شود |
| `libpango-1.0-0`, `libpangocairo-1.0-0`, `libcairo2` | چیدمان و رستر متن — **کیفیت رندر فونت فارسی به این‌ها وابسته است** |
| `libasound2` | ALSA؛ Chromium صدای سیستم را لینک می‌کند |
| `fonts-dejavu-core`, `fonts-liberation` | آخرین سنگر fallback؛ متن اصلی با Vazirmatn و KaTeX رندر می‌شود که همراه پروژه‌اند |

### نکتهٔ نام بسته در توزیع‌ها

`libasound2` یک **بستهٔ مجازی** است: در Bookworm به `libasound2` و در Trixie به
`libasound2t64` می‌رسد. نوشتن نام صریحِ `libasound2t64` باعث شکست build روی
Bookworm می‌شود (تجربه شد: `Unable to locate package libasound2t64`). نام مجازی
هر دو را پوشش می‌دهد.

نسخهٔ پایتون پایه `3.13-slim-bookworm` است (هم‌خوان با `README` که ۳٫۱۱+ می‌خواهد).

### گام تأیید سلامت در build

`deploy/verify_runtime.py` در انتهای build اجرا می‌شود و سه چیز را می‌سنجد:

1. باندل و ورودی چاپ موجودند
2. فونت Vazirmatn همراه باندل است
3. **Chromium واقعاً اجرا می‌شود و یک اسکرین‌شات می‌گیرد**

اگر تصویر معیوب باشد، build همان‌جا شکست می‌خورد — نه اولین درخواست کاربر.

---

## چرا `--no-sandbox`

Chromium داخل کانتینر با namespaceهای محدود نمی‌تواند sandbox خودش را بسازد.
سرویس با کاربر غیرریشه (`fahmyar`, uid 10001) اجرا می‌شود و مرورگر فقط
صفحات محلی خودِ پروژه را بار می‌کند، پس این پرچم سطح حمله‌ای باز نمی‌کند.

---

## عیب‌یابی

| نشانه | علت | درمان |
|---|---|---|
| `libnspr4.so: cannot open shared object` | کتابخانهٔ سیستمی جا افتاده | تصویر را از Dockerfile بسازید، نه نصب دستی |
| `playwright install` با `libatomic.so.1` می‌میرد | `libatomic1` نیست | همان |
| API خطای **503** با `reason: bundle_missing` | `frontend/dist` ساخته نشده | `npm run build` در پوشهٔ `frontend`؛ در Docker خودکار است |
| API خطای **503** با `reason: chromium_missing` | باینری مرورگر نیست | `python -m playwright install chromium` |
| PDF فارسی با فونت سیستم رندر می‌شود | Vazirmatn در باندل نیست | `frontend/public/print-fonts/*.ttf` را بررسی کنید |

خطای ۵۰۳ با `Retry-After: 5` برمی‌گردد و دلیل ساختاریافتهٔ `reason` دارد؛
لاگ سرور پیام کامل و stack را ثبت می‌کند.

---

## آزمون‌ها

```bash
# آزمون‌های واحد پایتون (بدون مرورگر برای بخش‌های غیر PDF)
docker run --rm fahmyar:latest python -m pytest tests/ -q

# تأیید سلامت موتور PDF در همان تصویر
docker run --rm fahmyar:latest python /app/deploy/verify_runtime.py
```

---

## محدودیت‌های شناخته‌شده

- **PDF لایهٔ متنی ندارد.** تصویری خالص است (معماری تصویری، پذیرفته‌شده).
- **هر درخواست یک Chromium کوتاه‌عمر** بالا می‌آورد (~۲–۵ ثانیه برای ۱۲ سؤال).
  در بار بالا باید نمونهٔ مرورگر نگه داشته و درخواست‌ها صف شوند.
- **سقف بسته‌بند:** ۱۲۰ صفحه و ۲۲۰MB تصویر؛ فراتر از آن خطای روشن.
- تصویر نهایی حدود **۱٫۴GB** است (بیشترش Chromium و پکیج‌های پایتون).
