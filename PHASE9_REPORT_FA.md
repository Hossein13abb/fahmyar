# گزارشِ فاز ۹ — از «شکلِ پاسخ» به «شاهدِ پاسخ»

## ۱. وضعیتِ تحویل

| مورد | مقدار |
|---|---|
| SHA نهایی | `5ad5cd4` (`4e95351` = کامیتِ اصلیِ فاز ۹، `5ad5cd4` = افزودنِ شاهدِ تصویری) |
| شاخه‌ها | `main` و `master` هر دو روی `5ad5cd4`؛ `origin` همگام |
| مخزن | https://github.com/Hossein13abb/fahmyar |
| مدلِ پیش‌فرض | `deepseek/deepseek-v4.1-flash-1017` |
| تست‌ها | **۱۳۴ passed** (خروجی: `134 passed, 183 warnings in 1.74s`) |
| `git diff --check` | بدون خطا |
| درختِ کاری | پاک |

> ⚠️ **نکتهٔ صداقتی دربارهٔ شاهدِ زنده.** طبق بند ۷ فقط **یک** smoke زنده مجاز بود و
> همان اجرا شد. بعد از آن `fahmyar.db` از بکاپِ `phase9` بازگردانده شد تا فایلِ
> آزمایشی commit نشود؛ آن بکاپ **قبل از** نشستِ E2E گرفته شده بود، پس ردیف‌های
> نشستِ ۳۸ در دیتابیسِ فعلی نیستند. شاهدِ تصویریِ کارنامه
> (`docs/screenshots/phase9-report.png`) و اعدادِ هزینه در همین گزارش مستند
> مانده‌اند، اما **در دیتابیسِ زنده قابلِ بازپخش نیستند**. آنچه بازپخش‌شدنی است:
> ۱۳۴ تستِ mock و smokeِ واقعیِ دوم (تحلیل، ۱ تلاش) که خروجی‌اش در بخش ۶ آمده است.

---

## ۲. بند ۱ — پاسخِ واقعی در کارنامه

| تغییر | فایل |
|---|---|
| `_raw_student_answer` صرفاً از `evidence_log` می‌خواند | `reports/exam_report.py` |
| `_looks_like_model_output` پاسخِ شبیه‌به‌مدل را رد می‌کند | `reports/exam_report.py` |
| پاسخِ خالی → «بدون پاسخ» | `reports/exam_report.py` + `ReportView.jsx` |
| تستِ برابری برای هر ۵ مرحله | `tests/test_phase9_regressions.py` |

`cognitive_verdict` / `qualitative_feedback` / `reasoning` در هیچ مسیری جای پاسخ
نمی‌نشینند. در اسکرین‌شات، سؤال ۱ عبارت «بدون پاسخ» را نشان می‌دهد و متنِ
تحلیلیِ مدل در جای پاسخ نیست.

## ۳. بند ۲ — MCQ: یک منبعِ حقیقت، صفرمبنا

**ریشهٔ باگ پیدا و بسته شد:** `_coerce_index(..., one_based=True)` در
`normalize_stage_items` کلیدِ گزینهٔ ۱ را به ۰ تبدیل می‌کرد، Q2 کلیدِ نامعتبر
می‌گرفت و بی‌صدا به fallback می‌افتاد. حالا صفرمبنا است و
`selected_option_index` خام ذخیره می‌شود.

| تغییر | فایل |
|---|---|
| حذف `one_based=True` از نرمال‌سازیِ کلید | `ai/stage_chain.py` |
| `verify_mcq_key` + `_OHM_PATTERN` (۱۲ ولت ÷ ۴ اهم ⇒ ۳ آمپر) | `ai/stage_chain.py` |
| `_DIACRITICS` برای ارقامِ فارسی/عربی و اعراب | `ai/stage_chain.py` |
| یک منبع برای «پاسخ شما»، رنگِ گزینه‌ها و کارنامه (`index+1`) | `ExamRoom.jsx`, `ReportView.jsx` |
| توضیحِ اختیاری جدا و بی‌اثر بر استخراجِ انتخاب | `api/routes_assessment.py`, `ExamRoom.jsx` |
| `options` در `evidence_log` و `per_question` (بدونِ `correct_option_index`) | `api/routes_assessment.py`, `reports/exam_report.py` |

تست‌های (الف) تا (د) همه در `tests/test_phase9_regressions.py` پیاده شدند:
انتخابِ «۳ آمپر» → برچسب ۳؛ توضیحِ حاوی «۳»/«۴» بی‌اثر؛ «۳ آمپر» سبز و
«۰٫۲۳ آمپر» هرگز سبز نشود؛ کلیدِ ناخوانا با ۱۲÷۴ ⇒ ردِ سؤال.

