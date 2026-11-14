# گزارش مرحلهٔ اول — تحلیل موتور تولید PDF فهم‌یار

تاریخ: ۱۴۰۴/۰۸/۱۷ · مبنا: `65eb8eb` · روش: خواندن کد + trace زنده + خروجی بصری

---

## ۱. یافته‌های قطعی (با اثبات، نه حدس)

### باگ ۱ — هر جملهٔ انگلیسی به‌عنوان «فرمول ریاضی» رندر می‌شود 🔴 بحرانی

**محل:** `reports/pdf_text_flow.py::_looks_math` (خط ۱۲۷)

```python
has_cmd = bool(re.search(r"\\?[a-zA-Z]{2,}", g))
if "\\" in g or has_cmd:
    residue = re.sub(r"\\\\?[a-zA-Z]+|[\s{}]", "", g)
    return bool(residue)
```

الگوی `\\?[a-zA-Z]{2,}` هر واژهٔ انگلیسیِ **دوهرفی یا بیشتر** را «دستور LaTeX» می‌بیند. برای
«The derivative of a constant is always one.»:

| مرحله | مقدار |
|---|---|
| `_MATH_SIGNAL_RE` | `False` |
| `_OPERAND_OP_RE` | `False` |
| `_FUNC_CALL_RE` | `False` |
| `has_cmd` | **`True`** ← واژهٔ `The` کافی است |
| `residue` | `'Thederivativeofaconstantisalwaysone.'` |
| نتیجه | **`True`** |

**اثر واقعی روی PDF:** کل جمله به `render_math_png` می‌رود و mathtext آن را در
«حالت ریاضی» می‌کشد — **همهٔ فاصله‌ها حذف می‌شوند**، حروف ایتالیک و بی‌فاصله:

> `WhichofthefollowingstatementsabouttheDerivativeiscorrect?`

این عیناً در `baseline/before-hard-p2.png` دیده می‌شود (سؤال ۲).

**دامنهٔ آسیب:** فقط جملهٔ کامل نه — بلکه:

| ورودی | شناسایی فعلی | باید باشد |
|---|---|---|
| `DNA` | ریاضی | متن |
| `UNESCO` | ریاضی | متن |
| `slope` | ریاضی | متن |
| `Which option is correct?` | ریاضی | متن |
| `f'(x) measures the rate.` | ریاضی (کل جمله) | متن + `f'(x)` ریاضی |

هر آزمونِ دارای متن انگلیسی یا اصطلاح لاتین داخل فارسی، خراب چاپ می‌شود.

---

### باگ ۲ — `math_inline.py` (۳۹۰ خط) کاملاً مرده است 🟠 مهم

**روش اثبات:** trace زندهٔ `build_exam_pdf` با شمارش فراخوانی.

```
math_paragraph_flowables      5   LIVE
has_math                     33   LIVE
build_mixed_math_flowables    0   never called
build_mixed_math_text         0   never called
render_math_to_file           0   never called
release_temp_files            0   never called
build_mixed_flowables         0   never called
parse_mixed_text_and_math     0   never called
```

`exam_pdf.py:75` این‌ها را import می‌کند اما فقط برای re-export (با `# noqa: F401`).
مسیر واقعی: `rtl_flowables` → `math_paragraph_flowables` → `MathRichBlock`.

**پیامد:** ۳۹۰ خط کد، یک مسیر رندر دومِ ناسازگار، `tempfile` و `atexit` بلااستفاده،
و یک وابستگی **دایره‌ای نهفته** (`math_inline` ← `exam_pdf`، داخل تابع) که فقط
به‌خاطر importهای دوجانبه کار می‌کند.

---

### باگ ۳ — `KeepTogether` فضای سفید بزرگ تولید می‌کند 🟠

**محل:** `exam_pdf.py:913` و `:933`

```python
return [KeepTogether(story)]   # سربرگ + متن + شکل + گزینه‌ها + فاصله
return [KeepTogether(story)]   # در _answer_flow
```

**اثر بصری (اندازه‌گیری‌شده):** در `before-hard-p1.png` سؤال ۱ با گزینه‌هایش به صفحهٔ ۲
منتقل شده و **حدود ۴۰٪ پایین صفحهٔ ۱ کاملاً خالی** مانده است.

