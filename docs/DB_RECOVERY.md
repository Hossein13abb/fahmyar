# نجاتِ دیتابیس پس از خطای «database disk image is malformed»

## این خطا از کجا می‌آید

اگر در صفحهٔ «تاریخچهٔ آزمون‌های من» یا هر جای دیگر این را دیدید:

```
sqlite3.DatabaseError: database disk image is malformed
[SQL: SELECT assessment_sessions.id AS assessment_sessions_id, ...]
```

**دیتابیسِ شما خراب نشده.** در ۹۹٪ موارد فایلِ اصلی سالم است و مشکل از
یکی از این دو فایلِ کنارش است:

| فایل | چیست |
|---|---|
| `fahmyar.db-wal` | تغییرهایی که هنوز در فایلِ اصلی نوشته نشده‌اند |
| `fahmyar.db-shm` | حافظهٔ اشتراکیِ ایندکسِ WAL |

این دو **وضعیتِ موقتِ یک پروسه‌اند، نه داده**. اگر از سیستمی دیگر بیایند
(مثلاً همراهِ `git pull`)، SQLite می‌کوشد تغییرهای یک دیتابیس را روی
دیگری اعمال کند و این خطا را می‌دهد.

### چه اتفاقی افتاد (سابقهٔ فنی)

در کامیتِ `be08ff4` دستورِ `git add -A` این دو فایل را از محیطِ توسعه به
مخزن فرستاد، چون `.gitignore` فقط `*.db` را می‌گرفت و نامِ این‌ها به
`-wal`/`-shm` ختم می‌شود. سپس روی سیستمِ شما با `git pull` این فایل‌ها
کنارِ دیتابیسِ **خودتان** نشستند.

از کامیتِ `a2f9d31` به بعد، `.gitignore` این‌ها را می‌گیرد و تستِ خودکار
(`tests/test_phase33_db_resilience.py`) جلوی تکرارش را می‌گیرد.

---

## راهِ نجات — سه دقیقه

### گامِ ۰: پشتیبان بگیرید (اجباری)

قبل از هر کاری، یک کپی از فایلِ دیتابیس بگیرید:

```powershell
# ویندوز — PowerShell
Copy-Item "D:\fahmyar\fahmyar.db" "D:\fahmyar\fahmyar.db.backup"
```

```bash
# لینوکس / مک
cp ~/fahmyar/fahmyar.db ~/fahmyar/fahmyar.db.backup
```

### گامِ ۱: سرور را ببندید

```powershell
# ویندوز: Ctrl+C در پنجرهٔ uvicorn، یا
Get-Process python | Where-Object { $_.Path -like "*fahmyar*" } | Stop-Process
```

این مهم است: اگر سرور باز باشد، فایل‌ها قفل‌اند و پاک نمی‌شوند.

### گامِ ۲: ابزارِ تعمیر را اجرا کنید

```powershell
cd D:\fahmyar
.\venv\Scripts\python.exe tools\repair_db.py --repair
```

خروجیِ سالم چیزی شبیهِ این است:

```
دیتابیس: D:\fahmyar\fahmyar.db
  فایلِ اصلی : موجود  (2,039,808 بایت)
  فایل‌های WAL:
    • fahmyar.db-wal  (230,752 بایت)
    • fahmyar.db-shm  (32,768 بایت)
  خطا: WALِ ناهمخوان: با WAL 50 ردیف دیده می‌شود، بدونِ آن 5 ردیف.
  وضعیت: نیازمندِ تعمیر ✗

کنار گذاشتنِ فایل‌های WAL/SHM …
  → fahmyar.db-wal.bak-20261127-103012
  → fahmyar.db-shm.bak-20261127-103012

  آزمون‌های ثبت‌شده: 12
  وضعیت: سالم ✓

✓ تعمیر شد. هیچ داده‌ای حذف نشد.
```

**توجه:** ابزار فایل‌ها را `rename` می‌کند، `delete` نمی‌کند. اگر بعداً
لازم شد، می‌توانید برگردانیدشان.

### گامِ ۳: سرور را دوباره بالا بیاورید

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

صفحهٔ تاریخچه باید سالم باز شود.

---

## اگر گامِ ۲ جواب نداد

یعنی مشکل از خودِ فایلِ اصلی است، نه از WAL. در این حالت:

```powershell
# ۱) فایلِ خراب را کنار بگذارید
Rename-Item "D:\fahmyar\fahmyar.db" "fahmyar.db.corrupt"

# ۲) پشتیبان را برگردانید
Copy-Item "D:\fahmyar\fahmyar.db.backup" "D:\fahmyar\fahmyar.db"

# ۳) دوباره بررسی کنید
.\venv\Scripts\python.exe tools\repair_db.py
```

اگر آماری که می‌خواهید در پشتیبان نیست، آخرین راه `PRAGMA integrity_check`
و `sqlite3 .recover` است:

```powershell
# اگر sqlite3 CLI نصب است
sqlite3 fahmyar.db.corrupt ".recover" | sqlite3 fahmyar.db.recovered
```

---

## پیشگیری

| کار | چرا |
|---|---|
| `*.db-wal`, `*.db-shm` در `.gitignore` | انجام شد — این‌ها وضعیتِ موقت‌اند، نه داده |
| دیتابیس را هرگز `git add` نکنید | هر محیط باید دیتابیسِ خودش را داشته باشد |
| پیش از `git pull` سرور را ببندید | فایل‌های قفل‌شده ممکن است جابه‌جا نشوند |
| پشتیبانِ دوره‌ای | یک `cp` روزانه کافی است |

### بررسیِ سلامت (هر وقت خواستید)

```powershell
.\venv\Scripts\python.exe tools\repair_db.py
```

اگر `وضعیت: سالم ✓` دید، همه‌چیز خوب است. این ابزار **هیچ چیزی را تغییر
نمی‌دهد** مگر با `--repair`.