## ۴. بند ۳ — حکمِ معنایی، نه شمارشی

| تغییر | فایل |
|---|---|
| برچسبِ `correct|partial|incorrect|insufficient` + شاهدِ مستقیم | `ai/cross_check.py` |
| حذفِ کامل `debugging_strong` و `substantive` و منطقِ طول/تعدادِ کلمه | `ai/cross_check.py` |
| `MASTERED` فقط با `correct` بودنِ مرحلهٔ ۳ **و** ۴ | `ai/cross_check.py` |
| `_WRONG_Q4_CLAIMS` هر دو جهتِ بدفهمی ⇒ حداکثر `partial` | `ai/cross_check.py` |
| `derive_status` منبعِ واحد؛ `_verdict_culprit` (Q4→Q3→Q1→Q5) | `ai/cross_check.py` |
| نشان/`persona_title`/`executive_summary` از همان وضعیت | `ai/cross_check.py` |

**شاهدِ زنده:** در هر دو smoke، پاسخِ Q4 («جریان تغییر می‌کند تا مقاومت ثابت
بماند») با گارد گرفته شد:
`[CrossCheck] Q4 was marked correct but contains a wrong claim: … — وارونه‌گوییِ رابطه`
و حکمِ نهایی `ILLUSION_OF_COMPETENCE` شد، نه `MASTERED`.

## ۵. بندهای ۴ و ۵ — کارت‌ها، یافته‌ها و متنِ سؤال‌ها

| تغییر | فایل |
|---|---|
| برچسبِ کارت از همان دادهٔ حکم؛ ممنوعیتِ «کامل» + «نامشخص» | `ai/cross_check.py`, `ReportView.jsx` |
| «ابعادِ فهم» فقط با دادهٔ معتبر؛ «روشن‌نشده» فقط واقعی | `ReportView.jsx` |
| `_filter_false_synergy` فقط Q3/Q4 و با هم‌سوییِ واقعی | `ai/cross_check.py` |
| حذفِ «هیچ نقشی ندارند» از Q2 | `ai/stage_chain.py` |
| Q1 یک پرسشِ متمرکز، بدونِ لو دادنِ پاسخ | `ai/stage_chain.py` |
| حذفِ «نه ویژگیِ منبعِ تغذیه» و «یک نفسِ عمیق بکش» | `ai/stage_chain.py` |
| «محدودکنندهٔ ثابتِ مسیر» → فارسیِ کتاب‌درسی | `ai/stage_chain.py` |
| `LEAKY_PHRASES` + تستِ نبودِ عباراتِ لو‌دهنده | `ai/stage_chain.py`, تست‌ها |
| `_FORMULA_HINT` سخت شد تا «رابطه‌ای» فرمول شمرده نشود | `ai/stage_chain.py` |

## ۶. بند ۶ — مدل، توکن، هزینه

| تغییر | فایل |
|---|---|
| لاگِ `[AI] assessment model = … (source=…; timeout=…)` در startup | `main.py` |
| `OPENROUTER_PINNED_MAX_ATTEMPTS=2` (۳ فراخوانی در کل)، بدونِ fallbackِ پنهان | `config.py`, `.env.example` |
| timeout از `.env` (۶۰ ثانیه)، نه هاردکد | `ai/model_abstraction.py` |
| `OPENROUTER_MAX_TOKENS` پیش‌فرض ۸۰۰۰ → **۱۶۰۰۰** | `config.py`, `ai/model_abstraction.py`, `.env.example` |
| قیمت هاردکد **نیست**؛ هزینه از `usage.cost` خودِ OpenRouter | `ai/model_abstraction.py` |
| `usage_ledger`: مدل/توکنِ in-out/هزینه/زمان/نوع، **جمع‌شونده** | `ai/model_abstraction.py` |
| `reset_usage_ledger()` در **start-test** (نه submit) | `api/routes_assessment.py` |
| `ai_usage` در متادیتای گزارش + پنلِ معلم | `reports/exam_report.py`, `ReportView.jsx` |

### هزینهٔ واقعیِ اندازه‌گیری‌شده

| فراخوانی | تلاش | توکن (in/out) | هزینه |
|---|---|---|---|
| تولیدِ ۵ مرحله | ۱ ✓ | ۶٬۸۹۶ (۳٬۴۶۲ / ۳٬۴۳۴) | `$0.003354` |
| تحلیل — سقفِ ۸٬۰۰۰ | ۱ ✗ `finish_reason=length`، ۲ ✓ | ۱۳٬۴۲۳ (۵٬۴۹۴ / ۷٬۹۲۹) | `$0.004624` |
| تحلیل — سقفِ ۱۶٬۰۰۰ | ۱ ✓ | ۱۱٬۷۵۸ (۳٬۴۳۱ / ۸٬۳۲۷) | `$0.007164` |