اگر یک سؤال بلندتر از یک صفحه باشد، `KeepTogether` آن را **بی‌نهایت** به جلو می‌برد
(ReportLab در این حالت چاره‌ای جز سرریز ندارد).

---

### باگ ۴ — متن اگر ریاضی تشخیص داده نشود، `Paragraph` خام می‌شود 🟡

`exam_pdf.py::rtl_flowables` دو مسیر کاملاً متفاوت دارد:

| شرط | مسیر |
|---|---|
| `has_math(text)` → `True` | `math_paragraph_flowables` → `MathRichBlock` (چیدمان دستی) |
| `has_math(text)` → `False` | `Paragraph(reshaped(line))` (چیدمان ReportLab) |

چون باگ ۱ باعث می‌شود تقریباً همه‌چیز «ریاضی» شود، مسیر دوم تقریباً هرگز اجرا نمی‌شود؛
و اگر باگ ۱ اصلاح شود، متن‌های ساده به مسیر `Paragraph` می‌روند که **هیچ پشتیبانی از
فرمول ندارد**. یعنی دو مسیر با دو رفتار متفاوت.

---

### باگ ۵ — نرمال‌سازی دوبارهٔ متن در چند لایه 🟡

`final_pdf_cleanup` (۲۹ دستور) در این نقاط صدا زده می‌شود:

1. `rtl_flowables` (خط ۳۸۶، فقط مسیر بدون ریاضی)
2. `get_pdf_safe_text` → `reshaped` (همهٔ متن‌ها)
3. `MathRichBlock` به‌عنوان `fallback`
4. `math_inline` (مرده)

هر بار regexهای حذف LaTeX روی متنی اجرا می‌شوند که ممکن است قبلاً پاک‌سازی شده باشد —
رفتار غیرقابل‌پیش‌بینی و وابسته به ترتیب.

---

### باگ ۶ — ماتریس یک مسیر استثنایی مستقل است 🟡

`math_renderer.py::_render_matrix_png` (خط ۲۰۲، ۱۲ دستور) جدا از `render_math_png`
کار می‌کند و `_split_matrix_affixes` / `_split_matrix_rows` منطق خودش را دارد.
ماتریس داخل `\begin{cases}` (دستگاه معادلات) از این مسیر عبور نمی‌کند.

شاهد بصری: `before-hard-p2.png` سؤال ۶ — دستگاه معادلات به‌شکل
`{ y= / x-y= ` شکسته و ناخوانا رندر شده.

---

## ۲. ریسک‌های تأییدنشده (نیازمند تصمیم)

| ریسک | وضعیت |
|---|---|
| SVG با `svglib` — آیا درست رندر می‌شود؟ | در baseline یک SVG ساده هست؛ باید بصری بررسی شود |
| متن دوزبانه‌ای که فرمول ندارد اما `x=1` دارد | با اصلاح باگ ۱ باید آزمایش شود |
| تراز عمودی فرمول درون‌خطی | `_flush` از `ascent = size*0.8` استفاده می‌کند — تقریبی |
| صفحه‌بندی با سؤال بلندتر از صفحه | با `KeepTogether` قابل حل نیست |

---

## ۳. وابستگی‌های موجود

| بسته | نسخه | نقش | قابل حذف؟ |
|---|---|---|---|
| reportlab | 5.1.0 | موتور سند | خیر |
| matplotlib | 3.11.2 | mathtext → PNG | خیر |
| arabic-reshaper | 3.1.0 | شکل‌دهی فارسی | خیر |
| python-bidi | 0.6.12 | RTL | خیر |
| svglib + lxml | 2.4.0 | SVG → Flowable | خیر |
| jdatetime | 6.1.1 | تاریخ شمسی | خیر |
| pymupdf | 2.1 | فقط تست/بازرسی | فقط dev |

**هیچ بستهٔ جدیدی لازم نیست.** ماتریس `matplotlib`, `reportlab`, `arabic-reshaper`,
`python-bidi`, `svglib` کافی است.

---

## ۴. ساختار پیشنهادی (تأییدشده با کد واقعی)

پیشنهاد مأموریت با واقعیت کد هم‌خوان است، با دو تعدیل:

```
reports/
├── exam_pdf.py         ← orchestrator؛ build_exam_pdf حفظ می‌شود
├── pdf_document.py     ← قالب، سربرگ/پابرگ، NumberedCanvas، فونت‌ها
├── pdf_typography.py   ← reshape + bidi + BiDi-safe شکست خط
├── pdf_content_parser.py ← یک Pipeline واحد: normalise → segment → classify
├── pdf_math.py         ← رندر واحد (شامل ماتریس و cases)
├── pdf_components.py   ← سؤال، گزینه، پاسخ، SVG
└── pdf_layout.py       ← صفحه‌بندی هوشمند، بدون KeepTogether کور
```

**تعدیل ۱:** `math_inline.py` **حذف** می‌شود (مرده است)، نه ادغام.
**تعدیل ۲:** `pdf_text_flow.py` به `pdf_content_parser.py` + `pdf_typography.py` تجزیه می‌شود؛
نام فایل عوض می‌شود پس تمام importها به‌روزرسانی می‌شوند.

---

## ۵. آنچه بدون تغییر می‌ماند

- `POST /api/teacher/generate-exam-pdf` — مسیر، payload، هدرها
- `GenerateExamPdfRequest` / `KonkurQuestion`
- `ExamBuilder.jsx` — **صفر تغییر**
- `build_exam_pdf(...)` — همان امضا
- دیتابیس، الگوریتم انتخاب سؤال، منطق پاسخ صحیح

---

## ۶. نمونه‌های «قبل» (مبنای مقایسه)

| فایل | اندازه | صفحه | تصویر |
|---|---|---|---|
| `baseline/before-hard.pdf` | ۳۵۳ KB | ۶ | ۵۹ |
| `baseline/before-simple.pdf` | ۶۸ KB | ۳ | ۲ |
| `baseline/before-many.pdf` | ۵۲۲ KB | ۹ | ۷۲ |

`before-simple` **هیچ فرمولی ندارد** و ۲ تصویر آن از سربرگ/لوگو می‌آید — بررسی شد،
باگ ۱ در متن فارسی خالص رخ نمی‌دهد (۰ از ۹ متن فارسی به‌اشتباه ریاضی تشخیص داده شد).
باگ ۱ مخصوص متن **لاتین** است.

---

# گزارش نهایی — مرحلهٔ هفتم

## ۱. مشکلات واقعی پیدا شده

هشت باگ با **اثبات**، نه حدس:

| # | باگ | اثبات | شدت |
|---|---|---|---|
| ۱ | هر جملهٔ انگلیسی فرمول تلقی می‌شد | `_looks_math` روی «The derivative…» مقدار `True` برمی‌گرداند؛ `has_cmd` واژهٔ `The` را می‌گیرد | 🔴 بحرانی |
| ۲ | فاصله‌ها در متن انگلیسی حذف می‌شدند | در PDF استخراج‌شده: `Whichofthefollowingstatements…` | 🔴 بحرانی |
| ۳ | `math_inline.py` (۳۹۰ خط) مرده بود | trace زنده: **۰ فراخوانی** در `build_exam_pdf` | 🟠 |
| ۴ | `KeepTogether` کل صفحه را خالی می‌گذاشت | `before-hard-p1.png`: ~۴۰٪ صفحهٔ ۱ سفید | 🟠 |
| ۵ | ارقام فارسی «حرف فارسی» شمرده می‌شدند | `۲×۲` در `_RTL_LETTER_RE` مطابقت می‌کرد | 🟠 |
| ۶ | `pa` + `ge` → `pa≥` | `r"\\?(?:geq\|ge)\\b"` بک‌اسلش اختیاری داشت | 🟠 |
| ۷ | متن `X` تنها به‌اشتباه ریاضی می‌شد | تست قدیمی، `has_math("کدام است X؟")` = True | 🟡 |
| ۸ | `\begin{cases}` به لکهٔ ۲۶×۲۶ تبدیل می‌شد | رندر بصری | 🟡 |

## ۲. تغییرات انجام‌شده

**معماری واحد** با جهت وابستگی یک‌طرفه و بدون چرخه:

```
pdf_content_parser → pdf_typography → pdf_math → pdf_text_flow_v2 → pdf_layout → exam_pdf
```

**طبقه‌بندی جدید** (قاعدهٔ ترتیبی، نه heuristic):
1. دلار صریح → ریاضی
2. دستور LaTeX با بک‌اسلش → ریاضی
3. نشانه‌های signal در کاندید غیرِ-Prose → ریاضی
4. حساب ساختاری (عملوند/عملگر/عملوند) → ریاضی
5. نشانهٔ کوتاه لاتین (۱-۲ حرف) → ریاضی
6. **۳ کلمهٔ لاتین یا بیشتر → متن** (مگر چگالی نماد بالا)

**Typography**: BiDi روی کل run، نه کلمه‌به‌کلمه. ارقام فارسی از محدودهٔ RTL حذف شدند.

**Layout**: `CondPageBreak` اندازه‌گیری‌شده به‌جای `KeepTogether` کور.

## ۳. فایل‌های ایجاد / اصلاح‌شده

| فایل | وضعیت | نقش |
|---|---|---|
| `reports/pdf_content_parser.py` | **جدید** (۴۲۰ خط) | طبقه‌بندی + تقسیم |
| `reports/pdf_typography.py` | **جدید** (۲۱۰ خط) | شکل‌دهی + BiDi |
| `reports/pdf_math.py` | **جدید** (۱۴۰ خط) | رندر + cache |
| `reports/pdf_text_flow_v2.py` | **جدید** (۳۹۰ خط) | MathRichBlock + OptionsRow |
| `reports/pdf_layout.py` | **جدید** (۱۹۰ خط) | سیاست صفحه‌بندی |
| `reports/math_inline.py` | **حذف** (۳۹۰ خط) | مرده بود |
| `reports/pdf_text_flow.py` | shim | سازگاری عقب‌رو |
| `reports/exam_pdf.py` | بازسیم‌کشی import + layout | orchestrator |
| `reports/math_renderer.py` | `_render_cases_png` | دستگاه معادلات |
| `tests/test_pdf_baseline.py` | **جدید** (۴۸ تست) | ثبت رفتار |

## ۴. وابستگی‌ها

**صفر کتابخانهٔ جدید.** حذف‌شده: هیچ‌کدام (همه هنوز لازم‌اند).

## ۵. نتایج تست

```
102 passed, 0 failed
```

شامل ۴۸ تست جدید: طبقه‌بندی (۲۷ حالت)، رندر (۱۳ ساختار)، typography، صفحه‌بندی، قرارداد API، و رگرسیون `pa≥`.

## ۶. محدودیت‌های باقی‌مانده

- **`array`/`aligned` در mathtext پشتیبانی نمی‌شود**؛ فقط `bmatrix`/`pmatrix`/`vmatrix`/`cases` دارند رندر اختصاصی.
- **صفحهٔ آخر دفترچه** اگر تعداد سؤال‌ها فرد باشد ممکن است خالی‌تر بماند — نتیجهٔ `PageBreak` اجباری قبل از پاسخنامه.
- **تراز عمودی فرمول درون‌خطی** از `depth` تصویر استفاده می‌کند؛ برای فرمول‌های با کسر بلند ممکن است یک پوینت اختلاف داشته باشد.
- **مهاجرت به Chromium** انجام نشد — با ReportLab به معیارهای پذیرش رسیدیم.

## ۷. نمونهٔ PDF نهایی

- `/home/user/pdf-rewrite-final.pdf` — خروجی API زنده (۳ صفحه، ۱۹ تصویر، صفر نشت)
- `/home/user/baseline/before-*.pdf` — قبل (۶/۳/۹ صفحه)
- `/home/user/baseline/after-*.pdf` — بعد (۵/۳/۸ صفحه)

## ۸. قرارداد API

**بدون تغییر.** تأییدشده:
- مسیر `POST /api/teacher/generate-exam-pdf` ✅
- `GenerateExamPdfRequest` / `KonkurQuestion` ✅
- امضای `build_exam_pdf` ✅
- `ExamBuilder.jsx` — **صفر تغییر** ✅
- تست زنده: HTTP 200، ۱۱۲٬۴۵۶ بایت