سقفِ ۸٬۰۰۰ در مجموع ۲۰٬۳۱۹ توکن و `$0.007978` خورد. با سقفِ ۱۶٬۰۰۰، تحلیل در
**یک تلاش** تمام شد؛ یعنی بالا بردنِ سقف، تلاشِ دوباره‌ای که ۱۳٬۴۲۳ توکن
می‌سوزاند را حذف کرد. (هزینهٔ هر توکن ثابت است؛ آنچه کم می‌شود توکنِ سوخته است، نه قیمت.)

## ۷. بند ۷ — تست و شاهد

- `tests/test_phase9_regressions.py` — **۴۰ تستِ mock**، شاملِ سناریوی واقعیِ
  «قانون اهم»: Q2 با انتخابِ «۳ آمپر» و توضیحی حاوی «۳» و «۴»؛ Q4 با ادعای
  جریانِ متغیر؛ Q1 با پاسخِ کوتاه.
- `tests/test_stage_chain.py` — انتظارِ اندیسِ صفرمبنا (۲ به‌جای ۳).
- `tests/test_phase8_assessment.py` — سازگار با `_usage_from` چهارتایی.
- کلِ مجموعه: **۱۳۴ passed**؛ بدونِ درخواستِ واقعی در تست‌ها.
- `git diff --check` پاک؛ `.env`، کلید و فایلِ موقت commit نشدند (اسکنِ
  `sk-or-v1`/`ghp_` روی diff: پاک).
- `COGNITIVE_ENGINE.md` بخشِ ۱۰ (فاز ۹) را گرفت.

## ۸. تنظیماتِ `.env` لازم

```env
OPENROUTER_ASSESSMENT_MODEL=deepseek/deepseek-v4.1-flash-1017
OPENROUTER_PINNED_MAX_ATTEMPTS=2
OPENROUTER_TIMEOUT_SECONDS=60
OPENROUTER_MAX_TOKENS=16000
OPENROUTER_API_KEY=sk-or-v1-...
```

> ⚠️ **دو اقدامِ امنیتیِ باز:**
> ۱. توکنِ GitHub در همین گفتگو به‌صورتِ متنِ ساده منتشر شد؛ **باطل و
>    جایگزینش کنید**.
> ۲. `OPENROUTER_API_KEY` در `.env` محلی است و commit نشده، اما در جریانِ این
>    کار در گفتگو دیده شد؛ اگر همان کلید است، **rotate کنید**.

## ۹. فهرستِ کلیِ تغییرات

```
 .env.example                      |   8 +-
 COGNITIVE_ENGINE.md               | بخشِ ۱۰ اضافه شد
 PHASE9_REPORT_FA.md               | جدید (همین گزارش)
 ai/cross_check.py                 | 425 +++++++++++++++-----
 ai/model_abstraction.py           | 137 +++++--
 ai/stage_chain.py                 | 186 +++++++--
 api/routes_assessment.py          |  52 +++-
 config.py                         |   5 +-
 docs/screenshots/phase9-report.png| جدید
 frontend/src/pages/ExamRoom.jsx   |  79 +++-
 frontend/src/pages/ReportView.jsx |  75 +++-
 main.py                           |  16 +
 reports/exam_report.py            |  52 ++-
 tests/test_phase8_assessment.py   |  19 +-
 tests/test_phase9_regressions.py  |  جدید (۴۰ تست)
 tests/test_stage_chain.py         |  15 +-
```

## ۱۰. آنچه هنوز باز است

1. **روتیتِ دو کلید** (بخش ۸) — تنها اقدامِ امنیتیِ باقی‌مانده.
2. **`STATUS_FA`** هنوز سه‌حالته است؛ اگر برچسبِ فارسیِ `INSUFFICIENT_EVIDENCE` در
   جایی از UI لازم شد، باید گسترش یابد (در حالِ حاضر «بدون پاسخ» در سطحِ پاسخ
   مدیریت می‌شود، نه در این دیکشنری).
3. **دیتابیسِ زنده** ردیفِ نشستِ ۳۸ را ندارد (توضیح در بخش ۱); اگر بازپخشِ
   کارنامهٔ واقعی لازم شد، یک نشستِ تازه لازم است که در سقفِ smoke نمی‌گنجد.
